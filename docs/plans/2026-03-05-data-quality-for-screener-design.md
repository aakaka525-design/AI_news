# 选股系统数据质量修复设计

- 日期: 2026-03-05

> **状态：已批准**

## 背景

选股系统（`potential_screener.py`、`rps_screener.py`）依赖 14+ 张数据表。审计发现 14 个数据质量问题，覆盖基本面、技术面、资金面和整体一致性。目标：让选股结果可靠、可操作。

用户拥有 Tushare 5000+ 积分，可调用全部高级接口。

## 问题汇总

### 致命级（阻塞选股）
- **#9**: 股东人数 — 每只股票仅 1 条记录，无法计算变化（筹码集中信号完全不可用）
- **#4**: 行业 PE 用均值 — 极端值干扰严重，筛选失去区分度
- **#11**: 北向资金 — 仅 top10，`ts_hk_hold` 有 4193 只但数据停在 2026-01-21
- **#1/#3**: 财报/现金流数据滞后约 2 个季度

### 中等（降低精度）
- **#2**: PE_TTM 覆盖率 72% — NULL PE 的股票得 0 分而非"不可用"
- **#10**: 融资数据仅覆盖 64%
- **#5**: 毛利率趋势需 ≥2 期，仅 2525 只满足

### 低（可接受）
- **#6/#7/#8/#12/#13/#14**: 影响小，有变通方案

## 设计方案

### 方向 A：新增数据管道（修复 #9, #11）

#### A1: 股东人数表 (`ts_holder_number`)

新建表，存储 Tushare `stk_holdernumber` 接口的每期股东户数。

```sql
CREATE TABLE ts_holder_number (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    ann_date TEXT,          -- 公告日期
    end_date TEXT NOT NULL, -- 报告期末
    holder_num INTEGER,     -- 股东总户数
    holder_num_change REAL, -- 计算字段：环比变化 %
    UNIQUE(ts_code, end_date)
);
CREATE INDEX idx_holder_num_code_date ON ts_holder_number(ts_code, end_date);
```

抓取脚本: `src/data_ingestion/tushare/holder_number.py`
- 首次回填：抓取所有股票最近 8 个季度
- 每日增量：抓取最新公告
- 插入时计算 `holder_num_change` = (本期 - 上期) / 上期
- 集成到 `update_all_data.py` 调度

#### A2: 北向持股全量刷新 (`ts_hk_hold`)

现有 `ts_hk_hold` 表结构可用，但数据停更。修复：

- 新建抓取脚本 `src/data_ingestion/tushare/northbound.py`，每日调用 `hk_hold` 接口
- 回填 2026-01-21 至今的缺失数据
- 加入 `update_all_data.py` 每日调度
- 覆盖 4000+ 只股票，替代当前仅 top10

### 方向 B：估值精度（修复 #4, #2）

#### B1: 行业估值中位数表 (`industry_valuation`)

新建每日计算表，存储各行业 PE/PB 分位数。

```sql
CREATE TABLE industry_valuation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    industry TEXT NOT NULL,
    pe_median REAL,         -- PE 中位数
    pe_p25 REAL,            -- PE 25分位
    pe_p75 REAL,            -- PE 75分位
    pb_median REAL,         -- PB 中位数
    stock_count INTEGER,    -- 行业内股票总数
    valid_pe_count INTEGER, -- 有效 PE 股票数
    UNIQUE(trade_date, industry)
);
```

计算逻辑：每日 `ts_daily_basic` 更新后执行
- 关联 `ts_stock_basic.industry` 和 `ts_daily_basic.pe_ttm`
- 排除 PE < 0（亏损）和 PE > 500（极端值）后取中位数
- 存储计数指标，便于透明审查

#### B2: 选股器 NULL PE 处理

修改 `potential_screener.py`：
- PE_TTM 为 NULL → 标记"估值不可用"，**不给 0 分**
- 将 7 分 PE 权重重新分配到其他基本面因子（ROE +3, 盈利增长 +4）
- 输出中增加 `data_completeness` 字段

### 方向 C：数据滞后感知（修复 #1, #3）

#### C1: 数据新鲜度视图

