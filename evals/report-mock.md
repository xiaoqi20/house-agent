# 风险识别评测报告（extractor=mock · 2026-09-08）

- 语料来源：**合成模板（`evals/generate.py`）+ 生成器自动打标 → 仅回归冒烟，不代表真实合同能力**
- 样本：20 份合同（模板化合成的真实语料替身；拿到真实脱敏合同后可直接替换 contracts/ 并同步 ground_truth.json）
- 指标：precision **100.0%** / recall **100.0%** / F1 **100.0%**（TP=91 FP=0 FN=0）
- 平均抽取延迟：0.0s/份

## 分规则明细

| 规则 | 期望 | TP | FP | FN | 查全 | 查准 |
|------|------|----|----|----|------|------|
| over-penalty | 13 | 13 | 0 | 0 | 100% | 100% |
| deposit-no-deadline | 11 | 11 | 0 | 0 | 100% | 100% |
| no-handover | 11 | 11 | 0 | 0 | 100% | 100% |
| sublease-ban | 11 | 11 | 0 | 0 | 100% | 100% |
| deposit-vague-damage | 11 | 11 | 0 | 0 | 100% | 100% |
| unilateral-termination | 10 | 10 | 0 | 0 | 100% | 100% |
| auto-renewal | 8 | 8 | 0 | 0 | 100% | 100% |
| repair-inverted | 6 | 6 | 0 | 0 | 100% | 100% |
| unclear-fees | 5 | 5 | 0 | 0 | 100% | 100% |
| long-prepay | 5 | 5 | 0 | 0 | 100% | 100% |

## 逐份明细

| 合同 | 期望 | 预测 | 漏报 | 误报 |
|---|---|---|---|---|
| contract_01.txt | 9 | 9 | — | — |
| contract_02.txt | 3 | 3 | — | — |
| contract_03.txt | 4 | 4 | — | — |
| contract_04.txt | 5 | 5 | — | — |
| contract_05.txt | 2 | 2 | — | — |
| contract_06.txt | 7 | 7 | — | — |
| contract_07.txt | 3 | 3 | — | — |
| contract_08.txt | 3 | 3 | — | — |
| contract_09.txt | 6 | 6 | — | — |
| contract_10.txt | 3 | 3 | — | — |
| contract_11.txt | 6 | 6 | — | — |
| contract_12.txt | 3 | 3 | — | — |
| contract_13.txt | 7 | 7 | — | — |
| contract_14.txt | 0 | 0 | — | — |
| contract_15.txt | 7 | 7 | — | — |
| contract_16.txt | 4 | 4 | — | — |
| contract_17.txt | 6 | 6 | — | — |
| contract_18.txt | 3 | 3 | — | — |
| contract_19.txt | 8 | 8 | — | — |
| contract_20.txt | 2 | 2 | — | — |

> 本报告数字只用于管线回归，不可对外宣称「真实合同风险识别能力」（见完善计划 §3）。
