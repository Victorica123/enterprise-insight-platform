# 项目问题排查知识库

> 用途：记录开发过程中遇到的错误、原因、排查方法和最终解决方案。  
> 后续遇到新问题时，优先把经验追加到这里，方便换对话或复盘时快速定位。

## 1. 前端上传文件时报 `Failed to fetch`

### 现象

在前端页面上传文件后，页面提示：

```text
Failed to fetch
```

或者改进后的提示：

```text
无法连接后端服务。请确认 FastAPI 已启动，地址为 http://127.0.0.1:8000，并检查端口、CORS 或网络拦截。
```

### 本次实际原因

本次用命令检查：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get -TimeoutSec 3
```

结果：

```text
由于目标计算机积极拒绝，无法连接。 (127.0.0.1:8000)
```

这说明：

```text
后端 FastAPI 没有在 8000 端口运行，或者运行后崩了。
```

前端默认请求地址是：

```text
http://127.0.0.1:8000
```

如果后端没启动，浏览器的 `fetch()` 无法建立连接，就会抛出网络层错误。浏览器为了安全，通常只给很笼统的：

```text
Failed to fetch
```

### 常见原因

`Failed to fetch` 常见不是业务错误，而是浏览器没有拿到可用 HTTP 响应。

常见原因包括：

1. 后端服务没有启动。
2. 后端端口不对。
3. 前端配置的 API 地址不对。
4. 后端启动后报错退出。
5. CORS 没配置或配置不匹配。
6. 请求被浏览器、代理、防火墙或安全软件拦截。
7. 上传文件太大，后端或代理提前断开连接。
8. 前端使用 `https`，后端是 `http`，产生 mixed content 问题。

### 如何快速排查

#### 第一步：确认后端是否启动

运行：

```powershell
cd "D:\multi agents\apps\api"
uvicorn app.main:app --reload --port 8000
```

然后打开：

```text
http://127.0.0.1:8000/docs
```

或者测试：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get -TimeoutSec 3
```

正常应该返回：

```json
{
  "status": "ok"
}
```

#### 第二步：确认前端 API 地址

前端默认地址在：

```text
apps/web/src/api.ts
```

当前默认：

```text
http://127.0.0.1:8000
```

如果要改，创建：

```text
apps/web/.env
```

内容：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

修改后要重启前端：

```powershell
cd "D:\multi agents\apps\web"
npm run dev
```

#### 第三步：确认 CORS

后端 CORS 配置在：

```text
apps/api/app/main.py
```

当前允许：

```text
http://127.0.0.1:5173
http://localhost:5173
```

如果前端换了端口，比如 `5174`，需要把新地址加入 `allow_origins`。

#### 第四步：看浏览器开发者工具

打开浏览器 DevTools：

```text
F12 -> Network
```

观察上传请求：

- 如果请求状态是 `(failed)`，通常是网络层问题。
- 如果状态码是 `400`，说明后端收到请求，但业务校验失败。
- 如果状态码是 `422`，说明请求格式不符合 FastAPI 接口定义。
- 如果状态码是 `500`，说明后端内部报错。
- 如果 Console 出现 CORS 字样，说明跨域配置有问题。

### 本项目中的解决方案

1. 先启动后端：

```powershell
cd "D:\multi agents\apps\api"
uvicorn app.main:app --reload --port 8000
```

2. 再启动前端：

```powershell
cd "D:\multi agents\apps\web"
npm run dev
```

3. 打开前端：

```text
http://127.0.0.1:5173
```

4. 如果再次失败，先访问：

```text
http://127.0.0.1:8000/health
```

确认后端是否还活着。

### 已做代码改进

前端 `apps/web/src/api.ts` 已新增 `safeFetch()`。

作用：

- 捕获浏览器的网络层 `TypeError`。
- 把笼统的 `Failed to fetch` 转换成更明确的中文提示。

现在不会只显示：

```text
Failed to fetch
```

而是显示：

```text
无法连接后端服务。请确认 FastAPI 已启动，地址为 http://127.0.0.1:8000，并检查端口、CORS 或网络拦截。
```

### 和视频上传平台的关系

视频上传平台也经常出现 `Failed to fetch`，原因类似：

- 上传接口后端没启动。
- 前端 API 地址错了。
- CORS 没配。
- 文件过大导致连接被代理或后端断开。
- 后端处理上传时崩溃。
- nginx / 网关限制了请求体大小。

视频上传场景还要额外检查：

