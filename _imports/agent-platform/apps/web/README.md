# Web 前端（React + Vite）

React 19 + TypeScript + Vite。四个功能面板：知识问答、工单管理（含审批）、关系图谱（SVG 可视化）、运行监控（指标/成本/日志回放）。

完整快速开始见[仓库根 README](../../README.md)。

## 本地开发

```bash
cd apps/web
npm install
npm run dev        # http://127.0.0.1:5173
```

后端默认地址 `http://127.0.0.1:8000`，可通过 `.env`（Vite 环境变量）覆盖：

```bash
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > .env
```

## 构建与检查

```bash
npm run build      # tsc -b 类型检查 + vite 生产构建
npm run preview    # 本地预览生产构建
```

## 结构

```text
src/
  main.tsx            应用装配、全局状态与顶栏（角色/用户切换）
  api.ts              全部 API 调用与类型定义（含 X-User-Role / X-User-Id 头）
  features/
    QAView.tsx        知识问答面板（上传/提问/证据/trace/反馈）
    TicketsView.tsx   工单与审批面板（待审批队列、四眼审批演示）
    GraphView.tsx     关系图谱面板（分层 SVG、关系链查询）
    MonitorView.tsx   运行监控面板（指标带、token 成本、日志回放）
    common.tsx        共享 UI（指标卡、错误提示等）
```

顶栏「演示角色」切换 viewer/operator/admin 体验权限差异；「用户」输入框切换身份，
同一身份发起的写操作不能由自己审批（职责分离演示）。
