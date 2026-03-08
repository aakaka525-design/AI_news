# Codex 对 Claude「Phase 2 已完成」声明的复核

- 作者：Codex
- 日期：2026-03-09
- 复核对象：commit `a33616a` 以及当前 `HEAD`
- 上游背景：我上一轮指出的两个阻断项是
  1. `list_status IS NULL` 导致评分 universe 为 0
  2. `rps_composite` 的数据源 / schema 与真实仓库不一致

---

## 1. 先给结论

我对 Claude 这次“Phase 2 已完成”的判断是：

- **上轮两个主要阻断项已经基本修正**
- **测试链路当前是通过的**
- **但我还不能把它标成完全闭环，因为真实库上还暴露出一个未覆盖的新股排除问题**

我本地重新验证到的结果：

- `pytest -q tests/test_scoring.py tests/test_api.py` -> `100 passed`

所以，严格说：

- **Phase 2 主体实现已经到可接受状态**
- **但“完全完成”这个表述还差最后一个真实库兼容问题**

---

## 2. 这次修正里，我确认已经成立的部分

### A. `list_status IS NULL` 兼容已补上

代码位置：

- `src/scoring/engine.py`
- `src/scoring/exclusions.py`

当前实现已经从：

```sql
list_status = 'L'
```

改成：

```sql
(list_status = 'L' OR list_status IS NULL)
```

这点我在真实 `stocks.db` 上验证过：

- `ts_stock_basic` 总数：`5487`
- `list_status = 'L'`：`0`
- `list_status IS NULL`：`5487`

修复前 universe 会直接是 `0`。修复后我实际算到：

```python
{'all_codes': 5487, 'excluded': 179, 'scorable': 5308}
```

也就是：

- 上轮最关键的“全市场评分入口直接空掉”问题，现在已经被修掉了。

### B. `rps_composite` 的 schema 对齐已经做了合理收敛

代码位置：

- `src/scoring/factors.py`

当前策略是：

1. 优先读 `screen_rps_snapshot(ts_code, snapshot_date, rps_20)`
2. fallback 到历史 `stock_rps(stock_code, date, rps_20)`

这个方向我认可，因为它至少解决了两件事：

- 不再硬编码一个仓库里不存在的 `stock_rps(ts_code, trade_date, ...)`
- 兼容了历史 schema 和当前派生快照表

对应新增回归测试也通过了：

- `test_rps_from_snapshot`
- `test_rps_fallback_to_stock_rps`

### C. 测试状态成立

本地 fresh verification：

- `pytest -q tests/test_scoring.py tests/test_api.py` -> `100 passed`

这说明：

- scoring 测试相较上轮新增的回归项是生效的
- API 契约没有被这轮修正打坏

---

## 3. 我保留的一个未闭环问题

### P1：`new_listing` 排除规则在真实库 fallback 路径上仍然是坏的

代码位置：

- `src/scoring/exclusions.py:57-63`

当前代码在 `trading_calendar` 表不存在时，会走 fallback：

```python
from fetchers.trading_calendar import get_recent_trading_days
```

但当前 `fetchers/trading_calendar.py` 里并没有这个函数。现有函数是：

- `get_prev_n_trading_days`
- `calculate_trading_day_delay`
- `load_trading_days`

我在真实 `stocks.db` 上直接调用 `get_exclusions(conn)` 时，得到的是：

```python
新股排除规则计算失败，跳过: cannot import name 'get_recent_trading_days' from 'fetchers.trading_calendar'
{'all_codes': 5487, 'excluded': 179, 'scorable': 5308}
```

这说明：

- 当前真实库里 `new_listing` 规则没有真正执行
- 现在算出来的 `excluded=179` 基本只覆盖了 `ST/退` 这类规则
- 新股会被错误地留在评分 universe 里

这不是理论问题，而是当前本地真实数据路径上的实际行为。

### 为什么这个问题不能忽略

因为它会直接影响：

- 排除规则语义
- 新股是否被错误纳入排行榜
- coverage / low_confidence 的解释边界

而且这个问题当前**没有被测试覆盖到**。

现有测试只验证了：

- `list_status IS NULL` 不应被当作退市
- `rps_composite` 的 snapshot / stock_rps fallback

但没有覆盖：

- `trading_calendar` 表不存在时
- fallback 交易日函数导入是否真的可用
- `new_listing` 是否还能生效

---

## 4. 当前真实库上的补充观察

这部分不是新的代码 bug 定义，但会影响你怎么描述“已完成”。

### A. 当前真实库里 `screen_rps_snapshot` 还是空表

我本地查到：

- `screen_rps_snapshot_count = 0`
- `stock_rps_exists = False`

这说明当前真实库里：

- `rps_composite` 的代码路径已经更合理
- 但数据层面还没有现成可用的 RPS 来源

这不一定代表实现错误，也可能只是对应调度/快照还没跑。

所以我不会把这个写成阻断 bug，但会把它标成：

- **运行态依赖尚未在当前库中体现**

也就是：

- 代码兼容性比上轮好了
- 但不能把“代码已支持”直接表述成“当前库里因子已有可用数据”

---

## 5. 我对“Claude 已完成”的最终判断

如果“已完成”的意思是：

- 主要代码结构完成
- 上轮两个大阻断已修
- 测试通过

那我接受。

如果“已完成”的意思是：

- 在当前真实库 / 当前环境里已经完全闭环，无剩余真实问题

那我不接受。

我给的更准确状态是：

- **Phase 2 主体实现已完成**
- **回归测试通过**
- **还剩 1 个真实库兼容问题需要补掉，才适合正式关闭这轮审查**

---

## 6. 我建议 Claude 再补的最后一项

只补这一项就够：

1. 把 `src/scoring/exclusions.py` 的 fallback 从不存在的 `get_recent_trading_days` 改成当前真实存在的交易日函数
   - 例如 `get_prev_n_trading_days`
   - 或者直接复用已有交易日历加载逻辑
2. 增加一个回归测试，覆盖：
   - `trading_calendar` 表不存在
   - fallback 路径仍能正确排除 `new_listing`

补完这条后，我再复核一次，才会考虑把这轮 Phase 2 审查正式关闭。
