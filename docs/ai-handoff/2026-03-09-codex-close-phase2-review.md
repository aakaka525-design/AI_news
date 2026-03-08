# Codex 对 Claude Phase 2 的最终关闭复核

- 作者：Codex
- 日期：2026-03-09
- 复核对象：当前 `HEAD`（最新修复提交：`21f37c9`）

---

## 1. 结论

这轮我给出的结论是：

- **Phase 2 代码实现可以接受**
- **closing review 通过**
- **我之前指出的最后一个真实库阻断项已经闭环**

这不是基于主观判断，而是基于本地 fresh verification。

---

## 2. Fresh Verification 结果

### A. 测试

我重新执行了完整的本轮相关测试：

- `pytest -q tests/test_scoring.py tests/test_api.py` -> `102 passed`

说明：

- scoring 模块的回归测试继续通过
- API 契约没有因最后一轮修正被打坏

### B. 真实 `stocks.db` 上的 `new_listing` 排除验证

我直接在真实库上运行了 `get_exclusions(conn)`，结果：

```python
{'all_codes': 5487, 'excluded': 217, 'st': 179, 'new_listing': 38}
```

同时我又用 `ts_daily` 最近 `61` 个交易日反推出 cutoff：

```python
{'ts_daily_cutoff': '20251126', 'stocks_newer_than_cutoff': 38}
```

这两个结果一致，说明：

- `new_listing` 排除现在已经在真实库上真正生效
- 之前那个“fallback 最终仍然失效”的问题已经解决

---

## 3. 我确认已闭环的关键项

### A. `list_status IS NULL` universe 兼容

真实库里 `ts_stock_basic` 的 `list_status` 主要是 `NULL`。当前评分 universe 已兼容：

- `(list_status = 'L' OR list_status IS NULL)`

这点之前已经验证过，现在没有回退。

### B. `rps_composite` 数据源兼容

当前实现：

1. 优先 `screen_rps_snapshot`
2. fallback `stock_rps(stock_code, date)`

这修正了原先的 schema 假设错误。相关测试仍在本轮 `102 passed` 中。

### C. `new_listing` 真实库 fallback

这是我上轮保留的最后一个阻断项。

现在 `src/scoring/exclusions.py` 已经不再只依赖：

- `trading_calendar`
- `get_prev_n_trading_days()`

而是增加了更稳定的中间路径：

- 直接从 `ts_daily` 的 distinct `trade_date` 推导 cutoff

这一点正是让真实库上的 `new_listing=38` 成立的关键。

---

## 4. 我对 Claude “已完成”说法的最终判断

这次我接受。

更准确地说：

- **Phase 2 主体功能完成**
- **测试通过**
- **真实库兼容性问题已闭环**
- **这轮审查可以正式关闭**

---

## 5. 仍然存在但不阻断关闭的事项

这些不再属于本轮未完成项，只是后续优化方向：

- `pytest` warnings 清理
- 运行态数据填充是否按计划由 scheduler 持续生成
  - 例如当前 `screen_rps_snapshot` 是否已被定时任务产出
- 综合评分结果表的首次批量跑数和前端消费联调

这些属于下一阶段工作，不影响我对本轮关闭的判断。

---

## 6. 最终状态

**Codex 结论：Phase 2 审查关闭。**
