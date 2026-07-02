# 视频内容理解平台 — 功能与面试要点总结

> 本文档是项目的**权威能力清单 + 面试讲解稿**。功能描述与当前代码保持一致(截至 2026-07-02)。
> 相关文档:`README.md`(快速上手)、`CLAUDE.md`/`AGENTS.md`(给 AI 的项目规则)、`docs/TROUBLESHOOTING.md`(排障历史)、`docs/DEMO_SCRIPT.md`(演示脚本)。

---

## 一、平台能做什么(功能清单)

| 功能 | 实现方式 | 关键类/文件 |
|---|---|---|
| 多用户 + JWT 鉴权 | 注册/登录签发 JWT,过滤器校验;用户持久化 | `auth/`(JwtService, JwtAuthenticationFilter, AuthService) |
| 单文件上传 | 直接落盘,建任务,发布处理 | `SingleUploadService` |
| **分片上传** | init/chunk/merge 三段;Redis 管理会话与分片集合;合并加分布式锁 | `MediaController`, `ChunkUploadService` |
| **断点续传** | 已传分片索引查询 + 前端 localStorage 记忆 + 按 MD5 复用未完成会话 | `/api/media/upload/status`, `ChunkUploadService.tryResume` |
| **秒传** | 文件 MD5 命中已处理内容 → 直接建任务 | `ChunkUploadService.initUpload`(FILE_MD5_KEY) |
| **完整性校验** | 合并后算整文件 MD5 与前端上传值比对,不一致清理报错 | `ChunkUploadService.computeMd5` |
| **内容级去重** | 按 MD5 寻址的 `MediaAsset`,相同内容只转写/摘要一次并 fan-out | `MediaAsset`, `MediaAssetService`, `WorkflowProcessor` |
| **异步处理** | 本地 `@Async` 或 RocketMQ 解耦;发布器抽象 | `WorkflowPublisher`(Local/RocketMq), `AsyncConfig` |
| **分布式锁** | Redisson(看门狗)/ Redis 兜底 / 本地 三实现,条件装配 | `DistributedLockService` 及三实现 |
| **幂等消费** | 乐观状态占位,抵御 MQ 重复投递 | `VideoTaskService.claimForProcessing` |
| 音频提取/转写/摘要 | FFmpeg 抽音轨 → Whisper HTTP → LLM HTTP;各有 Mock 兜底 | `transcript/`, `summary/` |
| 视频流式播放 | HTTP Range 分段 + 短时效签名播放令牌 | `VideoPlaybackController` |
| 任务查询/管理 | owner 过滤的任务列表/详情/删除 | `WorkflowController` |
| 三种部署模式 | `@ConditionalOnProperty` 按 `app.redis.enabled`/`app.mq.enabled` 装配 | 全局 |

---

## 二、两条核心链路

### 上传链路
```
计算文件 MD5(前端 SparkMD5 分块增量)
  → POST /init   (Redis 建会话;MD5 命中→秒传;命中未完成会话→断点续传)
  → POST /chunk × N (并发上传;跳过已传分片;落盘 + Redis 记录分片集合)
  → POST /merge  (分布式锁防重复;按序合并;整文件 MD5 校验;建 VideoTask)
  → WorkflowPublisher.publish(taskId)  ← 接口到此立即返回
```

### 处理链路(`WorkflowProcessor.processAsync`)
```
1. 去重命中?  MediaAsset READY → 直接复用结果,秒完成(不跑 FFmpeg/Whisper/LLM)
2. 幂等占位   claimForProcessing:仅 QUEUED→TRANSCRIBING 成功者继续(挡 MQ 重复投递)
3. 无 MD5     → standalone:抽音轨 → 转写 → 摘要(每阶段一个短事务)
4. 单飞处理   tryLockWithWatchdog(lock:asset:{md5}):
                 赢家 → markProcessing → 转写 → 摘要 → markReady → fan-out 完成所有同内容任务
                 输家 → 直接返回,由赢家 fan-out 完成(不重复处理、不占线程)
```

---

## 三、面试要点(重点)

