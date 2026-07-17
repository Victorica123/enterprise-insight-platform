# P4 对象存储：大文件生产化存储与播放

## 为什么要做 P4

本地磁盘适合开发，但不适合真实用户：

- 多人上传后磁盘容易满。
- 多实例部署时，每台机器看到的文件不同。
- 视频播放会占用应用服务器带宽。
- 备份、扩容、迁移都麻烦。

P4 的目标不是立刻上云，而是先把存储边界抽出来，让系统可以从 `local` 平滑切到 MinIO / OSS / S3。

## 本轮做了什么

- 新增 `MediaStorageService` 存储抽象。
- 默认 `LocalMediaStorageService` 保持原本本地磁盘行为。
- 新增 `S3MediaStorageService`，使用 S3/MinIO 兼容协议：
  - 上传后保存为 `s3://bucket/key`。
  - 后台转写前下载到临时文件，处理后自动清理。
  - 播放时返回 `307 Temporary Redirect` 到预签名 URL，让对象存储承担 Range 播放流量。
- 新增浏览器直传后端入口：
  - `POST /api/media/upload/direct/init`：后端校验文件名，生成 S3/MinIO 预签名 PUT URL。
  - `POST /api/media/upload/direct/complete`：后端校验直传 token、确认对象存在，再创建 `VideoTask` 并发布工作流。
  - 直传 token 绑定 owner、fileName、storagePath，避免用户拿别人的对象路径创建任务。
  - 重复调用 `complete` 会返回同一 storagePath 已有任务，避免用户刷新/重试时重复创建任务。
- 前端上传模式已接入“对象存储直传”：`init / PUT / complete`，PUT 使用 XHR 以展示上传进度。
- 新增 `docker-compose` 的 `object-storage` profile，方便本地起 MinIO。
  - MinIO 已配置 `MINIO_API_CORS_ALLOW_ORIGIN=http://localhost:8081,http://127.0.0.1:8081`，允许浏览器从本地页面直传 PUT。

## 怎么验证 MinIO 路径

### 1. 启动 MinIO

```powershell
docker compose --profile object-storage up -d minio minio-init
```

控制台：

- API: `http://localhost:19000`
- Console: `http://localhost:19001`
- 用户名：`minioadmin`
- 密码：`minioadmin123`

### 2. 用对象存储模式启动应用

如果你只想验证存储，不想开 Redis/MQ/外部 AI：

```powershell
$env:APP_STORAGE_TYPE="s3"
$env:APP_STORAGE_S3_ENDPOINT="http://localhost:19000"
$env:APP_STORAGE_S3_BUCKET="video-platform"
$env:APP_STORAGE_S3_ACCESS_KEY="minioadmin"
$env:APP_STORAGE_S3_SECRET_KEY="minioadmin123"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
mvn spring-boot:run -Dspring-boot.run.profiles=h2
```

### 3. 页面上传验证

1. 打开 `http://localhost:8081`。
2. 注册/登录。
3. 上传一个 mp4。
4. 打开 MinIO Console，进入 `video-platform/uploads/`，应该看到上传的视频对象。
5. 查看任务的 `storagePath`，应该是 `s3://video-platform/uploads/...`。
6. 请求播放 token 后访问 stream URL，应用会返回 `307` 到 MinIO 预签名 URL。

### 4. 页面直传验证

1. 按上面的方式启动 MinIO 和应用。
2. 打开 `http://localhost:8081` 并登录。
3. 上传策略选择“对象存储直传”。
4. 选择视频并上传。
5. 前端进度条会显示“申请直传地址 → 直传对象存储 → 确认直传结果”。
6. MinIO Console 的 `video-platform/uploads/direct/` 下应出现对象。
7. 任务列表出现新任务，状态进入 `QUEUED` 或后续处理状态。

### 5. 直传 API 验证

直传链路分三步：

1. 登录后请求后端签发上传地址。
2. 浏览器用返回的 `uploadUrl` 直接 `PUT` 到 MinIO。
3. 上传完成后调用 `complete`，后端确认对象存在并创建任务。

示例流程（需要先拿到登录 token）：

```powershell
$headers = @{ Authorization = "Bearer <你的登录JWT>" }

$init = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8081/api/media/upload/direct/init `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"fileName":"demo.mp4","fileSize":1024}'

Invoke-RestMethod `
  -Method Put `
  -Uri $init.data.uploadUrl `
  -ContentType "video/mp4" `
  -InFile .\demo.mp4

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8081/api/media/upload/direct/complete `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ uploadToken = $init.data.uploadToken } | ConvertTo-Json)
```

验证点：

- 应用服务器没有接收视频文件正文，只签发短期 URL。
- MinIO 的 `uploads/direct/` 下能看到对象。
- `complete` 返回 `taskId`，任务进入 `QUEUED`。
- 如果没有先 PUT 文件就调用 `complete`，后端会返回“对象存储尚未收到该视频文件”。

## 这对高并发有什么帮助

对象存储不是让转写更快，它解决的是另一类瓶颈：

- 上传和播放流量从应用服务器迁出，减少应用带宽压力。
- 多实例部署时，所有应用实例都访问同一份对象。
- 对象存储天然支持大文件、Range、生命周期管理。
- 现在已经具备“前端直传对象存储 + 后端接收完成确认/元数据”的完整页面入口。

## 面试怎么讲

> 一开始我用本地磁盘降低开发复杂度。到要上线和支持多人上传时，本地磁盘会成为瓶颈：磁盘容量、带宽、多实例一致性、备份都不好处理。所以我抽象了 `MediaStorageService`，默认本地存储，生产可以切到 S3/MinIO。播放时用预签名 URL 让对象存储直接承接 Range 请求；上传也提供了直传入口，后端只签发短期 PUT URL 和完成确认，视频正文不再经过应用服务器。

## 后续可继续做

- 直传上传会话表：记录 token、storagePath、fileSize、状态、过期时间，支持更完整的审计和清理。
- 对象生命周期清理：临时分片、失败任务文件、过期视频。
- 上传限流：按用户/IP 限制并发任务数和总容量。
- 存储指标：对象上传耗时、下载耗时、失败率、磁盘/桶容量。