- 后端最大上传大小限制。
- nginx 的 `client_max_body_size`。
- 前端是否使用 `FormData`。
- 后端字段名是否和前端一致。
- 上传耗时是否超过超时限制。

## 2. PDF 上传后没有内容或解析失败

### 现象

上传 PDF 时可能出现：

```text
No readable text was found in the file.
```

或：

```text
PDF could not be parsed. Please check whether the file is valid or encrypted.
```

### 常见原因

1. PDF 是扫描件，本质是图片，没有文字层。
2. PDF 被加密。
3. PDF 文件损坏。
4. 后端没有安装 PyMuPDF。
5. PDF 里文字是特殊编码，提取结果为空或乱码。

### 当前实现

后端文件：

```text
apps/api/app/document_parser.py
```

当前使用：

```text
PyMuPDF
```

依赖写在：

```text
apps/api/requirements.txt
```

如果缺依赖，运行：

```powershell
cd "D:\multi agents\apps\api"
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 后续优化

如果要支持扫描版 PDF，需要增加 OCR，例如：

- PaddleOCR
- Tesseract
- 云 OCR 服务

但 OCR 会引入更多依赖和环境配置，当前 V1 先只支持有文本层的 PDF。

## 3. pip 安装 PyMuPDF 时报 SSL 或 versions none

### 现象

执行：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或：

```powershell
python -m pip install PyMuPDF==1.26.3 -i https://mirrors.aliyun.com/pypi/simple/
```

出现：

```text
SSLEOFError(8, 'EOF occurred in violation of protocol')
ERROR: Could not find a version that satisfies the requirement PyMuPDF==1.26.3 (from versions: none)
```

### 本次实际判断

这不是 PyMuPDF 一定不存在，也不是代码导入名写错。

更像是当前环境访问 Python 包源时 SSL 握手失败，导致 pip 没拿到包索引，所以最后显示：

```text
from versions: none
```

### 可尝试方案

1. 换网络或代理后重试。
2. 升级 pip：

```powershell
python -m pip install --upgrade pip -i https://pypi.org/simple
```

3. 换官方 PyPI：

```powershell
python -m pip install PyMuPDF==1.26.3 -i https://pypi.org/simple
```

4. 临时信任镜像主机：

```powershell
python -m pip install PyMuPDF==1.26.3 -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

5. 如果网络环境持续不稳定，可以下载 wheel 文件后本地安装。

### 当前项目兜底

后端代码已经做了清晰报错：

```text
PDF support requires PyMuPDF. Please run pip install -r requirements.txt.
```

也就是说：

- txt/md 上传不受影响。
- PDF 上传需要 PyMuPDF 成功安装后才能使用。

### 2026-06-30 补充排查

在 VPN 使用美国节点时，直接使用官方 PyPI：

```powershell
python -m pip install PyMuPDF==1.26.3
```

仍然出现：

```text
SSLEOFError(8, 'EOF occurred in violation of protocol')
```

使用 trusted-host 后出现过：

```text
ProxyError('Cannot connect to proxy.')
```

这说明问题更可能在：

- pip 使用了无效代理。
- VPN 没有正确接管 Python 进程流量。
- Python / pip / certifi 版本较旧，和当前网络 TLS 链路不兼容。
- 本机安全软件或代理工具拦截了 Python 的 HTTPS 连接。

安全注意：

不要直接打印 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，因为里面可能包含代理账号密码。

可以尝试只在当前命令临时清空代理变量：

```powershell
$env:HTTP_PROXY=''
$env:HTTPS_PROXY=''
$env:ALL_PROXY=''
$env:NO_PROXY=''
python -m pip install PyMuPDF==1.26.3
```

如果仍失败，建议：

1. 在系统终端确认代理工具是否开启了 TUN / 全局模式。
2. 升级 Python 或 pip。
3. 手动从 PyPI 下载对应 wheel 后本地安装。
4. 临时换一个网络环境安装依赖。

## 4. 图片版 PDF 为什么需要 OCR

### 文本型 PDF

文本型 PDF 里本身有文字层。解析工具可以直接提取文字。

当前项目可以使用 PyMuPDF 或 pypdf 处理这种 PDF：

```text
PDF 页面 -> 提取文字层 -> 文本进入 RAG 切块流程
```

### 图片版 PDF

图片版 PDF 通常来自扫描件。页面看起来有字，但底层其实是一张图片。

这种情况下，普通 PDF 文本解析工具拿不到文字，只能得到空文本。

图片版 PDF 需要 OCR：

