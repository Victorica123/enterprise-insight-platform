# Enterprise Insight Platform 面试演示脚本

目标是在 8 分钟内证明业务闭环、Agent 工程和真实性边界。不要把时间花在注册表单或配置排错上。

## 演示前准备

1. 使用 JDK 17/18、Python 3.12 和 Node.js 22。
2. 准备一个小型 MP4；本地 mock 转写只验证链路，不用于展示真实语音质量。
3. 启动持久本地工作台：

```powershell
./scripts/start_local.ps1 -Build
```

4. 打开 `http://127.0.0.1:8080`，提前创建两个账号并准备一个 team Workspace。
5. 演示前跑一次：

```powershell
python scripts/local_acceptance.py
```

保留最后的 PASS 和 checks 输出，UI 异常时可作为兜底证据。

仓库还保留三张已验收截图作为静态兜底：`docs/images/interview/knowledge-materialization.png`、`approved-knowledge-source.png` 和 `cache-hit.png`。截图只能证明该次本地运行，不替代现场自动验收结果。

## 8 分钟主线

### 0:00-0:45 定位

话术：

> 这个平台把会议视频和文档转成可回放证据、PRD、受治理知识和行动项。两个后端不是历史遗留拼接：Media 拥有媒体和身份，Agent 拥有分析和知识，通过 JWT 与版本化事件形成一个产品。

展示统一顶部品牌、当前 Workspace 和主导航。

### 0:45-1:45 视频到证据

上传小视频，展示任务状态和时间戳片段。进入知识问答并选择该视频，提问：

> 这段会议材料提出了什么需求？请给出可回放证据。

点击视频证据，说明播放 token 由 Media Service 短时签发，Agent 不保存对象存储凭证。

### 1:45-3:15 六阶段分析与恢复

进入“需求分析”，创建目标：

> 基于当前视频生成一份可评审的交付需求 PRD。

如果进入等待状态，填写：

- 决策人：产品负责人；
- 验收标准：审批后 2 秒内展示明确结果；
- 优先级规则：合规阻塞项优先；
- 证据范围：仅使用当前视频。

强调当前恢复的是同一持久化业务阶段 checkpoint，而不是模型执行栈：接口读取创建时冻结的证据，校验并 CAS 消费 resume token，合并人工答案，保留阶段 1–4，只重算收敛与 PRD。页面展示 checkpoint version、evidence revision 与 hash；不要把它讲成实习系统中的 AppServer/WebSocket continuation。

### 3:15-4:30 PRD 与审批

展示六阶段结果、证据化需求和假设。申请发布后说明：

- personal：OWNER 必须进行第二次明确确认；
- team：提交者不能批准自己的 PRD。

展示审计记录和 PRD 内容哈希。

### 4:30-5:25 知识沉淀

在“发布交付物”中点击“批准并沉淀”，展示：

- 状态变为 `APPROVED`；
- 出现托管知识 document ID；
- 出现 SHA-256 摘要。

回到“知识问答”，提问：

> 已批准业务知识有哪些？

指出来源标签为“已批准知识”，并解释它仍保留 candidate、PRD version 和原始证据；图谱或索引失败会整体回滚。

### 5:25-6:10 知识替代与撤回

回到分析交付物，在一个活跃候选下填写治理原因和替代陈述，点击“申请替代”，再完成第二次决定。展示 v1 `SUPERSEDED`、v2 `ACTIVE` 和双向版本链。重新提问时只命中 v2；打开旧聊天回放时，原引用仍存在但显示 `SUPERSEDED` 及替代文档。时间允许时再申请撤回，说明未来 RAG 和图谱不再使用该版本，但历史文档未删除。team 空间必须由另一位写成员决定。

### 6:10-6:50 行动项闭环

把行动项送入工单审批，展示 pending action；由授权用户批准后，真实 `ticket_id` 回写到发布交付物。强调 Agent 不能直接执行高风险写操作。

### 6:50-7:30 团队隔离

切换 team Workspace，展示两名成员共享媒体/知识；切回 personal 后资源不可见。VIEWER 能读但不能上传或审批。

### 7:30-8:00 指标与边界

打开监控页，展示请求延迟、token、执行轨迹和两个缓存命中率。最后主动说明：

> 当前演示使用 localhost 和 mock AI，证明的是身份、状态、证据、审批、恢复和检索闭环；真实模型质量、统一平台生产吞吐和正式 SLA 需要独立环境证据。

## 无 UI 兜底

如果现场端口、浏览器或 Docker 不可用，运行：

```powershell
python scripts/local_acceptance.py
```

按输出解释 33 项检查中的七组：

1. 身份与个人/团队隔离；
2. 视频、outbox、Agent 摄取和时间戳证据；
3. objective 证据快照、阶段稳定与旧 resume token 拒绝；
4. 六阶段等待恢复与 PRD 审批；
5. 知识物化、替代/撤回、版本链与历史引用状态；
6. 工单审批与团队生命周期四眼；
7. VIEWER 只读、缓存鉴权和播放 Range。

## 演示禁区

- 不现场下载模型或安装中间件。
- 不用随机问题测试模型“聪明程度”。
- 不把 mock transcript 当语音识别效果。
- 不展示密钥、JWT、数据库路径或对象存储凭证。
- 不宣称候选 SLO 已经兑现。