```sql
CREATE VIEW data_freshness AS
SELECT
    b.ts_code,
    b.name,
    MAX(d.trade_date) AS latest_daily,
    MAX(f.end_date) AS latest_financial,
    MAX(c.end_date) AS latest_cashflow,
    MAX(h.end_date) AS latest_holder,
    CAST((julianday('now') - julianday(MAX(f.end_date))) / 90 AS INTEGER)
        AS financial_lag_quarters
FROM ts_stock_basic b
LEFT JOIN ts_daily d ON b.ts_code = d.ts_code
LEFT JOIN ts_fina_indicator f ON b.ts_code = f.ts_code
LEFT JOIN ts_cashflow c ON b.ts_code = c.ts_code
LEFT JOIN ts_holder_number h ON b.ts_code = h.ts_code
GROUP BY b.ts_code;
```

#### C2: 滞后加权评分

修改 `potential_screener.py`：
- 财报滞后 ≥ 3 个季度：基本面权重 20 → 10 分
- 释放的 10 分重新分配到技术面(+5) + 资金面(+5)
- 对滞后严重的股票输出警告日志

#### C3: 业绩快报 / 预告补充

新增 Tushare `express`（业绩快报）和 `forecast`（业绩预告）抓取：
- 新表 `ts_express`: 最新营收/利润快报
- 新表 `ts_forecast`: 利润预告区间
- 当快报数据比正式财报更新时，用快报数据计算增长率

### 方向 D：低优先级批量修复

| 问题 | 修复方式 | 位置 |
|------|---------|------|
| #5 毛利率趋势 | 不足 2 期用绝对值评分 | `potential_screener.py` |
| #8 不足 60 天 | 选股已自动排除 | 无需修改 |
| #10 融资覆盖 64% | 非两融标的标记"N/A"，不给 0 分 | `potential_screener.py` |
| #12 资金流不足 3 天 | 跳过主力净流入判断 | `potential_screener.py` |
| #14 list_status NULL | 用 ts_daily 近 5 日有数据判断"在市" | `potential_screener.py` |

## 实施阶段

### Phase 1：数据管道（A1 + A2）
- 新建抓取器：`holder_number.py` — 股东人数
- 新建抓取器：`northbound.py` — 北向持股全量
- 新建表：`ts_holder_number`
- 更新：`update_all_data.py` 加入新任务
- 测试：回填后验证数据完整性

### Phase 2：估值层（B1 + B2）
- 新建表 + 计算脚本：`industry_valuation`
- 修改 `potential_screener.py`：中位数 PE、NULL 处理
- 测试：验证行业中位数计算准确性

### Phase 3：滞后处理（C1 + C2 + C3）
- 新建视图：`data_freshness`
- 新建抓取器：`express.py`、`forecast.py`
- 修改 `potential_screener.py`：滞后加权评分
- 测试：验证权重调整逻辑

### Phase 4：选股器加固（D）
- 批量修复 5 个低优先级问题
- 选股输出增加 `data_quality` 元数据节
- 测试：全流程选股含边界用例

## 涉及文件

| 文件 | 操作 |
|------|------|
| `src/data_ingestion/tushare/holder_number.py` | 新建 — 股东人数抓取 |
| `src/data_ingestion/tushare/northbound.py` | 新建 — 北向持股全量抓取 |
| `src/data_ingestion/tushare/express.py` | 新建 — 业绩快报抓取 |
| `src/data_ingestion/tushare/forecast.py` | 新建 — 业绩预告抓取 |
| `src/database/models.py` | 新增 HolderNumber、IndustryValuation、Express、Forecast 模型 |
| `src/database/repositories/stock.py` | 新增相关查询方法 |
| `src/strategies/potential_screener.py` | 中位数 PE、NULL 处理、滞后加权 |
| `scripts/update_all_data.py` | 新增管道步骤 |
| `scripts/compute_industry_valuation.py` | 新建 — 每日行业中位数计算 |
| `config/settings.py` | 新增 HOLDER_BACKFILL_QUARTERS 等配置 |

## 验收标准

1. `ts_holder_number` 有 ≥2 期数据的股票占比 > 90%
2. `ts_hk_hold` 每日更新，覆盖 > 4000 只
3. `industry_valuation` 使用中位数而非均值
4. PE 为 NULL 的股票不再得 0 分
5. 选股输出包含 `data_quality` 元数据
6. `grep -r "holder_num_change" src/strategies/` 有结果（选股器已接入）