```text
PDF 页面 -> 渲染成图片 -> OCR 识别图片里的字 -> 文本进入 RAG 切块流程
```

OCR 是 Optical Character Recognition，意思是光学字符识别。

### OCR 方案对比

#### 方案 A：本地 OCR

常见选择：

- Tesseract
- PaddleOCR
- EasyOCR

优点：

- 文件不离开本机。
- 适合企业私有资料。
- 可控性强。

缺点：

- 安装复杂。
- Windows 环境容易遇到依赖问题。
- 中文识别效果需要模型和参数调优。

#### 方案 B：云 OCR / 多模态模型

可以把 PDF 页面图片发给外部 OCR 服务或多模态模型识别。

优点：

- 接入快。
- 识别效果通常更好。
- 不用本地安装复杂图像依赖。

缺点：

- 文件会上传到外部服务。
- 有隐私和合规风险。
- 有调用成本。
- 大文件处理要做分页和限流。

#### 方案 C：MCP 工具

MCP 本身不是 OCR 引擎，它只是让 AI/Agent 可以调用外部工具的协议。

也就是说：

```text
MCP 不能凭空完成 OCR。
MCP 可以包装一个 OCR 工具，让 Agent 调用它。
```

例如未来可以做一个 MCP tool：

```text
tool: parse_pdf_with_ocr
input: pdf_path
output: extracted_text
```

这个 tool 背后仍然需要调用：

- 本地 OCR
- 云 OCR
- 多模态模型

### 本项目建议路线

当前阶段建议：

```text
先支持文本型 PDF，不急着做 OCR。
```

原因：

- 当前项目重点是 RAG 工作流，不是文档识别系统。
- OCR 依赖复杂，容易拖慢主线。
- 先把上传、检索、回答、来源、前端闭环打磨好，收益更高。

后续可升级为：

```text
Document Parser 抽象层
  -> txt/md parser
  -> text pdf parser
  -> scanned pdf OCR parser
```

再进一步可以把 OCR parser 封装成 MCP 工具，供 Agentic RAG 阶段调用。

### 中文 PDF 适配记录

2026-06-30 已生成中文 PDF 测试样本：

```text
docs/sample-project-delay-cn.pdf
```

生成时使用系统中文字体：

```text
C:\Windows\Fonts\NotoSansSC-VF.ttf
```

当前已做适配：

- 使用 Unicode NFKC 规范化，减少中文兼容区字符问题。
- 清洗 PDF 抽取文本中的异常换行。
- 对常见中文字段增加边界识别：
  - 客户
  - 项目
  - 原计划交付日期
  - 调整后交付日期
  - 项目负责人
  - 延期原因
  - 合同风险
  - 建议动作
- local 模式可以从中文 PDF 中抽取延期原因和补充信息。

注意：

- 这解决的是“有文字层的中文 PDF”。
- 扫描版中文 PDF 仍然需要 OCR。

## 5. PyMuPDF 装不上时的替代方案

### 推荐替代：pypdf

PyMuPDF 在 Windows 上通常是 wheel 包安装，但如果 pip 的 TLS/代理链路有问题，就会卡住。

当前项目已经改成：

```text
优先使用 PyMuPDF
如果 PyMuPDF 不存在，则回退到 pypdf
```

`pypdf` 是纯 Python PDF 解析库，安装通常更轻：

```powershell
cd "D:\multi agents\apps\api"
python -m pip install pypdf==5.9.0
```

或安装全部依赖：

```powershell
python -m pip install -r requirements.txt
```

### pypdf 的优缺点

优点：

- 纯 Python，安装更简单。
- 适合 V1 阶段解析文本型 PDF。
- 不需要额外系统依赖。

缺点：

- 对复杂排版 PDF 的提取效果可能不如 PyMuPDF。
- 不能处理扫描版 PDF。
- 表格结构、页眉页脚等可能不够理想。

### 当前项目建议

当前阶段先使用：

```text
pypdf
```

等 RAG 主流程更完整后，再考虑：

- PyMuPDF
- OCR
- 表格解析
- PDF 分页来源定位

### 2026-06-30 安装结果

尝试安装：

```powershell
python -m pip install pypdf==5.9.0
```

仍然出现：

```text
SSLEOFError(8, 'EOF occurred in violation of protocol')
```

这说明当前问题不是 PyMuPDF 单个包的问题，而是本机 pip 到 PyPI 的 HTTPS 连接整体有问题。

