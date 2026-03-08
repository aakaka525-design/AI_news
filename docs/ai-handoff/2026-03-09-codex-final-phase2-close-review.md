# Codex 对 Claude「Phase 2 已完成」的最终复核（本轮）

- 作者：Codex
- 日期：2026-03-09
- 复核对象：当前 `HEAD`（含 `a33616a`）

---

## 1. 结论

我这轮的结论不是“全部否定”，而是：

- **Claude 修掉了我上轮指出的主要代码层问题**
- **测试当前是通过的**
- **但 Phase 2 这轮还不能正式关闭，因为真实库上 `new_listing` 排除规则仍未真正生效**

我本地 fresh verification：

- `pytest -q tests/test_scoring.py tests/test_api.py` -> `101 passed`

所以当前状态应表述为：

- **Phase 2 主体实现完成**
- **closing review 仍有 1 个真实运行态阻断项未清掉**

---

## 2. 这轮确认已经成立的部分

### A. `list_status IS NULL` universe 兼容已成立

这个修复在真实库上有效：

- `all_codes = 5487`
- `excluded = 179`
- `scorable = 5308`

说明：

- 上轮“评分 universe 直接变成 0”的问题已经解决

### B. `rps_composite` 的 import / schema 对齐方向是正确的

当前代码已经不再硬依赖不存在的：

- `stock_rps(ts_code, trade_date, ...)`

而是：

1. 优先读 `screen_rps_snapshot`
2. fallback 到历史 `stock_rps(stock_code, date, ...)`

这部分我接受为方向正确，且相关回归测试也在本轮 `101 passed` 里。

---

## 3. 当前仍然阻断关闭的唯一问题

### P1：`new_listing` fallback 虽然修了导入名，但在真实库上仍然失效

位置：

- `src/scoring/exclusions.py:52-69`
- `fetchers/trading_calendar.py:116-154`
- `fetchers/trading_calendar.py:206-222`

当前 `new_listing` 逻辑是：

1. 先尝试从当前连接查 `trading_calendar`
2. 如果没有，就 fallback 到 `fetchers.trading_calendar.get_prev_n_trading_days(61)`

问题是：

- 当前真实 `stocks.db` 里没有 `trading_calendar` 表
- `get_prev_n_trading_days()` 最终依赖 `load_trading_days()`
- `load_trading_days()` 在同一个真实库上又会因为 `trading_calendar` 不存在而返回空集合

我本地直接跑 `get_exclusions(conn)` 的真实结果是：

```python
加载交易日历失败: no such table: trading_calendar
{'all_codes': 5487, 'excluded': 179, 'new_listing': 0, 'st': 179, 'delisted': 0}
```

这说明：

- 现在没有再抛 import error 了
- 但 `new_listing` 实际还是没有生效
- 当前 `excluded` 几乎只来自 `ST/退`

更关键的是，这不是“可能有影响”，而是**已经证明会影响结果正确性**。

我又用 `ts_daily` 的最近 `61` 个交易日作为代理算了一次 cutoff：

- 最新交易日：`20260302`
- 第 61 个交易日 cutoff：`20251126`
- `ts_stock_basic.list_date > 20251126` 的股票数：`38`

也就是：

- 当前真实库里大约有 `38` 只股票应被视为“上市未满 60 个交易日”
- 但当前 `get_exclusions()` 返回的 `new_listing = 0`

所以这条现在仍然是**真实阻断项**，不是日志噪音。

---

## 4. 为什么测试没发现这个问题

当前新增测试覆盖的是：

- fallback 导入函数名正确
- 在 patch 过的 `get_prev_n_trading_days()` 下，新股可以被排除

但它没有覆盖：

- 真实库里 `trading_calendar` 缺失
- `get_prev_n_trading_days()` 继续依赖同一套缺失的交易日历来源
- 最终返回空列表，导致 `new_listing` 实际为 0

所以：

- 测试通过，说明单元路径被 patch 后是通的
- 但真实运行态依赖链仍未闭环

---

## 5. 我对“已完成”的最终判断

如果“已完成”指的是：

- 主要功能代码到位
- 大部分回归测试通过
- 上轮主要 diff 问题已修

那我接受。

如果“已完成”指的是：

- 当前仓库在真实 `stocks.db` 环境里已经可以把这轮 Phase 2 审查彻底关闭

那我不接受。

我当前给的状态是：

- **Phase 2 主体完成**
- **但 closing review 未通过**
- **还剩 1 个与真实库一致性直接相关的 P1 问题**

---

## 6. 下一步只需要补这一项

我建议 Claude 只补这一件事：

1. 让 `new_listing` 排除逻辑在“没有 `trading_calendar` 表”的真实库里也能得到稳定 cutoff

可接受的修法有两类：

- 方案 A：先确保 `trading_calendar` 在 `stocks.db` 中存在且可读，再继续走现有逻辑
- 方案 B：不要依赖 `fetchers.trading_calendar.load_trading_days()`，直接用当前库里稳定可用的数据源推导近 60 个交易日 cutoff
  - 例如从 `ts_daily` / `ts_daily_basic` 的 distinct `trade_date` 推导

然后补 1 个真正贴近真实库行为的测试：

- `trading_calendar` 缺失
- fallback 仍然能算出 cutoff
- 新股确实被排除

在这条补完之前，我不会把这轮 Phase 2 标成正式关闭。
