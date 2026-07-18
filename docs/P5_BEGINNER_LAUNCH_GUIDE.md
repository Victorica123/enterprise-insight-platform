# 小范围上线新手指引

> **状态：可选能力。** 当前主线是本地可复现的完整业务与工程实验，不需要购买服务器或域名。只有你重新决定做公网试用时，才按本指引执行。

这份指引只解决一个目标：让少量真实用户通过 HTTPS 打开平台、上传视频、看到任务结果，并且出问题时知道先查哪里。

不要一次打开真实转写、真实总结、监控、压测和所有外部服务。第一次上线先用 Mock 跑通业务闭环，再逐项打开真实能力。

## 当前进度

项目侧已经具备：

- 生产 Docker 镜像和 `docker-compose.prod.yml`；
- MySQL、Redis、RocketMQ、MinIO；
- Caddy 自动 HTTPS 和域名反向代理；
- 容器日志轮转、应用健康检查；
- 上线前体检脚本和部署后业务链路验证脚本；
- Prometheus/Grafana 可选监控。
- GitHub 私有仓库 `Victorica123/video-platform` 和可部署的 `main` 分支。

当前还没有完成：

- 云服务器、域名和 DNS 还需要你购买或提供；
- 真实 Whisper/LLM API 暂不建议在第一次部署时打开。

## 你要准备的东西

1. 一个代码托管仓库，建议 GitHub 或 Gitee 私有仓库。
2. 一台 Linux 云服务器，建议 Ubuntu 22.04/24.04、4 核 8 GB、100 GB 磁盘。
3. 一个域名，并准备两个子域名：
   - `video.你的域名`：平台网页和 API；
   - `files.你的域名`：MinIO 视频直传。
4. 云服务器安全组只开放：
   - `22/TCP`：SSH；
   - `80/TCP`：Caddy 申请 HTTPS 证书；
   - `443/TCP` 和 `443/UDP`：HTTPS/HTTP3。

不要开放 MySQL 3306、Redis 6379、RocketMQ 9876/10911、MinIO 9000/9001。

## 第一关：保存并上传当前代码（已完成）

当前私有仓库：

```text
https://github.com/Victorica123/video-platform
```

代码已经经过敏感信息、大文件和提交范围检查，并整理到 `main` 分支。后续服务器直接从该仓库拉取。

```bash
git remote -v
git status
```

能看到远程仓库地址，并且计划上线的代码已经形成明确 commit。

## 第二关：购买服务器并配置 DNS

购买 Ubuntu 服务器后，记录公网 IP。到域名解析控制台添加两条 A 记录：

```text
video.你的域名  -> 服务器公网 IP
files.你的域名  -> 服务器公网 IP
```

在本机终端验证：

```powershell
nslookup video.你的域名
nslookup files.你的域名
```

两个结果都应指向服务器公网 IP。DNS 未生效时不要启动 Caddy，否则自动申请证书会失败。

## 第三关：安装 Docker

用云厂商网页控制台或 SSH 登录服务器：

```bash
ssh root@服务器公网IP
```

优先按照 Docker 官方 Ubuntu 安装文档安装 Docker Engine 和 Compose 插件。安装后验证：

```bash
docker version
docker compose version
```

两条命令都正常输出版本号才继续。

## 第四关：拉取代码并创建配置

服务器执行：

```bash
git clone 你的私有仓库地址 video-platform
cd video-platform
cp .env.example .env
```

编辑 `.env`：

```bash
nano .env
```

至少修改这些值：

```dotenv
PUBLIC_APP_DOMAIN=video.你的域名
PUBLIC_FILES_DOMAIN=files.你的域名
PUBLIC_APP_URL=https://video.你的域名
APP_STORAGE_S3_PUBLIC_ENDPOINT=https://files.你的域名
MINIO_API_CORS_ALLOW_ORIGIN=https://video.你的域名
```

生成随机密钥：

```bash
openssl rand -base64 48
```