在这种情况下，换轻量包也不一定能成功，需要优先解决 pip 网络链路：

- 检查 VPN 是否代理 Python 进程。
- 检查代理环境变量是否配置错误。
- 升级 pip / certifi。
- 手动下载 wheel 后本地安装。

### 2026-06-30 解决结果

关闭 VPN 后，用户成功安装：

```text
PyMuPDF
pypdf
```

随后项目验证通过：

- `pypdf` 可以导入。
- `PyMuPDF` 可以导入。
- 后端语法检查通过。
- 使用 PyMuPDF 生成临时 PDF。
- 使用项目的 `parse_document()` 成功提取 PDF 文本。
- PDF 文本可以写入 SQLite。
- `/chat` 检索可以命中 PDF chunk。

结论：

```text
此前安装失败主要是 VPN/代理链路导致 pip HTTPS 连接异常。
```

## 6. Evidence Check 证据门控设计

### 设计目标

RAG 不能只做到“检索到内容就回答”，还要判断证据是否足够支撑答案。

当前项目在检索和回答之间加入：

```text
question -> query_expansion -> retrieve -> select_sources -> evidence_check -> answer / refuse
```

作用：

- 防止因为少量字面重合就强行回答。
- 防止延期原因、合同风险等问题被错误归因。
- 防止 API 模型基于弱证据生成看起来合理的幻觉。
- 在 trace 中暴露拒答原因，方便排查。

### 判断维度

当前 `evidence_check` 主要看三件事：

1. 最高相关分 `top_score`：最高命中分太低，说明资料和问题弱相关。
2. 强相关来源数量 `related_sources`：至少要有可用证据来源。
3. 意图覆盖率 `intent_coverage`：问题里的关键意图词是否被证据覆盖。

问题类型会影响门槛：

```text
risk    风险/合同类，要求更高：top_score >= 8，intent_coverage >= 40%
causal  原因/延期类，中等要求：top_score >= 6，intent_coverage >= 30%
fact    负责人/日期类，要求稍低：top_score >= 4，intent_coverage >= 20%
general 通用问题，默认要求：top_score >= 6，intent_coverage >= 30%
```

### 拒答逻辑

如果证据不足，系统不继续调用 API 生成，而是直接拒答，并在 trace 里记录原因：

```text
evidence_check: weak_score
evidence_check: not_enough_sources
evidence_check: intent_coverage_low
```

面试表达：

```text
我没有把 RAG 简单做成 top-k 检索后直接回答，而是在回答前加了 Evidence Check。
它会根据问题类型动态调整证据门槛，比如合同风险类问题要求更高，负责人这类事实查询要求稍低。
判断维度包括最高相关分、强相关来源数量和意图覆盖率。
如果证据不足，系统会拒答，并在 trace 中说明原因，避免模型基于弱证据生成幻觉。
```

后续可升级：

- 用 embedding 相似度替代关键词分数。
- 引入 reranker 对来源重排。
- 加入 LLM-as-judge 判断证据是否支持答案。
- 建立人工标注集，评估拒答准确率。
- 按不同业务场景配置不同证据策略。

## 7. Retriever 检索器抽象设计

原来关键词检索直接写在 `rag.py` 里，短期能跑，但后续接 embedding、reranker 或 pgvector 时会让主流程变乱。

现在拆成：

```text
rag.py：负责 query 扩展、来源选择、证据检查和回答生成。
retrievers.py：负责具体怎么检索，当前实现 KeywordRetriever。
```

后续可新增：

```text
EmbeddingRetriever
HybridRetriever = keyword + embedding
RerankRetriever = retrieve + rerank
```

面试表达：

```text
我把检索逻辑从 RAG 主流程中抽成 Retriever 接口。当前先保留 keyword retriever，保证学习版可运行；后续接 embedding 或 pgvector 时，只需要新增检索器实现，而不用重写问答、证据检查和前端展示流程。
```

## 8. Harness 上下文压缩与验证脚本

本项目新增：

```text
docs/context-brief.md
scripts/context-harness.ps1
```

作用：

- `context-brief.md`：压缩版项目上下文，新对话优先读取它。
- `context-harness.ps1 -Mode files`：输出关键文件列表，自动排除 `node_modules`、`dist`、缓存和数据库。
- `context-harness.ps1 -Mode verify`：执行基础 smoke test，确认后端主流程可导入、可调用。
- `context-harness.ps1 -Mode brief`：输出短上下文和关键文件索引。

为什么要做：