### 1. MD5 内容指纹:秒传 / 去重 / 完整性校验
- **MD5 是什么**:把任意长度输入映射为定长 128 位指纹。同内容同指纹、雪崩效应、不可逆、快。密码学抗碰撞已被攻破 → **不用于安全签名**,但用于**去重和防意外损坏校验完全够用**。
- **三个用途**:
  - **秒传**:上传前算 MD5,命中已有内容直接建任务,省上传带宽。
  - **内容级去重**:更大的价值——命中已处理内容直接复用转写+摘要,**省掉分钟级的 FFmpeg/Whisper/LLM**。
  - **完整性校验**:合并后算整文件 MD5 比对,防分片丢失/乱序导致的静默损坏。
- **前端如何算**:SparkMD5 分块增量(每 2MB 一块),分块间让出事件循环避免卡 UI;CDN 缺失时优雅降级为空串(功能休眠但上传不受影响)。
- **追问「MD5 会碰撞怎么办」**:去重场景可叠加文件大小/二次校验;安全敏感场景改用 SHA-256。本项目定位下 MD5 的碰撞风险可接受。

### 2. 分布式锁:Redisson 看门狗 vs 固定 TTL(最强点)
- **问题**:固定 TTL 的分布式锁遇到**分钟级长任务**(视频转码/转写),锁会在处理途中过期 → 另一个 worker 以为无人处理 → **重复执行昂贵任务**。
- **看门狗机制**:Redisson 获取锁时**不传 leaseTime**,会启动后台线程,只要持有者进程存活,每约 10 秒把锁续期一次(默认续到 30s)。锁因此能安全横跨整个长处理。
- **本项目的取舍**:
  - `merge` 用 `tryLock(key, 30s)` —— **故意传 leaseTime 关掉看门狗**,因为合并是秒级操作,固定租约足够且语义和 Redis 兜底实现对齐。
  - 内容单飞用 `tryLockWithWatchdog(lock:asset:{md5})` —— **不传 leaseTime 开看门狗**,因为要横跨分钟级处理。
  - `waitTime=0` 非阻塞:抢不到立即返回,输家交给赢家 fan-out,**不阻塞线程**(避免消费线程被长时间占用拖垮吞吐)。
- **三实现条件装配**:Redisson(redis 启用且有 RedissonClient)、Redis 兜底(setIfAbsent+TTL+Lua 释放,无看门狗→长租约)、本地(JVM ReentrantLock,无过期)。
- **锁误释放防护**:Redis 兜底用 Lua 脚本"比对持有者标识再删",避免删掉别人的锁;Redisson `isHeldByCurrentThread` 判断。

### 3. MQ 异步:如何"大大降低响应时间"
- **同步痛点**:若上传接口内联跑完 FFmpeg+转写+摘要,用户要等**几分钟**才拿到响应,且长时间占用请求线程和 DB 连接,高并发下线程池/连接池被打满。
- **异步方案**:merge 建完任务只发一条 MQ 消息就返回 → **接口 RT 从分钟级降到毫秒级**;重活由消费者在后台线程池跑,前端轮询任务状态获取进度。
- **RocketMQ 的解耦价值**:生产者/消费者分离 → 可**独立横向扩容消费者**;削峰(上传洪峰进队列,消费者按能力消费);消费失败可重试。
- **两种模式对比**(可作为压测论据):本地 `@Async`(单机线程池)vs RocketMQ(跨节点解耦);`app.mq.enabled` 一个开关切换。
- **量化验证思路(下一步)**:埋点区分"接口响应时间"和"端到端处理时间",用 k6/JMeter 压测对比开关两态的 P50/P99/吞吐/队列堆积。

### 4. 分片上传 + 断点续传
- **为什么分片**:大文件单请求易超时/失败重传代价高;分片可**并发上传**(前端 4 并发)、失败只重传单片、支持断点续传。
- **Redis 管理会话**:`upload:{id}:meta`(哈希:文件名/大小/分片数/owner)+ `upload:{id}:chunks`(集合:已传索引),均设 24h TTL 防泄漏。
- **断点续传两条路径**:① 前端 localStorage 按"文件名+大小+修改时间"记 uploadId,续传前调 `/status` 确认;② 后端按 MD5 复用未完成会话(`upload:inprogress:{md5}`),跨设备/浏览器也能续。
- **owner 校验无处不在**:每次 chunk/merge/status 都校验会话归属,防越权。

