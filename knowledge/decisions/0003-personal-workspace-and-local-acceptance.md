# ADR-0003：个人工作区起步与本地可验收

- 状态：已接受
- 日期：2026-08-29

## 背景

统一 JWT 必须携带真实 tenant，但公开注册时尚无企业邀请上下文。把所有注册用户放入全局默认 tenant 会造成越权风险；直接把 user ID 当 tenant ID 又会阻碍未来一个用户加入多个企业空间。

用户同时要求核心功能验收不依赖公网服务器、正式域名或云账号。

## 决策

- 注册时创建独立 Workspace，生成稳定 `tenant_id`，注册用户成为 OWNER。
- UserAccount 保存主工作区；WorkspaceMember 保存成员关系与工作区角色，为未来邀请和切换工作区保留扩展点。
- 当前 OWNER 在访问 JWT 中映射为 `admin`；JWT 的 `sub` 始终是不可变 user ID。
- 老账号首次登录时幂等补建个人工作区。
- 平台级验收使用本机 H2、SQLite、本地文件存储、mock 转写/摘要和本地 HTTP；不依赖 DNS、公网回调或云中间件。

## 结果

首版注册体验保持简单，同时 tenant 不会与用户或全局默认空间混淆。未来新增邀请、企业 Workspace 和 active workspace 切换时可沿用现有身份与数据边界。