```text
把重复的上下文整理、文件索引和基础验证脚本化，减少每次对话重新扫描大目录、重复粘贴长文档和手写验证命令的 token 成本。
```

面试表达：

```text
我给项目加了一个轻量 harness，用脚本固定“读取最小上下文、列出关键文件、运行 smoke test”这几个重复动作。
这样新对话或上下文压缩后，不需要重新解释整个项目，也不会误扫 node_modules、dist、数据库这类大目录。
它本质上是把 AI 协作过程工程化，提升可复现性，同时降低 token 消耗。
```

## 9. 本地 Embedding 学习版

当前新增 `apps/api/app/embeddings.py`，用本地哈希向量模拟 embedding，并把向量以 JSON 文本存到 SQLite 的 `chunks.embedding` 字段。

它的目的不是替代真实 embedding 模型，而是先打通数据流：

```text
chunk -> build_embedding -> 存库 -> query embedding -> cosine similarity -> source ranking
```

检索模式：

```text
keyword   关键词检索，默认稳定模式
embedding 本地向量检索，学习语义检索流程
hybrid    keyword + embedding 混合检索
```

面试表达：

```text
我先做了一个本地 embedding 学习版，不依赖外部模型，把 chunk 向量化、存入 SQLite，并支持 cosine similarity 检索。
这个版本的重点是验证向量检索的数据流和接口抽象；后续可以把哈希向量替换成真实 embedding API，再把 SQLite 升级为 PostgreSQL + pgvector。
```

### 2026-07-01 补充：Embedding 可观察性

新增：

```text
GET  /embeddings/status
POST /embeddings/rebuild
```

作用：

- 查看总 chunk 数、已生成 embedding 数、缺失数和覆盖率。
- 对历史 chunk 一键重建 embedding。
- 前端左侧新增“向量状态”面板，便于验证 embedding 是否真的入库。

面试表达：

```text
我没有只做一个黑盒 embedding 检索，而是补了状态查询和重建接口。
这样可以看到向量覆盖率，也能对历史数据补建 embedding，方便排查“为什么 embedding 检索没命中”的问题。
这属于 RAG 系统的可观察性和运维能力。
```

## 10. V1 收口：系统状态与前端交互

新增：

```text
GET /system/status
```

前端新增状态面板，展示：

- API 是否可用。
- 文档数和 chunk 数。
- LLM provider 和是否已配置 key。
- embedding 覆盖率。

同时补齐：

- 上传、删除、重建向量后自动刷新工作台状态。
- 复制回答。
- 清空回答。
- 关闭错误提示。

面试表达：

```text
我把 V1 从“功能能跑”补成“可验收工作台”：除了上传、检索和回答，还加入了系统状态接口和前端状态面板。
这样演示时可以直接看到 API、文档、chunk、LLM 和 embedding 的状态；交互上也补齐了复制回答、清空回答、错误关闭和状态刷新。
这体现的是产品闭环和工程可验收性，而不是只堆后端接口。
```

## 11. V2 Agentic RAG 状态机设计

当前工作流：

```text
question
-> Router 分类
-> Planner 改写/拆解 query
-> Retriever 第一轮
-> Evidence 评分
-> 必要时改写并第二轮
-> Answer 生成
-> Reviewer 引用审核
-> answer / refuse
```

核心策略：

- 简单且证据充分的问题只检索一轮。
- 复杂问题或弱证据最多检索两轮，防止无边界循环。
- Evidence Check 同时检查相关分、意图覆盖率和主题锚点。
- 即使向量分高，核心主题完全不在来源中，也以 `topic_mismatch` 拒答。
- Reviewer 在返回前检查 `[来源 N]`，缺失时自动补全标准引用。
- `AgentSummary` 返回分类、复杂度、轮次、query、证据、引用和参与节点。

为什么没有直接引入 LangGraph：

```text
当前阶段先用显式 Python 状态机把节点输入、输出和流转条件写清楚，减少新手同时处理框架和业务逻辑的认知负担。
节点边界已经按图工作流设计，后续迁移 LangGraph 时主要替换编排层，不需要重写检索和证据策略。
```

面试表达：

```text
我把固定单轮 RAG 升级成了有状态的 Agentic RAG。Router 先分类，Planner 改写和拆解 query，Retriever 根据复杂度和证据质量决定是否重查，Evidence Agent 做动态门控，Reviewer 在最终返回前审核引用。
真实回归中我发现本地哈希 embedding 会让无关问题获得虚高分，因此又加入主题锚点检查：向量分够但问题核心词在证据中没有落点时仍然拒答。这个规则修复了“火星氧气方案”错误命中项目延期文档的问题。
```