### 5. 幂等消费
- **问题**:MQ 至少一次投递 → 同一消息可能被消费多次。
- **方案**:`UPDATE video_task SET status=TRANSCRIBING WHERE taskId=? AND status=QUEUED` 语义的**乐观占位**,只有把状态从 QUEUED 原子推进的那个 worker 继续,重复投递返回 false 直接跳过。
- 与单飞锁互补:锁保证"同内容只处理一次",占位保证"同任务只处理一次"。

### 6. 事务边界设计(容易被追问的细节)
- 处理器**不加大事务**:转写+摘要涉及 FFmpeg 和两次 HTTP,耗时分钟级;大事务会在整个外部 I/O 期间独占一条 DB 连接 → 高并发耗尽连接池,且中间状态在提交前对前端轮询不可见。
- 改为**每阶段一个短事务**(`updateStatus`/`completeTranscript`/`completeSummary`/`markFailed`),各自独立提交 → 前端能看到 TRANSCRIBING/SUMMARIZING 进度,连接占用短。
- 跨阶段多次提交是**刻意设计**;但同一方法内多次 `save()` 同一实体仍是坏味道。

### 7. 内容寻址 MediaAsset + 单飞 fan-out
- **思路**:把"昂贵结果"(转写/摘要)与"用户任务"解耦到按 MD5 寻址的 `MediaAsset`;N 个用户传同一视频只处理一次,结果共享。
- **fan-out**:赢家处理完 `completeAllByContentMd5` 一次性完成所有同内容任务(含因抢锁失败而等待的),输家零成本复用,无需重试或轮询。

### 8. 视频流式播放(Range + 签名令牌)
- **HTTP Range**:支持 `bytes=start-end`,可拖动进度条、边下边播,返回 206 Partial Content。
- **鉴权难点**:`<video>` 标签无法带 Authorization 头 → 用**短时效签名令牌**作查询参数,端点自校验(purpose/taskId/owner),该路径在 SecurityConfig 放行。这与 CDN 预签名 URL 同构,为后续对象存储迁移铺路。

### 9. 健壮性细节(体现工程素养)
- **资源清理**:FFmpeg 临时文件在所有异常/超时路径 `deleteIfExists`;合并失败清理半成品文件。
- **错误信息截断**:`errorMessage` 用 TEXT 列,处理器截断到 2000 字符防日志膨胀。
- **空转写友好降级**:无语音的视频返回友好摘要而非报错。
- **文件名安全**:`MediaFileValidator.safeVideoFileName` 防路径穿越。

---

## 四、诚实的已知不足 / 下一步(加分项)

- **单飞崩溃恢复缺口**:单飞赢家中途崩溃时,抢锁失败的任务会卡在 TRANSCRIBING。修法:**定时 reaper 扫描超时的非终态任务重投**。
- **MQ 消费与 @Async 的关系**:RocketMQ 消费者内部又调 `@Async`,消息会在处理真正完成前被 ACK;更严谨可去掉内部 @Async、由消费线程同步处理并按结果 ACK/NACK。
- **可观测性**:尚无 Micrometer/Prometheus 指标,压测对比数据待补(P2)。
- **对象存储**:当前本地磁盘,公网多用户需迁移 MinIO/OSS/S3 + 前端直传(P4)。
- **公网部署**:应用 Dockerfile、Nginx 反代/HTTPS、密钥外部化待做(P5)。

---

## 五、一句话电梯陈述

> 这不是简单 CRUD,而是围绕"大文件传输慢、高并发上传易拖垮服务、AI 处理耗时长"三个真实瓶颈做架构:上传链路用 **Redis 分片会话 + MD5 秒传/去重/校验 + 断点续传 + 分布式锁**保证可靠;处理链路用 **RocketMQ 异步解耦**把接口响应从分钟级降到毫秒级,用**内容寻址去重 + Redisson 看门狗单飞 + 幂等消费**保证"同内容只处理一次、同任务不重复处理"。
