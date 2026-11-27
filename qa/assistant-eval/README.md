# 研究助手质量评测

运行一套合成商户数据，核对研究助手能否用正确的来源、市场、日期和币种作答，并给出能打开的引用。43 个用例包括 21 个中文问题和 22 个英文问题，覆盖美国、英国和中国。25 个概览用例核对成交额与销量，11 个榜单用例核对实体顺序、指标和引用，6 个用例要求在缺快照、缺基期或缺指标时说明数据不足，另 1 个用例验证另一工作区的私有来源被拒绝。

## 在本机复现

在仓库根目录运行以下命令。CI 使用 Node.js 24 和 Python 3.13。首次安装需要访问 npm，评测阶段仅访问本机的临时服务。Promptfoo 锁定为 0.126.0，传递依赖由本目录的 package-lock.json 锁定。

```sh
npm ci --prefix qa/assistant-eval --no-audit --no-fund
npm test --prefix qa/assistant-eval
python3 qa/assistant-eval/test_budget.py
```

运行器每次创建临时数据库和两个合成工作区，走正式注册、导入和问答 HTTP 接口。模型和权限配置来自该次显式参数。默认启动的工作台使用空环境文件。Promptfoo 使用本机 JS provider 逐次请求 `POST /api/assistant/ask`，关闭缓存、分享、更新检查和遥测。判分器不调用裁判模型。[Promptfoo 自定义 provider](https://github.com/promptfoo/promptfoo/blob/main/site/docs/providers/index.md)

逐例输出写入 `reports/results.json`。摘要 `reports/summary.json` 给出总用例数、通过率、合格回答数、HTTP 往返延迟 P50/P95 和模型费用。总体通过率包含权限拒绝用例，合格回答数只统计通过的实际回答，包括正确说明缺数据的回答。HTTP 延迟包括接口处理和响应解析。2026-11-26 太平洋时间的一次本机离线运行，43 项全部通过，42 个回答合格，HTTP P50 为 2.29 ms，P95 为 4.43 ms，模型请求数和推理费用均为零。该组数字对应合成样本和本地查询。

## 判分口径

`suite.py` 的原始日记录与手算的对账数值分别维护。任务标签、排序答案和商品 ID 留在评测端，provider 只发送问题、语言和查询窗口。两个可见来源的同一商品 ID 给出不同金额，另一个工作区使用独立私有数据。

判分器检查 HTTP 状态、执行模式、实际查询范围、回答中的市场和时间窗口、金额与销量单位、排名顺序和实体对应指标。链接校验逐一核对来源、市场、截止日和窗口，也核对详情实体及标签。金额规则覆盖阿拉伯数字、分组逗号、基准币种代码和常用货币符号。反例测试向有效答案注入错误货币、金额、日期、跨来源引用及跨租户响应。自然语言释义和未列入样本的表达方式仍需人工抽查。

## 对已授权候选模型运行

此模式会把合成问题及合成资料发送给指定模型。新建配置文件，填写已授权的兼容聊天接口、其模型名、实际限额与合同价格。下例中的本机地址、模型名和价格均为结构示例。

```json
{
  "endpoint": "http://127.0.0.1:9000/v1/chat/completions",
  "model": "candidate-name",
  "context_tokens": 8192,
  "max_output_tokens": 256,
  "input_usd_per_million": "1.00",
  "output_usd_per_million": "2.00",
  "fixed_usd": "0"
}
```

如端点需要凭据，使用环境变量 `TIKFLOWSO_EVAL_MODEL_KEY`。运行器只向临时工作台传递该凭据。下面的命令授权本次向指定端点发送至多 3 个用例，并为整次运行设置 0.05 美元上限。省略 `--limit` 会运行全套样本。

```sh
python3 qa/assistant-eval/run.py --candidate /absolute/path/to/candidate.json --budget-usd 0.05 --limit 3 --output /absolute/path/to/candidate-results
```

临时工作区只为两个合成来源授权指定端点及模型，关闭历史对话和评论外发。每次调用按工作台预算机制先预留，返回可核对的 token 用量后按配置费率结算。超过预算触发本地回退时，候选评测将该用例计为未通过。摘要中的 `metered_usd` 是已结算部分，`unsettled_reserved_usd` 单列待结算的预留。任何一次调用缺失可计费用量，整次的 `model_cost_usd` 和 `model_usd_per_qualified_answer` 都是 null。已知总费用包含未通过用例的成本，再除以合格回答数。计算仅涵盖模型推理，供应商账单可用于复核。

`test_budget.py` 运行一个仅监听本机的模拟模型，验证用量结算、缺用量保留未知以及预算不足时阻止调用。模拟响应复述合成查询结果，用于验证接线、权限、计费和回退判定。默认回归和模拟候选均未测试任何商用模型的回答质量。