自动化验收覆盖：

- 默认进入 agentic 工作流。
- 分类和 query 改写。
- 简单问题一轮检索。
- 复杂问题两轮检索。
- 无来源拒答。
- 高分但主题不匹配拒答。
- 引用缺失自动修复。
- `/health`、`/system/status` 和 `/chat` API 契约。
- standard 工作流向后兼容。

### 2026-07-21 交互收口

- 上传完成后同时清空 React 状态和原生 file input，允许再次选择同一个文件。
- 切换回答、工作流或检索模式时清空旧结果，避免旧答案看起来属于新模式。
- 未选择文件时禁用上传按钮，问题为空时禁用提问按钮。
- FastAPI 和 Vite 运行态 HTTP 检查通过，日志中没有 500、Traceback 或前端构建错误。

## 12. V2 工程指标、优化路线与面试总结

### 为什么要做指标

功能测试只能回答“这几个例子能不能跑通”，工程指标要回答：

```text
系统快不快、稳不稳、会不会乱答、成本会不会失控，以及优化后有没有真的变好。
```

当前新增：

```text
SQLite 表：chat_metrics
API：GET /metrics/summary
评测：python scripts/evaluate_v2.py
前端：工程指标面板
```

为保护隐私，`chat_metrics` 只记录模式、意图、轮次、状态、耗时等元数据，不保存用户原问题。

### 指标怎么理解

| 指标 | 新手理解 | 工程意义 |
| --- | --- | --- |
| Error Rate | 请求报错比例 | 判断系统稳定性，目标通常越低越好 |
| P95 Latency | 95% 请求都比这个时间快 | 比平均值更容易发现少量特别慢的请求 |
| Avg Retrieval Rounds | 平均查几轮资料 | 太高可能浪费延迟和 token，太低可能证据不足 |
| Evidence Pass Rate | 证据门控通过比例 | 不能盲目追高，要结合误答和拒答准确率判断 |
| Citation Ready Rate | 回答是否带可追溯引用 | 企业知识问答应接近 100% |
| Answer / Refusal Rate | 实际流量中回答和拒答的占比 | 这是流量分布，不等于回答准确率 |
| Answer/Refusal Accuracy | 该回答时回答、该拒答时拒答 | 需要人工标注评测集，是核心质量指标 |
| Intent Accuracy | 问题分类是否正确 | 分类错了会让后续 query 和门控策略全走偏 |

特别注意：

```text
拒答率 25% 不代表系统只有 75% 准确率。
如果评测集故意放了 1 个无关问题，4 个请求中正确拒答 1 个，拒答率自然就是 25%。
真正衡量质量的是“答/拒决策准确率”。
```

### 当前工程基线

基于当前 1 份中文项目 PDF 和 4 个固定问题：

```text
意图分类准确率：100%
答/拒决策准确率：100%
检索轮次符合预期：100%
引用覆盖率：100%
平均检索轮数：1.50
本地规则模式平均延迟：约 4-6 ms
本地规则模式 P95：约 5-10 ms
自动化测试：12 个通过
```

质量门槛：

```text
意图准确率 >= 90%
答/拒准确率 >= 90%
轮次符合率 >= 90%
引用覆盖率 = 100%
本地 P95 <= 100 ms
```

这组数据只能证明当前学习版闭环和评测工具有效，不能宣称生产准确率。原因是样本只有 4 个、知识库只有 1 份文档，而且没有计算外部大模型网络延迟。

### 指标异常时怎么优化

| 现象 | 常见原因 | 优化方向 |
| --- | --- | --- |
| P95 很高 | API 慢、检索串行、上下文过长 | 并行检索、缓存、超时、减少 query 和来源、流式输出 |
| 平均轮数接近 2 | 第一轮 query 质量差、门槛过严 | 优化分类和改写，增加 reranker，按意图校准阈值 |
| 误答多但拒答率低 | 门槛过松、embedding 虚高 | 主题锚点、reranker、LLM judge、提高高风险问题阈值 |
| 拒答很多 | 文档缺失、切块差、门槛过严 | 补知识库、按标题/段落切块、混合检索、降低合理阈值 |
| 引用率低 | 模型不遵循格式、Reviewer 缺失 | 结构化输出、引用校验、返回前自动修复 |
| 错误率高 | 外部 API、依赖、超时或数据库问题 | 重试、熔断、降级 local、日志和告警 |
| token 成本高 | query 太多、来源太长、频繁二次检索 | query 去重、上下文压缩、缓存、小模型路由、限制轮次 |

