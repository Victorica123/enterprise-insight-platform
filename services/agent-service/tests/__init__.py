"""测试包的全局环境：离线确定性 + 不消耗真实 API 额度。

LLM 路由（Router/Planner/工具选择）默认关闭，走规则降级通道；
需要验证 LLM 路径的用例通过 mock 直接替换入口函数，不受此开关影响。
"""
import os

os.environ.setdefault("LLM_ROUTER_ENABLED", "0")
