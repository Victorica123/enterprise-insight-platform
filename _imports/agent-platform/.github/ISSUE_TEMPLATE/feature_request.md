---
name: 功能建议
about: 提议一个新能力或改进
title: "[feature] "
labels: enhancement
body:
  - type: textarea
    id: problem
    attributes:
      label: 想解决什么问题？
      description: 先说场景和痛点，再谈方案。
    validations:
      required: true
  - type: textarea
    id: solution
    attributes:
      label: 期望的方案
      description: 你希望它怎么工作？可选：替代方案、参考项目。
    validations:
      required: true
  - type: dropdown
    id: area
    attributes:
      label: 涉及方向
      options:
        - 检索 / RAG 质量
        - Agentic 工作流
        - 工具与审批
        - 关系图谱
        - 观测与成本
        - 前端体验
        - 工程化 / 部署
        - 其他
    validations:
      required: true
