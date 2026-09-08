import os

# 单元测试保持确定性：LLM 链路一律走 mock（真实模型由 scripts/eval_risk.py 评测）
os.environ["LLM_PROVIDER"] = "mock"