### 优化优先级

第一优先级：扩大评测集。

```text
先整理 50-100 个真实问题，标注意图、是否可回答、期望来源和风险级别。
没有稳定评测集，调整阈值只能靠感觉。
```

第二优先级：升级检索质量。

```text
本地哈希 embedding -> 真实中文 embedding（如 BGE 系列）
SQLite 全表扫描 -> PostgreSQL + pgvector
top-k 直接使用 -> 召回后增加 reranker
```

第三优先级：完善线上可观察性。

```text
记录真实模型 token usage、费用、超时和降级次数；按 standard/agentic、local/api 分开统计延迟。
```

第四优先级：生产可靠性。

```text
身份认证、租户/文档权限、敏感数据脱敏、请求限流、API 重试与熔断、数据库备份。
```

### 面试常见问题

问题：为什么需要 Agentic RAG，普通 RAG 不够吗？

```text
普通 RAG 固定检索一次，适合简单问题；复杂问题可能同时涉及延期原因、合同风险和负责人，一次 query 很难覆盖。
我让 Router 和 Planner 先分类、改写和拆解，Evidence Agent 再决定是否重查，同时把上限固定为两轮，避免 Agent 无限循环和成本失控。
```

问题：你怎么证明系统变好了？

```text
我同时看离线质量和线上运行指标。离线评测关注意图准确率、答拒准确率、引用覆盖率；线上关注错误率、P95、平均轮数和使用分布。
每次修改检索和门控规则后都跑同一套评测，并设置质量门槛，防止某个案例变好但整体退化。
```

问题：项目中遇到过什么真实问题？

```text
本地哈希 embedding 曾把“火星氧气方案”和项目延期文档算成较高相似度，原 Evidence Check 只看分数所以错误放行。
我增加了主题锚点检查：向量分达到门槛，但问题核心主题在证据中完全没有落点时，仍然以 topic_mismatch 拒答，并补了回归测试。
```

问题：当前数据 100% 是否说明效果很好？

```text
不能。当前只有 4 个固定问题和 1 份文档，100% 只代表这套学习版评测通过，不代表生产准确率。
真正上线前要扩展人工标注集、分业务场景统计，并持续回放失败案例。这种诚实区分 demo 指标和生产指标，本身就是工程判断力。
```

问题：为什么不用完整 LangGraph？

```text
当前先用显式 Python 状态机把节点输入输出、重试条件和状态字段写清楚，减少框架遮蔽业务逻辑。
节点边界已经按图工作流设计，后续迁移 LangGraph 主要替换编排层，Retriever、Evidence 和 Reviewer 可以继续复用。
```

### 一分钟项目表达

```text
我做了一个企业知识助手，V1 完成文档上传、切块、持久化、混合检索、来源引用和 DeepSeek API；V2 把固定 RAG 升级为 Agentic RAG，由 Router、Planner、Retriever、Evidence、Answer、Reviewer 六个节点协作。
系统会根据问题复杂度决定查一轮还是两轮，并通过分数、意图覆盖和主题锚点做证据门控，证据不足就拒答，返回前再检查引用。
工程上我增加了 SQLite 运行指标、P95、错误率、平均轮数和引用率面板，也建立了离线评测和质量门槛。真实调试中修复了 embedding 虚高导致无关问题误答的问题。
当前版本是可运行的学习版，下一步会扩大标注集、接真实中文 embedding 和 reranker，再升级 pgvector、权限和线上 token 成本监控。
```

## 13. V3 受控工具调用、审批闭环与面试总结

### 目标与完整流程

V2 只能“查资料并回答”，V3 要让 AI 能推动业务，但不能让模型直接改数据库：

```text
用户问题 -> Tool Agent 选择工具 -> 参数/角色校验
读工具 -> 立即执行 -> 返回结果 + 审计
写工具 -> 生成草稿 -> 人工批准/拒绝
批准 -> 原子抢占执行权 -> 写库 -> 成功/失败状态 + 审计指标
```

演示闭环：

```text
“客户 A 为什么延期？请创建跟进工单”
-> V2 检索并通过 Evidence Check
-> create_ticket 只生成 pending 草稿
-> 人工检查标题、描述、优先级和来源
-> 批准后创建 open 工单
-> 状态变更再次走审批，直到 resolved/closed
```

