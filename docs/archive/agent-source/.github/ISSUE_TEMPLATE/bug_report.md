---
name: Bug 报告
about: 报告一个问题帮助我们改进
title: "[bug] "
labels: bug
body:
  - type: textarea
    id: what-happened
    attributes:
      label: 发生了什么？
      description: 清晰描述问题与预期行为的差异；有报错信息请贴在代码块里。
    validations:
      required: true
  - type: textarea
    id: reproduce
    attributes:
      label: 复现步骤
      placeholder: |
        1. 启动后端/前端（或 python scripts/seed_demo.py 后）
        2. 提问/上传/审批 ...
        3. 出现 ...
    validations:
      required: true
  - type: dropdown
    id: component
    attributes:
      label: 影响范围
      options:
        - 后端 API（/chat、/documents、/tickets...）
        - Agentic 工作流（路由/检索/证据门控/拒答）
        - 工具调用与审批
        - 关系图谱
        - 监控面板/指标
        - 前端界面
        - 评测门禁（evaluate_v2~v6）
        - CI / 部署
    validations:
      required: true
  - type: textarea
    id: env
    attributes:
      label: 环境
      placeholder: "操作系统、Python 版本、Node 版本、是否配置 LLM Key / fastembed"
  - type: textarea
    id: logs
    attributes:
      label: 相关日志 / trace
      description: 后端 JSON 日志或回答中的执行轨迹（注意先抹掉敏感信息）。