每执行一次得到一个新值，分别填入 JWT、MySQL、MinIO 和 Grafana 密钥。不要复用同一个值，也不要把 `.env` 发到聊天或提交到 Git。

第一次上线保持：

```dotenv
APP_TRANSCRIPT_ENABLED=false
APP_SUMMARY_ENABLED=false
```

这表示先用 Mock 验证上传、MQ、数据库、对象存储和页面闭环，不会产生 AI API 费用。

## 第五关：运行上线前体检

如果服务器安装了 PowerShell 7：

```bash
pwsh -File scripts/preflight-deploy.ps1
```

没有 PowerShell 时，至少执行：

```bash
docker compose --env-file .env -f docker-compose.prod.yml config --quiet
```

体检脚本出现 `FAIL` 时不要启动服务；`WARN` 表示已知的非阻断项，例如首次部署使用 Mock AI。

## 第六关：启动平台

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

首次构建会下载镜像和 Maven 依赖，可能需要几分钟。观察日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 app caddy
```

看到应用启动完成、Caddy 成功取得证书后，按 `Ctrl+C` 退出日志，不会停止容器。

验证：

```bash
curl https://video.你的域名/actuator/health
curl -I https://video.你的域名/
curl -I https://files.你的域名/minio/health/live
```

预期：health 返回 `UP`，网页返回 200，MinIO health 返回 200。

## 第七关：从你的电脑验证完整业务

在 Windows 项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-deploy.ps1 `
  -BaseUrl "https://video.你的域名" `
  -SkipDocker
```

然后浏览器打开 `https://video.你的域名`，亲自完成：

1. 注册和登录；
2. 选择一个小视频；
3. 验证普通上传；
4. 验证对象存储直传；
5. 查看任务是否完成；
6. 查看 Mock 转写/总结和视频播放；
7. 删除测试任务。

只有脚本和人工流程都通过，才算第一次上线成功。

## 第八关：打开真实 AI

首次上线稳定后，再修改服务器 `.env`：

```dotenv
APP_TRANSCRIPT_ENABLED=true
WHISPER_API_KEY=你的转写API密钥
APP_SUMMARY_ENABLED=true
LLM_API_KEY=你的总结API密钥
```

确认 `WHISPER_API_BASE_URL`、`WHISPER_MODEL`、`LLM_API_BASE_URL`、`LLM_MODEL` 与服务商文档一致，然后重建应用：

```bash
docker compose -f docker-compose.prod.yml up -d --build app
docker compose -f docker-compose.prod.yml logs -f --tail=200 app
```

用 10-30 秒的小视频先验证，不要一上来传几个 GB 的文件。

## 出问题时只按这个顺序查

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=200 caddy
docker compose -f docker-compose.prod.yml logs --tail=300 app
docker compose -f docker-compose.prod.yml logs --tail=200 minio
docker compose -f docker-compose.prod.yml logs --tail=200 rocketmq-broker
docker compose -f docker-compose.prod.yml logs --tail=200 mysql
```

判断方法：

- 域名打不开：先查 DNS、安全组、Caddy；
- 网页能开但登录失败：查 app 和 MySQL；
- 直传 PUT 失败：查 files 域名、MinIO CORS、公网 endpoint；
- 任务一直 QUEUED：查 RocketMQ；
- 任务 FAILED：看任务错误信息和 app 日志；
- 磁盘增长太快：查 MinIO 数据、Docker volume 和日志。

## 回滚

上线前记录当前 commit：

```bash
git rev-parse HEAD
```

新版本出问题时：

```bash
git checkout 上一个正常commit
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f --tail=200 app
```

不要执行 `docker compose down -v`，`-v` 会删除 MySQL、Redis、MinIO 等数据卷。

## 重新决定上线时的第一步

先确认有明确的公网试用需求和预算，再准备 Ubuntu 云服务器与域名。当前项目开发应继续按 `PROJECT_KNOWLEDGE.md` 的本地工程实验路线推进，不必为本指引购买资源。