### 五个关键设计

1. **读写分级**：`query_tickets/get_ticket_detail` 可立即执行；`create_ticket/update_ticket_status` 必须审批。风险越高，控制越严格。
2. **统一执行入口**：Agent 不直接调用数据库函数，只能调用 `execute_tool`。这里统一做白名单、参数、权限、审计和异常处理。
3. **幂等与并发**：审批先用条件更新把 `pending` 原子改成 `executing`，只有一个请求能成功；`execution_count` 应始终为 1，重复审批返回已有结果。
4. **失败是最终状态**：执行失败不能显示“已批准成功”，而是 `failed + error_message`；拒绝和过期分别是 `rejected/expired`，都不产生业务写入。
5. **可观测性**：每次工具调用记录工具名、读写类型、是否需审批、角色、输入/结果摘要、状态和端到端耗时。审计内容限制长度，避免日志无限膨胀。

状态机：

```text
pending --批准--> executing --成功--> succeeded
                         \--失败--> failed
pending --拒绝--------------------> rejected
pending --超时--------------------> expired
```

### 为什么直接工单查询要跳过 RAG

“有哪些工单”答案来自业务数据库，不来自知识文档。若仍先做 embedding 检索，不但浪费延迟和 token，还可能因为证据不足错误拒答。因此 Tool Agent 将直接查询/状态更新标记为 `evidence_status=not_required`，检索轮数为 0；只有“根据资料分析延期并建单”才先走 RAG 和证据门控。

### 指标与当前门槛

| 指标 | 含义 | 当前门槛 |
| --- | --- | --- |
| Safety Checks | 审批前零写入、批准、重复、拒绝、过期、校验、权限 | 100% |
| Exact-once Violations | `execution_count > 1` 的额外次数 | 0 |
| Tool P95 | 95% 已完成工具调用的端到端耗时 | <= 200 ms |
| Success Rate | `succeeded / (succeeded + failed)` | 看真实流量趋势 |
| Approval Rate | 已批准 /（已批准 + 已拒绝） | 业务分布，不是越高越好 |

一次真实调试中，评测脚本曾把“整套评测初始化耗时”当成“单次工具 P95”，7 项安全检查全通过却错误触发红灯。修复方式是从 `tool_call_logs` 的单次调用耗时计算 P95，整套脚本耗时单独展示。这说明指标必须先定义统计对象和分母，否则数字精确也可能结论错误。

当前学习版基线：18 个自动化测试通过；V3 7 项安全检查 100%；重复执行违规 0；本机 SQLite 工具 P95 通常为几十毫秒内。样本小，只证明闭环和门禁有效，不代表生产 SLA。

### 面试怎么回答

**为什么不能让 Agent 直接调用写接口？**

```text
模型输出不稳定，也可能受提示注入影响。我把模型限制在“提出结构化操作草稿”，真正写入由确定性工具层校验，并要求人工审批。这样模型负责判断，人负责高风险决策，系统负责执行和留痕。
```

**如何保证重复点击不会创建两张工单？**

```text
审批时用数据库条件更新实现原子 claim：只有 pending 才能变成 executing。第一个请求获得执行权，后续请求只能读取 succeeded/failed 的既有结果。自动化测试会连续批准两次并断言工单数仍为 1、execution_count 为 1。
```

**权限做完整了吗？**

```text
学习版实现了 viewer/operator/admin 的工具级角色门控，能展示最小权限思想；但 X-User-Role 请求头可由客户端伪造，不等于真实认证。生产版要接 OIDC/JWT，在服务端从可信 token 解析用户、租户和角色，并做资源级授权。
```

**还要怎么生产化？**

```text
将 SQLite 换成 PostgreSQL；审批执行放入持久化任务队列；为 executing 状态增加超时恢复；接真实身份与租户隔离；敏感字段脱敏；对外部工具增加超时、重试、熔断和补偿事务；再用线上告警监控失败率、P95 和积压量。
```

一分钟表达：

```text
V3 把知识助手升级成受控业务执行助手。我实现了四个注册工具，并按风险把读操作立即执行、写操作转成 15 分钟审批草稿。审批使用原子状态迁移和 execution_count 防止重复执行，参数白名单、角色门控和完整审计用于控制风险。前端能查看草稿、批准或拒绝、推动工单状态流转，并展示成功率、P95 和重复执行违规。工程验证覆盖审批前零写入、重复批准、拒绝、过期、越权、非法参数和执行失败，而不是只测正常路径。
```
