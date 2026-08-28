# 架构说明

本文用图讲清楚三件事：系统怎么分层、一次 Agentic 问答怎么流转、一次写操作怎么被审批。
所有图均为 Mermaid，GitHub 原生渲染。

## 系统分层

```mermaid
flowchart TB
    subgraph web["前端 apps/web（React 19 + Vite）"]
        QA["知识问答面板"]
        TK["工单与审批面板"]
        GR["关系图谱面板"]
        MO["运行监控面板"]
    end

    subgraph api["后端 apps/api（FastAPI）"]
        routes["routes/ 薄端点层<br/>chat · documents · tickets · graph · observability"]
        subgraph core["领域层"]
            ORCH["agentic_rag 编排器"]
            RAG["rag 标准 RAG + 证据门控"]
            RET["retrievers 检索器<br/>keyword / embedding / hybrid(RRF)"]
            SLOT["slot_extraction 槽位抽取"]
            TOOLS["tools 受控工具注册表"]
            TSTORE["ticket_store 工单/审批/审计"]
            GSTORE["graph_store 图存储 + BFS"]
        end
        subgraph infra["基础设施层"]
            DB[("SQLite<br/>WAL + busy_timeout")]
            LLM["llm_client / llm_router<br/>超时·重试·token 预算"]
            EMB["embeddings<br/>fastembed 或哈希降级"]
            LOG["logging_config<br/>JSON 结构化日志"]
        end
    end

    QA & TK & GR & MO -->|X-User-Role / X-User-Id| routes
    routes --> ORCH & RAG & TSTORE & GSTORE
    ORCH --> RAG & RET & SLOT & TOOLS & GSTORE
    TOOLS --> TSTORE
    core --> infra
```

要点：

- **路由层只做协议转换**，业务在领域层；`main.py` 只负责装配（lifespan 初始化 + CORS + 路由注册）。
- **鉴权策略集中在 `app/auth.py`**：所有端点读 `X-User-Role`，写操作与审计数据要求 operator+，替换为 JWT/OIDC 只改这一个模块。
- **SQLite 单文件承载全部持久化**（文档/chunk/向量、图谱、工单、审批、审计、指标），WAL + `busy_timeout` 应对读写并发，生产化时替换为 PostgreSQL + pgvector（见 [engineering-optimization.md](engineering-optimization.md)）。

## Agentic 问答流水线

```mermaid
flowchart LR
    Q["用户问题"] --> ROUTER{"Router Agent<br/>意图 + 复杂度<br/>LLM 或规则"}
    ROUTER -->|纯工单操作| TOOLONLY["跳过检索<br/>直接 Tool Agent"]
    ROUTER -->|知识型问题| PLANNER["Planner Agent<br/>query 改写与扩展<br/>LLM 或规则"]
    PLANNER --> RETRIEVE["Retriever Agent<br/>hybrid 检索"]
    RETRIEVE --> EVIDENCE{"Evidence Agent<br/>分数 + 意图覆盖<br/>+ 主题锚点"}
    EVIDENCE -->|不足且 complex| RETRY["第二轮重查<br/>（最多 2 轮）"]
    RETRY --> RETRIEVE
    EVIDENCE -->|通过| GRAPH["Graph Agent<br/>实体邻域 + 关系链"]
    EVIDENCE -->|仍不足| REFUSE["拒答<br/>不编造"]
    GRAPH --> TOOL["Tool Agent<br/>LLM 工具选择（白名单过滤）<br/>或关键词规则"]
    TOOL -->|写操作| DRAFT["生成审批草稿<br/>不直接写库"]
    TOOL --> ANSWER["Answer Agent<br/>API 或本地模板"]
    DRAFT --> ANSWER
    ANSWER --> REVIEW["Reviewer Agent<br/>引用审核 + 声明级溯源"]
    REVIEW --> OUT["回答 + 来源 + trace"]
    TOOLONLY --> TOOL
    REFUSE --> OUT
```

防幻觉是分层的：检索分数门控挡低质证据，主题锚点挡词面重合的无关语料，
含数字/日期/百分比的陈述必须在来源中找到锚点，否则附审核提示；证据不足时明确拒答。

## 写操作审批流（Human-in-the-loop）

```mermaid
sequenceDiagram
    participant U as 用户（operator）
    participant A as Agent
    participant DB as SQLite
    participant V as 审批人（operator/admin）

    U->>A: "要不要创建工单跟进？"
    A->>DB: insert pending_action（status=pending）<br/>幂等键去重 · TTL 15 分钟
    A-->>U: 回答 + 待审批操作（数据库无工单）
    U->>V: 通知审批（发起人不能自批，X-User-Id 相同则 403）
    V->>DB: approve → begin immediate 原子抢占<br/>（status=pending → executing）
    DB->>DB: 校验参数 → 执行 → status=succeeded
    V-->>U: 工单创建成功
    Note over DB: 重复批准 → already_resolved（幂等）<br/>过期/拒绝 → 不产生任何写入<br/>exact_once_violations 指标监控重复执行
```

## 数据模型（核心表）

```mermaid
erDiagram
    documents ||--o{ chunks : "切块"
    chunks {
        text id "docId:idx"
        text content
        text title "标题层级链（A4）"
        text embedding_json "哈希向量（降级通道）"
        text embedding_v2_json "BGE 512 维（可选）"
    }
    documents {
        text id
        text filename
    }
    graph_entities {
        text name
        text entity_type "客户/项目/人员/合同/日期..."
    }
    graph_relations {
        text source_name
        text relation_type "委托/负责人/延期原因..."
        text evidence "证据句"
    }
    tickets ||--o{ pending_actions : "草稿指向工单"
    pending_actions {
        text action_id
        json payload
        text status "pending/executing/succeeded/failed/rejected/expired"
        text idempotency_key "等价草稿去重"
        text requested_by_user "职责分离"
    }
    tool_call_logs {
        text tool_name
        text status
        json input_json
        json result_json
    }
    chat_logs {
        text question
        text outcome "answered/refused/error"
        text trace_json "失败回放"
    }
    chat_metrics {
        text outcome
        real latency_ms
        integer total_tokens
    }
```

隐私分层：`chat_metrics` 只有聚合指标不含问题原文；含原文的 `chat_logs` / `tool_call_logs`
对应端点要求 operator+ 角色。

## 关键设计取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 图数据库 | SQLite + BFS（≤4 跳） | 学习版 GraphRAG 零部署门槛；生产换 Neo4j 时 `graph_store` 是唯一改动点 |
| 向量库 | SQLite 存向量 + 内存相似度 | 同上；生产换 pgvector |
| LLM 路由 | LLM 优先 + 规则降级 | 无 Key/离线/CI 都能跑，`LLM_ROUTER_ENABLED=0` 强制规则版 |
| Embedding | fastembed 本地 ONNX，缺失降级哈希 | 零外部服务依赖，装 `requirements-embedding.txt` 即升级 |
| 鉴权 | Header 角色演示级 | 演示优先；策略单点收敛在 `auth.py` 便于换 JWT |
| 延迟门禁 | 墙钟阈值留余量（200/150ms） | 共享 CI runner 波动大；算法级回退仍会数量级超标被拦截 |
