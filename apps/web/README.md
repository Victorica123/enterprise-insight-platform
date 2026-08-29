# Web 前端（React + Vite）

React 19 + TypeScript + Vite。统一承载真实登录、视频证据、知识问答、六阶段需求分析、PRD 发布审批、工单、关系图谱与运行监控。

完整快速开始见[仓库根 README](../../README.md)。

## 本地开发

```bash
cd apps/web
npm ci
npm run dev        # http://127.0.0.1:5173
```

Agent 与 Media 默认地址分别为 `http://127.0.0.1:8000`、`http://127.0.0.1:8081`，可通过 Vite 环境变量覆盖：

```bash
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > .env
echo "VITE_MEDIA_API_BASE_URL=http://127.0.0.1:8081" >> .env
```

## 构建与检查

```bash
npm run build      # tsc -b 类型检查 + vite 生产构建
npm run preview    # 本地预览生产构建
```

## 结构

```text
src/
  main.tsx            应用装配、真实 Workspace 会话与统一导航
  api.ts              Agent 通用 API 与 Bearer 注入
  mediaApi.ts         Media/Auth/播放 API
  analysisApi.ts      六阶段分析与 PRD 类型/API
  hooks/              媒体任务轮询等跨视图状态
  features/
	AuthGate.tsx       登录/注册个人 Workspace
	MediaWorkspace.tsx 视频上传、范围选择与证据跳播
	AnalysisWorkspace.tsx 六阶段分析、等待恢复、PRD 审批和发布审计
    QAView.tsx        知识问答面板（上传/提问/证据/trace/反馈）
    TicketsView.tsx   工单与审批面板（待审批队列、四眼审批演示）
    GraphView.tsx     关系图谱面板（分层 SVG、关系链查询）
    MonitorView.tsx   运行监控面板（指标带、token 成本、日志回放）
    common.tsx        共享 UI（指标卡、错误提示等）
```

顶栏展示 JWT 中的真实用户与角色，不再提供可伪造的角色/用户切换。个人二次确认、团队待审批队列和四眼职责分离均由服务端 Workspace 策略裁决，前端只呈现状态。
