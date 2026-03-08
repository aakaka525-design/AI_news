# 选股系统数据质量修复 — 实施计划

> **状态：部分完成**
> 股东人数、北向持股、评分/telemetry/快照等多组 screener 测试已落地，但本计划覆盖面较广（14 个数据质量问题），尚未逐项回填完成度。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 修复 14 个数据质量问题，使多因子选股系统的评分结果可靠、可操作。

**架构:** 项目使用 sqlite3 直连模式（`get_connection()`）进行数据存取。Tushare 数据通过 `TushareAdapter`（含速率限制和重试）抓取，落地到 `data/stocks.db`。选股器 `potential_screener.py` 用 `pd.read_sql_query()` 读数据、NumPy 打分。新增管道遵循现有 `moneyflow.py` 等同样的模式：init_tables → fetch → INSERT OR REPLACE。

**技术栈:** Python 3, SQLite, Tushare API, pandas, numpy

**关键约束:**
- `TushareAdapter` 已有 `stk_holdernumber()` 和 `hk_hold()` 方法，但 **没有** `express()` 和 `forecast()`
- 现有 fetcher 全部使用 `sqlite3` 直连，不走 SQLAlchemy ORM
- 选股器 `potential_screener.py` 使用 `sqlite3.Connection` + `pd.read_sql_query()`

---

## Phase 1: 数据管道 — 股东人数 + 北向持股全量

### Task 1: 新建股东人数抓取器

**文件:**
- 新建: `src/data_ingestion/tushare/holder_number.py`
- 测试: `tests/test_holder_number.py`

**Step 1: 写失败测试**

```python
# tests/test_holder_number.py
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn

def test_init_tables_creates_holder_number(mem_conn):
    from src.data_ingestion.tushare.holder_number import init_tables
    init_tables(conn=mem_conn)
    row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ts_holder_number'"
    ).fetchone()
    assert row is not None

def test_fetch_holder_number_inserts_data(mem_conn):
    from src.data_ingestion.tushare.holder_number import init_tables, fetch_holder_number

    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.stk_holdernumber.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "ann_date": "20260101", "end_date": "20251231", "holder_num": 500000},
        {"ts_code": "000001.SZ", "ann_date": "20250401", "end_date": "20250930", "holder_num": 550000},
    ])
    count = fetch_holder_number("000001.SZ", client=mock_client, conn=mem_conn)
    assert count == 2
    rows = mem_conn.execute("SELECT * FROM ts_holder_number ORDER BY end_date").fetchall()
    assert len(rows) == 2

def test_holder_num_change_calculated(mem_conn):
    from src.data_ingestion.tushare.holder_number import init_tables, fetch_holder_number

    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.stk_holdernumber.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "ann_date": "20260101", "end_date": "20251231", "holder_num": 500000},
        {"ts_code": "000001.SZ", "ann_date": "20250701", "end_date": "20250930", "holder_num": 550000},
    ])
    fetch_holder_number("000001.SZ", client=mock_client, conn=mem_conn)
    row = mem_conn.execute(
        "SELECT holder_num_change FROM ts_holder_number WHERE end_date='20251231'"
    ).fetchone()
    # (500000 - 550000) / 550000 ≈ -0.0909
    assert row[0] is not None
    assert abs(row[0] - (-9.09)) < 0.1  # 百分比
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_holder_number.py -v`
预期: FAIL — `ModuleNotFoundError: No module named 'src.data_ingestion.tushare.holder_number'`

**Step 3: 实现抓取器**

```python
# src/data_ingestion/tushare/holder_number.py
#!/usr/bin/env python3
"""
Tushare 股东人数抓取模块

数据源: stk_holdernumber 接口
功能: 抓取每只股票每个报告期的股东总户数，计算环比变化
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_tables(conn: sqlite3.Connection = None):
    """初始化股东人数表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_holder_number (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            holder_num INTEGER,
            holder_num_change REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_holder_num_code_date "
        "ON ts_holder_number(ts_code, end_date)"
    )
    conn.commit()

    if own_conn:
        conn.close()
    log("✅ 股东人数表初始化完成")


def fetch_holder_number(
    ts_code: str,
    client: TushareAdapter = None,
    conn: sqlite3.Connection = None,
) -> int:
    """
    抓取单只股票的股东人数数据并计算环比变化。
    返回插入/更新的记录数。
    """
    if client is None:
        client = get_tushare_client()

    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        df = client.stk_holdernumber(ts_code=ts_code)
        if df is None or df.empty:
            return 0

        # 按 end_date 升序排列，便于计算环比
        df = df.sort_values("end_date").reset_index(drop=True)

        count = 0
        prev_num = None
        for _, row in df.iterrows():
            holder_num = row.get("holder_num")
            change = None
            if prev_num and prev_num > 0 and holder_num is not None:
                change = round((holder_num - prev_num) / prev_num * 100, 2)

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_holder_number
                    (ts_code, ann_date, end_date, holder_num, holder_num_change, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code", ts_code),
                    row.get("ann_date"),
                    row.get("end_date"),
                    holder_num,
                    change,
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 {ts_code} {row.get('end_date')} 失败: {e}")

            if holder_num is not None:
                prev_num = holder_num

        conn.commit()
        return count
    finally:
        if own_conn:
            conn.close()


def fetch_all_holder_numbers(client: TushareAdapter = None) -> int:
    """批量抓取全市场股东人数（回填最近 8 个季度）"""
    log("=" * 50)
    log("Tushare 股东人数批量抓取")
    log("=" * 50)

    if client is None:
        client = get_tushare_client()

    init_tables()
    conn = get_connection()

    try:
        # 获取所有活跃股票
        stocks = pd.read_sql_query(
            "SELECT ts_code FROM ts_stock_basic WHERE list_status='L'", conn
        )
        total_stocks = len(stocks)
        log(f"📊 活跃股票: {total_stocks} 只")

        total_count = 0
        for i, row in stocks.iterrows():
            ts_code = row["ts_code"]
            if (i + 1) % 100 == 0:
                log(f"  进度: {i+1}/{total_stocks}")
            count = fetch_holder_number(ts_code, client=client, conn=conn)
            total_count += count

        log(f"\n✅ 完成! 共 {total_count} 条股东人数记录")
        return total_count
    finally:
        conn.close()


def main():
    log("=" * 50)
    log("Tushare 股东人数抓取")
    log("=" * 50)
    fetch_all_holder_numbers()


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_holder_number.py -v`
预期: 3 passed

**Step 5: 提交**

```bash
git add src/data_ingestion/tushare/holder_number.py tests/test_holder_number.py
git commit -m "feat: add holder number fetcher with change calculation"
```

---

### Task 2: 新建北向持股全量抓取器

**文件:**
- 新建: `src/data_ingestion/tushare/northbound.py`
- 测试: `tests/test_northbound.py`

**Step 1: 写失败测试**

```python
# tests/test_northbound.py
import sqlite3
import pytest
from unittest.mock import MagicMock
import pandas as pd

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn

def test_init_tables_creates_hk_hold(mem_conn):
    from src.data_ingestion.tushare.northbound import init_tables
    init_tables(conn=mem_conn)
    row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ts_hk_hold'"
    ).fetchone()
    assert row is not None

def test_fetch_northbound_by_date(mem_conn):
    from src.data_ingestion.tushare.northbound import init_tables, fetch_northbound_by_date

    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.hk_hold.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "20260305", "vol": 1000000, "ratio": 1.23, "exchange": "SZ"},
        {"ts_code": "600519.SH", "trade_date": "20260305", "vol": 500000, "ratio": 0.56, "exchange": "SH"},
    ])
    count = fetch_northbound_by_date("20260305", client=mock_client, conn=mem_conn)
    assert count == 2

def test_fetch_northbound_upsert(mem_conn):
    from src.data_ingestion.tushare.northbound import init_tables, fetch_northbound_by_date

    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.hk_hold.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "20260305", "vol": 1000000, "ratio": 1.23, "exchange": "SZ"},
    ])
    fetch_northbound_by_date("20260305", client=mock_client, conn=mem_conn)
    # 再次插入（更新）
    mock_client.hk_hold.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "20260305", "vol": 2000000, "ratio": 2.00, "exchange": "SZ"},
    ])
    fetch_northbound_by_date("20260305", client=mock_client, conn=mem_conn)
    rows = mem_conn.execute("SELECT * FROM ts_hk_hold").fetchall()
    assert len(rows) == 1  # upsert, not duplicate
    assert rows[0]["vol"] == 2000000
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_northbound.py -v`
预期: FAIL — `ModuleNotFoundError`

**Step 3: 实现抓取器**

```python
# src/data_ingestion/tushare/northbound.py
#!/usr/bin/env python3
"""
Tushare 北向持股全量抓取模块

数据源: hk_hold 接口（全量持股，非仅 top10）
功能: 每日抓取所有北向持股数据，回填缺失日期
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_tables(conn: sqlite3.Connection = None):
    """初始化北向持股全量表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_hk_hold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            vol INTEGER,
            ratio REAL,
            exchange TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hk_hold_code ON ts_hk_hold(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hk_hold_date ON ts_hk_hold(trade_date)")
    conn.commit()

    if own_conn:
        conn.close()
    log("✅ 北向持股全量表初始化完成")


def fetch_northbound_by_date(
    trade_date: str,
    client: TushareAdapter = None,
    conn: sqlite3.Connection = None,
) -> int:
    """抓取指定日期的北向持股全量数据"""
    if client is None:
        client = get_tushare_client()

    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        df = client.hk_hold(trade_date=trade_date)
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_hk_hold
                    (ts_code, trade_date, vol, ratio, exchange, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code"),
                    trade_date,
                    row.get("vol"),
                    row.get("ratio"),
                    row.get("exchange"),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 {row.get('ts_code')} 失败: {e}")

        conn.commit()
        return count
    finally:
        if own_conn:
            conn.close()


def fetch_northbound_range(start_date: str, end_date: str = None) -> int:
    """批量抓取北向持股"""
    log("=" * 50)
    log("Tushare 北向持股全量批量抓取")
    log("=" * 50)

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    init_tables()
    client = get_tushare_client()
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 交易日: {len(trading_days)} 天")

    total = 0
    for i, trade_date in enumerate(trading_days):
        log(f"[{i+1}/{len(trading_days)}] {trade_date}")
        count = fetch_northbound_by_date(trade_date, client)
        total += count
        if count > 0:
            log(f"   ✅ {count} 条")

    log(f"\n✅ 完成! 共 {total} 条北向持股记录")
    return total


def main():
    """默认抓取最近 5 个交易日"""
    log("=" * 50)
    log("Tushare 北向持股全量抓取")
    log("=" * 50)

    init_tables()
    client = get_tushare_client()

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)

    for trade_date in trading_days[-5:]:
        count = fetch_northbound_by_date(trade_date, client)
        log(f"  {trade_date}: {count} 条")

    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_northbound.py -v`
预期: 3 passed

**Step 5: 提交**

```bash
git add src/data_ingestion/tushare/northbound.py tests/test_northbound.py
git commit -m "feat: add northbound full holdings fetcher (hk_hold)"
```

---

### Task 3: 集成到 update_all_data.py

**文件:**
- 修改: `scripts/update_all_data.py`

**Step 1: 在 steps 列表末尾添加两个新管道**

在 `scripts/update_all_data.py:48-54` 的 `steps` 列表末尾追加:

```python
    ("src.data_ingestion.tushare.holder_number", "股东人数数据"),
    ("src.data_ingestion.tushare.northbound", "北向持股全量"),
```

**Step 2: 运行 dry-run 确认模块可导入**

运行: `python -c "from src.data_ingestion.tushare.holder_number import main; print('OK')"`
运行: `python -c "from src.data_ingestion.tushare.northbound import main; print('OK')"`
预期: 两个都输出 `OK`

**Step 3: 提交**

```bash
git add scripts/update_all_data.py
git commit -m "feat: add holder_number and northbound to daily update pipeline"
```

---

## Phase 2: 估值精度 — 行业中位数 + NULL PE 处理

### Task 4: 新建行业估值中位数计算脚本

**文件:**
- 新建: `scripts/compute_industry_valuation.py`
- 测试: `tests/test_industry_valuation.py`

**Step 1: 写失败测试**

```python
# tests/test_industry_valuation.py
import sqlite3
import pytest
import pandas as pd

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 创建依赖表
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ts_daily_basic (
            id INTEGER PRIMARY KEY, ts_code TEXT, trade_date TEXT,
            pe_ttm REAL, pb REAL
        )
    """)
    # 插入测试数据: 3只银行股, PE 分别为 5, 10, 100(极端值)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ','A','银行','L')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('B.SZ','B','银行','L')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('C.SZ','C','银行','L')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('D.SZ','D','科技','L')")
    conn.execute("INSERT INTO ts_daily_basic (ts_code,trade_date,pe_ttm,pb) VALUES ('A.SZ','20260305',5.0,0.8)")
    conn.execute("INSERT INTO ts_daily_basic (ts_code,trade_date,pe_ttm,pb) VALUES ('B.SZ','20260305',10.0,1.2)")
    conn.execute("INSERT INTO ts_daily_basic (ts_code,trade_date,pe_ttm,pb) VALUES ('C.SZ','20260305',600.0,5.0)")  # 极端值, PE>500
    conn.execute("INSERT INTO ts_daily_basic (ts_code,trade_date,pe_ttm,pb) VALUES ('D.SZ','20260305',30.0,3.0)")
    conn.commit()
    return conn

def test_init_table(mem_conn):
    from scripts.compute_industry_valuation import init_table
    init_table(conn=mem_conn)
    row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='industry_valuation'"
    ).fetchone()
    assert row is not None

def test_compute_filters_extreme_pe(mem_conn):
    from scripts.compute_industry_valuation import init_table, compute_for_date
    init_table(conn=mem_conn)
    compute_for_date("20260305", conn=mem_conn)
    row = mem_conn.execute(
        "SELECT pe_median, stock_count, valid_pe_count FROM industry_valuation WHERE industry='银行'"
    ).fetchone()
    # C.SZ 的 PE=600 被排除(>500), 剩余 A(5) B(10), 中位数=7.5
    assert row["valid_pe_count"] == 2
    assert row["stock_count"] == 3
    assert abs(row["pe_median"] - 7.5) < 0.01

def test_compute_negative_pe_excluded(mem_conn):
    """PE 为负的也应被排除"""
    from scripts.compute_industry_valuation import init_table, compute_for_date
    mem_conn.execute("INSERT INTO ts_stock_basic VALUES ('E.SZ','E','银行','L')")
    mem_conn.execute("INSERT INTO ts_daily_basic (ts_code,trade_date,pe_ttm,pb) VALUES ('E.SZ','20260305',-5.0,0.5)")
    mem_conn.commit()
    init_table(conn=mem_conn)
    compute_for_date("20260305", conn=mem_conn)
    row = mem_conn.execute(
        "SELECT valid_pe_count FROM industry_valuation WHERE industry='银行'"
    ).fetchone()
    assert row["valid_pe_count"] == 2  # 仍然只有 A 和 B
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_industry_valuation.py -v`
预期: FAIL

**Step 3: 实现计算脚本**

```python
# scripts/compute_industry_valuation.py
#!/usr/bin/env python3
"""
计算行业估值中位数

每日在 ts_daily_basic 更新后运行，输出 industry_valuation 表。
排除 PE < 0（亏损）和 PE > 500（极端值）后计算中位数和分位数。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_table(conn: sqlite3.Connection = None):
    """初始化行业估值表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS industry_valuation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            industry TEXT NOT NULL,
            pe_median REAL,
            pe_p25 REAL,
            pe_p75 REAL,
            pb_median REAL,
            stock_count INTEGER,
            valid_pe_count INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, industry)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ind_val_date "
        "ON industry_valuation(trade_date)"
    )
    conn.commit()

    if own_conn:
        conn.close()


def compute_for_date(trade_date: str, conn: sqlite3.Connection = None):
    """计算指定日期的行业估值中位数"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        query = """
            SELECT b.industry, d.pe_ttm, d.pb
            FROM ts_daily_basic d
            JOIN ts_stock_basic b ON d.ts_code = b.ts_code
            WHERE d.trade_date = ?
              AND b.industry IS NOT NULL
              AND b.industry != ''
        """
        df = pd.read_sql_query(query, conn, params=[trade_date])

        if df.empty:
            log(f"  ⚠️ {trade_date} 无数据")
            return

        for industry, group in df.groupby("industry"):
            stock_count = len(group)
            # 过滤有效 PE: 排除 NULL, 负数, >500
            valid_pe = group["pe_ttm"].dropna()
            valid_pe = valid_pe[(valid_pe > 0) & (valid_pe <= 500)]
            valid_pe_count = len(valid_pe)

            pe_median = float(valid_pe.median()) if valid_pe_count > 0 else None
            pe_p25 = float(valid_pe.quantile(0.25)) if valid_pe_count > 0 else None
            pe_p75 = float(valid_pe.quantile(0.75)) if valid_pe_count > 0 else None

            valid_pb = group["pb"].dropna()
            valid_pb = valid_pb[valid_pb > 0]
            pb_median = float(valid_pb.median()) if len(valid_pb) > 0 else None

            conn.execute("""
                INSERT OR REPLACE INTO industry_valuation
                (trade_date, industry, pe_median, pe_p25, pe_p75,
                 pb_median, stock_count, valid_pe_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_date, industry, pe_median, pe_p25, pe_p75,
                pb_median, stock_count, valid_pe_count,
                datetime.now().isoformat(),
            ))

        conn.commit()
        industries = df["industry"].nunique()
        log(f"  ✅ {trade_date}: {industries} 个行业")
    finally:
        if own_conn:
            conn.close()


def main():
    log("=" * 50)
    log("行业估值中位数计算")
    log("=" * 50)

    init_table()
    conn = get_connection()

    try:
        # 获取最新交易日
        row = conn.execute("SELECT MAX(trade_date) FROM ts_daily_basic").fetchone()
        latest = row[0]
        if not latest:
            log("⚠️ ts_daily_basic 无数据")
            return
        log(f"📅 最新交易日: {latest}")
        compute_for_date(latest, conn=conn)
    finally:
        conn.close()

    log("✅ 完成!")


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_industry_valuation.py -v`
预期: 3 passed

**Step 5: 提交**

```bash
git add scripts/compute_industry_valuation.py tests/test_industry_valuation.py
git commit -m "feat: add industry valuation median computation script"
```

---

### Task 5: 修改选股器 — 中位数 PE + NULL 处理

**文件:**
- 修改: `src/strategies/potential_screener.py:253-313` (`score_fundamentals` 函数)
- 测试: `tests/test_screener_fundamentals.py`

**Step 1: 写失败测试**

```python
# tests/test_screener_fundamentals.py
import sqlite3
import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def conn_with_data():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # 基础表
    conn.execute("CREATE TABLE ts_stock_basic (ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT)")
    conn.execute("CREATE TABLE ts_fina_indicator (ts_code TEXT, end_date TEXT, roe REAL, netprofit_yoy REAL)")
    conn.execute("CREATE TABLE ts_daily_basic (ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL)")
    conn.execute("CREATE TABLE industry_valuation (trade_date TEXT, industry TEXT, pe_median REAL, pe_p25 REAL, pe_p75 REAL, stock_count INTEGER, valid_pe_count INTEGER, UNIQUE(trade_date, industry))")
    conn.execute("CREATE TABLE ts_daily (ts_code TEXT, trade_date TEXT, close REAL, amount REAL)")

    # 股票 A: PE=15, 行业中位数=20 → PE < 中位数 → 估值偏低
    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ','A','银行','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('A.SZ','20251231',18.0,25.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('A.SZ','20260305',15.0,1.2)")

    # 股票 B: PE=NULL → 应标记估值不可用, 不得 0 分
    conn.execute("INSERT INTO ts_stock_basic VALUES ('B.SZ','B','科技','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('B.SZ','20251231',20.0,30.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('B.SZ','20260305',NULL,3.0)")

    # 行业估值
    conn.execute("INSERT INTO industry_valuation VALUES ('20260305','银行',20.0,12.0,30.0,10,8)")
    conn.execute("INSERT INTO industry_valuation VALUES ('20260305','科技',35.0,25.0,50.0,15,12)")

    conn.commit()
    return conn


def test_null_pe_not_zero_score(conn_with_data):
    """PE 为 NULL 的股票不应得 0 分，fund_pe 应为 NaN"""
    from src.strategies.potential_screener import score_fundamentals
    candidates = pd.Series(["A.SZ", "B.SZ"])
    result = score_fundamentals(conn_with_data, candidates)
    b_row = result[result["ts_code"] == "B.SZ"].iloc[0]
    # fund_pe 应该是 NaN 而不是 0
    assert pd.isna(b_row["fund_pe"]), f"Expected NaN for NULL PE, got {b_row['fund_pe']}"


def test_pe_uses_industry_median(conn_with_data):
    """PE 评分应相对于行业中位数"""
    from src.strategies.potential_screener import score_fundamentals
    candidates = pd.Series(["A.SZ"])
    result = score_fundamentals(conn_with_data, candidates)
    a_row = result[result["ts_code"] == "A.SZ"].iloc[0]
    # PE=15 < 行业中位数 20 → 估值偏低，应得高分
    assert a_row["fund_pe"] >= 5.0


def test_data_completeness_field(conn_with_data):
    """输出应包含 data_completeness 字段"""
    from src.strategies.potential_screener import score_fundamentals
    candidates = pd.Series(["A.SZ", "B.SZ"])
    result = score_fundamentals(conn_with_data, candidates)
    assert "data_completeness" in result.columns
    a_row = result[result["ts_code"] == "A.SZ"].iloc[0]
    b_row = result[result["ts_code"] == "B.SZ"].iloc[0]
    assert a_row["data_completeness"] == "full"
    assert b_row["data_completeness"] == "pe_missing"
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_screener_fundamentals.py -v`
预期: FAIL — 当前 `score_fundamentals` 不支持行业中位数，NULL PE 得 0 分

**Step 3: 修改 `score_fundamentals` 函数**

替换 `potential_screener.py` 中的 `score_fundamentals` 函数 (L255-313):

```python
def score_fundamentals(conn: sqlite3.Connection, candidates: pd.Series) -> pd.DataFrame:
    """基本面评分: ROE(8) + PE相对行业(7) + 盈利增长(5)

    修复:
    - PE_TTM 为 NULL → 标记 'pe_missing', fund_pe = NaN (不计入总分)
    - PE 评分使用相对行业中位数，而非绝对区间
    - 输出 data_completeness 字段
    """
    log("计算基本面因子...")
    scores = pd.DataFrame({"ts_code": candidates})

    # ── 3a+3c. ROE 和 盈利增长 from ts_fina_indicator
    fina_query = """
        SELECT ts_code, roe, netprofit_yoy
        FROM ts_fina_indicator f1
        WHERE end_date = (
            SELECT MAX(end_date) FROM ts_fina_indicator f2
            WHERE f2.ts_code = f1.ts_code
        )
    """
    fina = pd.read_sql_query(fina_query, conn)
    fina = fina.drop_duplicates(subset="ts_code", keep="first")
    scores = scores.merge(fina, on="ts_code", how="left")

    scores["fund_roe"] = np.select(
        [scores["roe"] > 15, scores["roe"] > 10, scores["roe"] > 5],
        [8.0, 5.0, 2.0],
        default=0.0,
    )

    scores["fund_growth"] = np.select(
        [scores["netprofit_yoy"] > 30, scores["netprofit_yoy"] > 10, scores["netprofit_yoy"] > 0],
        [5.0, 3.0, 1.0],
        default=0.0,
    )

    # ── 3b. 估值: PE_TTM 相对行业中位数
    pe_query = """
        SELECT d.ts_code, d.pe_ttm, b.industry
        FROM ts_daily_basic d
        JOIN ts_stock_basic b ON d.ts_code = b.ts_code
        WHERE d.trade_date = (SELECT MAX(trade_date) FROM ts_daily_basic)
    """
    pe = pd.read_sql_query(pe_query, conn)
    scores = scores.merge(pe[["ts_code", "pe_ttm", "industry"]], on="ts_code", how="left")

    # 尝试加载行业中位数
    has_industry_val = False
    try:
        iv_query = """
            SELECT industry, pe_median, pe_p25, pe_p75
            FROM industry_valuation
            WHERE trade_date = (SELECT MAX(trade_date) FROM industry_valuation)
        """
        iv = pd.read_sql_query(iv_query, conn)
        if not iv.empty:
            scores = scores.merge(iv, on="industry", how="left")
            has_industry_val = True
    except Exception:
        pass  # industry_valuation 表可能不存在

    if has_industry_val:
        # 相对行业中位数评分
        # PE < p25 → 7分 (明显低估)
        # PE < median → 5分 (偏低估)
        # PE < p75 → 3分 (合理)
        # PE >= p75 → 1分 (偏高)
        # PE is NULL → NaN
        pe_valid = scores["pe_ttm"].notna() & (scores["pe_ttm"] > 0)
        scores["fund_pe"] = np.where(
            ~pe_valid,
            np.nan,
            np.select(
                [
                    pe_valid & (scores["pe_ttm"] <= scores["pe_p25"]),
                    pe_valid & (scores["pe_ttm"] <= scores["pe_median"]),
                    pe_valid & (scores["pe_ttm"] <= scores["pe_p75"]),
                ],
                [7.0, 5.0, 3.0],
                default=1.0,
            ),
        )
    else:
        # 回退: 绝对区间评分 (兼容无 industry_valuation 表的情况)
        pe_valid = scores["pe_ttm"].notna()
        scores["fund_pe"] = np.where(
            ~pe_valid,
            np.nan,
            np.select(
                [
                    pe_valid & (scores["pe_ttm"] >= 10) & (scores["pe_ttm"] <= 30),
                    pe_valid & (scores["pe_ttm"] > 30) & (scores["pe_ttm"] <= 50),
                    pe_valid & (scores["pe_ttm"] >= 5) & (scores["pe_ttm"] < 10),
                ],
                [7.0, 4.0, 3.0],
                default=0.0,
            ),
        )

    # data_completeness 标记
    scores["data_completeness"] = np.where(
        scores["pe_ttm"].isna(), "pe_missing", "full"
    )

    # NULL PE 的权重重新分配: ROE +3, 盈利增长 +4 (仅对 pe_missing 的行)
    pe_missing = scores["data_completeness"] == "pe_missing"
    scores.loc[pe_missing, "fund_roe"] = scores.loc[pe_missing, "fund_roe"].apply(
        lambda x: min(x + 3, 11.0)  # ROE 最高 8+3=11
    )
    scores.loc[pe_missing, "fund_growth"] = scores.loc[pe_missing, "fund_growth"].apply(
        lambda x: min(x + 4, 9.0)  # 盈利增长最高 5+4=9
    )

    scores["score_fundamental"] = (
        scores["fund_roe"].fillna(0) + scores["fund_pe"].fillna(0) + scores["fund_growth"].fillna(0)
    ).round(2)

    cols_drop = ["roe", "netprofit_yoy", "pe_ttm", "industry"]
    if has_industry_val:
        cols_drop += ["pe_median", "pe_p25", "pe_p75"]
    scores.drop(columns=[c for c in cols_drop if c in scores.columns], inplace=True)
    return scores
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_screener_fundamentals.py -v`
预期: 3 passed

**Step 5: 提交**

```bash
git add src/strategies/potential_screener.py tests/test_screener_fundamentals.py
git commit -m "feat: screener uses industry PE median, handles NULL PE properly"
```

---

### Task 6: 集成行业估值到 update_all_data.py

**文件:**
- 修改: `scripts/update_all_data.py`

**Step 1: 在 steps 列表中添加行业估值计算**

在 `holder_number` 步骤之后添加:

```python
    ("scripts.compute_industry_valuation", "行业估值中位数计算"),
```

注意: 必须在 `daily` 步骤之后运行（依赖 `ts_daily_basic` 数据）。

**Step 2: 提交**

```bash
git add scripts/update_all_data.py
git commit -m "feat: add industry valuation computation to daily pipeline"
```

---

## Phase 3: 数据滞后感知 — 新鲜度 + 业绩快报

### Task 7: 添加 express/forecast 方法到 TushareAdapter

**文件:**
- 修改: `src/data_ingestion/tushare/client.py`

**Step 1: 在 `TushareAdapter` 类中添加两个方法**

在 `stk_holdernumber` 方法 (L422) 之后添加:

```python
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def express(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None,
    ) -> pd.DataFrame:
        """
        获取业绩快报

        Returns:
            DataFrame 包含: ts_code, ann_date, end_date, revenue, operate_profit,
                           total_profit, n_income, total_assets, etc.
        """
        self._log_request("express")
        return self.api.express(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def forecast(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None,
    ) -> pd.DataFrame:
        """
        获取业绩预告

        Returns:
            DataFrame 包含: ts_code, ann_date, end_date, type, p_change_min,
                           p_change_max, net_profit_min, net_profit_max, etc.
        """
        self._log_request("forecast")
        return self.api.forecast(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )
```

**Step 2: 提交**

```bash
git add src/data_ingestion/tushare/client.py
git commit -m "feat: add express and forecast API methods to TushareAdapter"
```

---

### Task 8: 新建业绩快报/预告抓取器

**文件:**
- 新建: `src/data_ingestion/tushare/express_forecast.py`
- 测试: `tests/test_express_forecast.py`

**Step 1: 写失败测试**

```python
# tests/test_express_forecast.py
import sqlite3
import pytest
from unittest.mock import MagicMock
import pandas as pd

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn

def test_init_tables(mem_conn):
    from src.data_ingestion.tushare.express_forecast import init_tables
    init_tables(conn=mem_conn)
    tables = [r[0] for r in mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "ts_express" in tables
    assert "ts_forecast" in tables

def test_fetch_express(mem_conn):
    from src.data_ingestion.tushare.express_forecast import init_tables, fetch_express
    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.express.return_value = pd.DataFrame([{
        "ts_code": "000001.SZ", "ann_date": "20260115", "end_date": "20251231",
        "revenue": 100000.0, "operate_profit": 50000.0,
        "total_profit": 45000.0, "n_income": 35000.0,
        "total_assets": 500000.0, "yoy_net_profit": 15.5,
    }])
    count = fetch_express("000001.SZ", client=mock_client, conn=mem_conn)
    assert count == 1

def test_fetch_forecast(mem_conn):
    from src.data_ingestion.tushare.express_forecast import init_tables, fetch_forecast
    init_tables(conn=mem_conn)
    mock_client = MagicMock()
    mock_client.forecast.return_value = pd.DataFrame([{
        "ts_code": "000001.SZ", "ann_date": "20260120", "end_date": "20251231",
        "type": "预增", "p_change_min": 20.0, "p_change_max": 40.0,
        "net_profit_min": 30000.0, "net_profit_max": 40000.0,
    }])
    count = fetch_forecast("000001.SZ", client=mock_client, conn=mem_conn)
    assert count == 1
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_express_forecast.py -v`
预期: FAIL

**Step 3: 实现抓取器**

```python
# src/data_ingestion/tushare/express_forecast.py
#!/usr/bin/env python3
"""
Tushare 业绩快报 + 业绩预告抓取模块

用途: 补充财报滞后期间的盈利数据
- express (业绩快报): 正式财报前的速报数据
- forecast (业绩预告): 预计盈利区间
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_tables(conn: sqlite3.Connection = None):
    """初始化业绩快报/预告表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_express (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            revenue REAL,
            operate_profit REAL,
            total_profit REAL,
            n_income REAL,
            total_assets REAL,
            yoy_net_profit REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_express_code ON ts_express(ts_code)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            type TEXT,
            p_change_min REAL,
            p_change_max REAL,
            net_profit_min REAL,
            net_profit_max REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_forecast_code ON ts_forecast(ts_code)")

    conn.commit()
    if own_conn:
        conn.close()
    log("✅ 业绩快报/预告表初始化完成")


def fetch_express(
    ts_code: str,
    client: TushareAdapter = None,
    conn: sqlite3.Connection = None,
) -> int:
    """抓取单只股票的业绩快报"""
    if client is None:
        client = get_tushare_client()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        df = client.express(ts_code=ts_code)
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_express
                    (ts_code, ann_date, end_date, revenue, operate_profit,
                     total_profit, n_income, total_assets, yoy_net_profit, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code", ts_code),
                    row.get("ann_date"),
                    row.get("end_date"),
                    row.get("revenue"),
                    row.get("operate_profit"),
                    row.get("total_profit"),
                    row.get("n_income"),
                    row.get("total_assets"),
                    row.get("yoy_net_profit"),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 express {ts_code} 失败: {e}")

        conn.commit()
        return count
    finally:
        if own_conn:
            conn.close()


def fetch_forecast(
    ts_code: str,
    client: TushareAdapter = None,
    conn: sqlite3.Connection = None,
) -> int:
    """抓取单只股票的业绩预告"""
    if client is None:
        client = get_tushare_client()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        df = client.forecast(ts_code=ts_code)
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_forecast
                    (ts_code, ann_date, end_date, type, p_change_min,
                     p_change_max, net_profit_min, net_profit_max, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code", ts_code),
                    row.get("ann_date"),
                    row.get("end_date"),
                    row.get("type"),
                    row.get("p_change_min"),
                    row.get("p_change_max"),
                    row.get("net_profit_min"),
                    row.get("net_profit_max"),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 forecast {ts_code} 失败: {e}")

        conn.commit()
        return count
    finally:
        if own_conn:
            conn.close()


def fetch_all(client: TushareAdapter = None) -> int:
    """批量抓取全市场业绩快报和预告"""
    log("=" * 50)
    log("Tushare 业绩快报/预告批量抓取")
    log("=" * 50)

    if client is None:
        client = get_tushare_client()

    init_tables()
    conn = get_connection()

    try:
        stocks = pd.read_sql_query(
            "SELECT ts_code FROM ts_stock_basic WHERE list_status='L'", conn
        )
        total = len(stocks)
        log(f"📊 活跃股票: {total} 只")

        total_count = 0
        for i, row in stocks.iterrows():
            ts_code = row["ts_code"]
            if (i + 1) % 100 == 0:
                log(f"  进度: {i+1}/{total}")
            count = fetch_express(ts_code, client=client, conn=conn)
            count += fetch_forecast(ts_code, client=client, conn=conn)
            total_count += count

        log(f"\n✅ 完成! 共 {total_count} 条记录")
        return total_count
    finally:
        conn.close()


def main():
    fetch_all()


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_express_forecast.py -v`
预期: 3 passed

**Step 5: 提交**

```bash
git add src/data_ingestion/tushare/express_forecast.py tests/test_express_forecast.py
git commit -m "feat: add express (业绩快报) and forecast (业绩预告) fetchers"
```

---

### Task 9: 数据新鲜度视图 + 选股器滞后加权

**文件:**
- 修改: `src/database/connection.py` — 添加 `data_freshness` 视图
- 修改: `src/strategies/potential_screener.py` — 滞后加权评分
- 测试: `tests/test_screener_staleness.py`

**Step 1: 写失败测试**

```python
# tests/test_screener_staleness.py
import sqlite3
import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def conn_with_stale_data():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("CREATE TABLE ts_stock_basic (ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT)")
    conn.execute("CREATE TABLE ts_fina_indicator (ts_code TEXT, end_date TEXT, roe REAL, netprofit_yoy REAL)")
    conn.execute("CREATE TABLE ts_daily_basic (ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL)")
    conn.execute("CREATE TABLE ts_daily (ts_code TEXT, trade_date TEXT, close REAL, high REAL, low REAL, vol REAL, amount REAL)")
    conn.execute("CREATE TABLE industry_valuation (trade_date TEXT, industry TEXT, pe_median REAL, pe_p25 REAL, pe_p75 REAL, stock_count INTEGER, valid_pe_count INTEGER, UNIQUE(trade_date, industry))")

    # 股票 A: 财报滞后严重 (end_date=20250331, 距今约 3 个季度)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ','A','银行','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('A.SZ','20250331',15.0,20.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('A.SZ','20260305',15.0,1.2)")

    # 股票 B: 财报新鲜 (end_date=20251231)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('B.SZ','B','银行','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('B.SZ','20251231',15.0,20.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('B.SZ','20260305',15.0,1.2)")

    conn.execute("INSERT INTO industry_valuation VALUES ('20260305','银行',20.0,12.0,30.0,10,8)")
    conn.commit()
    return conn


def test_stale_stock_gets_lower_fundamental_weight(conn_with_stale_data):
    """财报滞后 >= 3 个季度的股票，基本面权重应降低"""
    from src.strategies.potential_screener import score_fundamentals
    candidates = pd.Series(["A.SZ", "B.SZ"])
    result = score_fundamentals(conn_with_stale_data, candidates)

    a_score = result[result["ts_code"] == "A.SZ"]["score_fundamental"].iloc[0]
    b_score = result[result["ts_code"] == "B.SZ"]["score_fundamental"].iloc[0]

    # A 的数据滞后严重，同样的 ROE/PE/增长 应该得分更低
    assert a_score < b_score, f"Stale A ({a_score}) should score less than fresh B ({b_score})"


def test_staleness_flag_in_output(conn_with_stale_data):
    """输出应包含 financial_lag_quarters 字段"""
    from src.strategies.potential_screener import score_fundamentals
    candidates = pd.Series(["A.SZ", "B.SZ"])
    result = score_fundamentals(conn_with_stale_data, candidates)
    assert "financial_lag_quarters" in result.columns
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_screener_staleness.py -v`
预期: FAIL

**Step 3: 修改 `score_fundamentals` — 添加滞后加权**

在 `score_fundamentals` 函数中，`fina_query` 之后、计算 `fund_roe` 之前，加入滞后计算:

```python
    # ── 数据新鲜度: 计算财报滞后季度数
    # 获取最新交易日作为参考日
    ref_date_row = conn.execute("SELECT MAX(trade_date) FROM ts_daily_basic").fetchone()
    ref_date = ref_date_row[0] if ref_date_row else datetime.now().strftime("%Y%m%d")

    fina_freshness_query = """
        SELECT ts_code, MAX(end_date) as latest_end_date
        FROM ts_fina_indicator
        GROUP BY ts_code
    """
    freshness = pd.read_sql_query(fina_freshness_query, conn)
    scores = scores.merge(freshness, on="ts_code", how="left")

    # 计算滞后季度数: (ref_date - latest_end_date) / 90
    def calc_lag_quarters(row):
        if pd.isna(row.get("latest_end_date")):
            return 4  # 无财报数据，视为严重滞后
        try:
            ref = datetime.strptime(str(ref_date)[:8], "%Y%m%d")
            end = datetime.strptime(str(row["latest_end_date"])[:8], "%Y%m%d")
            return max(0, int((ref - end).days / 90))
        except (ValueError, TypeError):
            return 4
    scores["financial_lag_quarters"] = scores.apply(calc_lag_quarters, axis=1)
```

然后在 `scores["score_fundamental"]` 计算之后，添加滞后折扣:

```python
    # 滞后加权: 滞后 >= 3 个季度，基本面总分减半
    stale = scores["financial_lag_quarters"] >= 3
    scores.loc[stale, "score_fundamental"] = (scores.loc[stale, "score_fundamental"] * 0.5).round(2)
```

同时从 `cols_drop` 中排除 `latest_end_date`（需要保留 `financial_lag_quarters`）:

```python
    cols_drop = ["roe", "netprofit_yoy", "pe_ttm", "industry", "latest_end_date"]
```

**Step 4: 运行测试确认通过**

运行: `python -m pytest tests/test_screener_staleness.py tests/test_screener_fundamentals.py -v`
预期: all passed

**Step 5: 添加 data_freshness 视图到 connection.py**

在 `_ensure_compat_views()` 函数末尾添加:

```python
    try:
        if not _table_exists(conn, "data_freshness"):
            needed = ["ts_stock_basic", "ts_daily", "ts_fina_indicator"]
            if all(_table_exists(conn, t) for t in needed):
                _create_or_replace_view(
                    conn,
                    "data_freshness",
                    """
                    SELECT
                        b.ts_code,
                        b.name,
                        MAX(d.trade_date) AS latest_daily,
                        MAX(f.end_date) AS latest_financial,
                        CAST((julianday('now') - julianday(
                            substr(MAX(f.end_date),1,4)||'-'||
                            substr(MAX(f.end_date),5,2)||'-'||
                            substr(MAX(f.end_date),7,2)
                        )) / 90 AS INTEGER) AS financial_lag_quarters
                    FROM ts_stock_basic b
                    LEFT JOIN ts_daily d ON b.ts_code = d.ts_code
                    LEFT JOIN ts_fina_indicator f ON b.ts_code = f.ts_code
                    GROUP BY b.ts_code
                    """,
                )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass
```

**Step 6: 提交**

```bash
git add src/strategies/potential_screener.py src/database/connection.py \
        tests/test_screener_staleness.py
git commit -m "feat: add staleness-weighted scoring and data_freshness view"
```

---

### Task 10: 集成业绩快报/预告到 update_all_data.py

**文件:**
- 修改: `scripts/update_all_data.py`

**Step 1: 在 steps 列表中添加**

```python
    ("src.data_ingestion.tushare.express_forecast", "业绩快报/预告"),
```

**Step 2: 提交**

```bash
git add scripts/update_all_data.py
git commit -m "feat: add express/forecast to daily update pipeline"
```

---

## Phase 4: 选股器加固 — 低优先级批量修复

### Task 11: 批量修复 5 个低优先级问题

**文件:**
- 修改: `src/strategies/potential_screener.py`
- 测试: `tests/test_screener_edge_cases.py`

**Step 1: 写失败测试**

```python
# tests/test_screener_edge_cases.py
import sqlite3
import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def conn_with_edge_cases():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("CREATE TABLE ts_stock_basic (ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT, list_date TEXT)")
    conn.execute("CREATE TABLE ts_daily (ts_code TEXT, trade_date TEXT, close REAL, high REAL, low REAL, vol REAL, amount REAL)")
    conn.execute("CREATE TABLE ts_daily_basic (ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL)")
    conn.execute("CREATE TABLE ts_fina_indicator (ts_code TEXT, end_date TEXT, roe REAL, netprofit_yoy REAL, grossprofit_margin REAL)")
    conn.execute("CREATE TABLE margin_trading (stock_code TEXT, date TEXT, margin_balance REAL)")

    # 股票 C: list_status 为 NULL 但近期有交易
    conn.execute("INSERT INTO ts_stock_basic VALUES ('C.SZ','C','银行',NULL,'20200101')")
    conn.execute("INSERT INTO ts_daily VALUES ('C.SZ','20260305',10.0,10.5,9.5,1000,60000)")
    conn.execute("INSERT INTO ts_daily VALUES ('C.SZ','20260304',9.8,10.0,9.5,1000,55000)")

    conn.commit()
    return conn


def test_null_list_status_with_recent_trading(conn_with_edge_cases):
    """#14: list_status 为 NULL 但有近期交易数据的股票应被视为在市"""
    conn = conn_with_edge_cases
    # 查近5日有数据 = 视为在市
    query = """
        SELECT b.ts_code
        FROM ts_stock_basic b
        WHERE (b.list_status = 'L' OR b.list_status IS NULL)
          AND b.ts_code IN (
              SELECT DISTINCT ts_code FROM ts_daily
              WHERE trade_date >= (
                  SELECT trade_date FROM (
                      SELECT DISTINCT trade_date FROM ts_daily
                      ORDER BY trade_date DESC LIMIT 5
                  ) ORDER BY trade_date ASC LIMIT 1
              )
          )
    """
    result = pd.read_sql_query(query, conn)
    assert len(result) == 1
    assert result.iloc[0]["ts_code"] == "C.SZ"


def test_score_capital_margin_na_for_non_margin_stock():
    """#10: 非两融标的的融资分数应为 NaN (不给 0 分)"""
    # 这个测试验证逻辑: 如果 margin_trading 表中无该股票，capital_margin 应为 NaN
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ts_moneyflow (ts_code TEXT, trade_date TEXT, buy_lg_amount REAL, buy_elg_amount REAL, sell_lg_amount REAL, sell_elg_amount REAL)")
    conn.execute("CREATE TABLE margin_trading (stock_code TEXT, date TEXT, margin_balance REAL)")
    conn.execute("CREATE TABLE ts_hsgt_top10 (ts_code TEXT, trade_date TEXT, net_amount REAL)")

    from src.strategies.potential_screener import score_capital_flow
    candidates = pd.Series(["X.SZ"])
    result = score_capital_flow(conn, candidates)
    # X.SZ 不在 margin_trading 中，capital_margin 应为 NaN
    assert pd.isna(result[result["ts_code"] == "X.SZ"]["capital_margin"].iloc[0])
    conn.close()
```

**Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_screener_edge_cases.py -v`
预期: FAIL

**Step 3: 修改选股器**

修改 `get_candidate_pool()` (L49-85): 支持 list_status NULL 通过近期交易判断在市:

将 L60 处的 WHERE 子句改为:
```sql
        WHERE b.name NOT LIKE '%ST%'
          AND b.name NOT LIKE '%退%'
          AND b.list_date IS NOT NULL
          AND b.list_date <= ?
          AND (b.list_status = 'L' OR b.list_status IS NULL)
```

修改 `score_capital_flow()` (L90-167): 融资余额 NaN 处理:

在 L139 之后，替换 `scores["capital_margin"] = percentile_score(...)` 为:

```python
    # 非两融标的: NaN 而不是 0
    has_margin = scores["margin_growth"].notna()
    scores["capital_margin"] = np.where(
        has_margin,
        percentile_score(scores["margin_growth"], 10),
        np.nan,
    )
```

同时调整 `score_capital` 汇总行，用 `nansum` 风格:

```python
    scores["score_capital"] = (
        scores["capital_main"].fillna(0)
        + scores["capital_margin"].fillna(0)
        + scores["capital_north"].fillna(0)
    ).round(2)
```

**Step 4: 运行所有选股器测试确认通过**

运行: `python -m pytest tests/test_screener_edge_cases.py tests/test_screener_fundamentals.py tests/test_screener_staleness.py -v`
预期: all passed

**Step 5: 提交**

```bash
git add src/strategies/potential_screener.py tests/test_screener_edge_cases.py
git commit -m "fix: screener edge cases - NULL list_status, non-margin stocks"
```

---

### Task 12: 选股输出添加 data_quality 元数据

**文件:**
- 修改: `src/strategies/potential_screener.py` — `run_screening` 函数
- 测试: `tests/test_screener_data_quality.py`

**Step 1: 写失败测试**

```python
# tests/test_screener_data_quality.py
def test_run_screening_has_data_quality_fields():
    """选股输出应包含 data_quality 相关字段"""
    # 只验证字段存在于结果列中
    expected_cols = ["data_completeness", "financial_lag_quarters"]
    # 由于需要完整数据库才能 run_screening, 这里只检查 score_fundamentals 的输出
    import sqlite3
    import pandas as pd
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ts_stock_basic (ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT)")
    conn.execute("CREATE TABLE ts_fina_indicator (ts_code TEXT, end_date TEXT, roe REAL, netprofit_yoy REAL)")
    conn.execute("CREATE TABLE ts_daily_basic (ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL)")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ','A','银行','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('A.SZ','20251231',15.0,20.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('A.SZ','20260305',15.0,1.2)")
    conn.commit()

    from src.strategies.potential_screener import score_fundamentals
    result = score_fundamentals(conn, pd.Series(["A.SZ"]))
    for col in expected_cols:
        assert col in result.columns, f"Missing column: {col}"
    conn.close()
```

**Step 2: 运行测试**

运行: `python -m pytest tests/test_screener_data_quality.py -v`
预期: PASS (如果 Task 5 和 Task 9 已完成)

**Step 3: 修改 `run_screening` 确保 data_quality 字段保留到最终输出**

在 `run_screening()` (L386-422) 中，确保 merge 时保留 `data_completeness` 和 `financial_lag_quarters`:

```python
    # 当前代码已经 merge fundamental 的所有列
    # 只需确认 print_results 也展示这些字段
```

在 `print_results()` 中追加数据质量摘要:

```python
    # 数据质量摘要
    if "data_completeness" in full_df.columns:
        pe_missing = (full_df["data_completeness"] == "pe_missing").sum()
        print(f"\n  数据质量:")
        print(f"    PE缺失: {pe_missing}/{len(full_df)} ({pe_missing/len(full_df)*100:.1f}%)")
    if "financial_lag_quarters" in full_df.columns:
        stale = (full_df["financial_lag_quarters"] >= 3).sum()
        print(f"    财报滞后≥3季: {stale}/{len(full_df)} ({stale/len(full_df)*100:.1f}%)")
```

**Step 4: 提交**

```bash
git add src/strategies/potential_screener.py tests/test_screener_data_quality.py
git commit -m "feat: add data_quality metadata to screener output"
```

---

### Task 13: 最终集成验证

**Step 1: 运行全部新测试**

```bash
python -m pytest tests/test_holder_number.py tests/test_northbound.py \
    tests/test_industry_valuation.py tests/test_express_forecast.py \
    tests/test_screener_fundamentals.py tests/test_screener_staleness.py \
    tests/test_screener_edge_cases.py tests/test_screener_data_quality.py -v
```

预期: all passed

**Step 2: 运行完整测试套件**

```bash
python -m pytest --tb=short
```

预期: 无新增失败

**Step 3: 验收标准检查**

```bash
# 验收 #6: 选股器已接入 holder_num_change
grep -r "holder_num_change\|ts_holder_number" src/strategies/
# 预期: 未来 screener 可通过 ts_holder_number 表查询（本 Phase 不修改北向评分逻辑,
#        但数据管道已就位）

# 验收 #3: 行业估值使用中位数
grep -r "pe_median" scripts/compute_industry_valuation.py src/strategies/
# 预期: 有结果

# 验收 #4: NULL PE 不再得 0 分
grep -r "pe_missing" src/strategies/potential_screener.py
# 预期: 有结果
```

**Step 4: 提交最终验证**

```bash
git add -A
git commit -m "test: final integration validation for data quality fixes"
```

---

## 涉及文件汇总

| 文件 | 操作 | Task |
|------|------|------|
| `src/data_ingestion/tushare/holder_number.py` | 新建 | 1 |
| `src/data_ingestion/tushare/northbound.py` | 新建 | 2 |
| `src/data_ingestion/tushare/express_forecast.py` | 新建 | 8 |
| `src/data_ingestion/tushare/client.py` | 修改 (添加 express/forecast) | 7 |
| `scripts/compute_industry_valuation.py` | 新建 | 4 |
| `scripts/update_all_data.py` | 修改 (添加 4 个步骤) | 3, 6, 10 |
| `src/strategies/potential_screener.py` | 修改 (PE中位数, NULL处理, 滞后加权, 边界修复) | 5, 9, 11, 12 |
| `src/database/connection.py` | 修改 (data_freshness 视图) | 9 |
| `tests/test_holder_number.py` | 新建 | 1 |
| `tests/test_northbound.py` | 新建 | 2 |
| `tests/test_industry_valuation.py` | 新建 | 4 |
| `tests/test_express_forecast.py` | 新建 | 8 |
| `tests/test_screener_fundamentals.py` | 新建 | 5 |
| `tests/test_screener_staleness.py` | 新建 | 9 |
| `tests/test_screener_edge_cases.py` | 新建 | 11 |
| `tests/test_screener_data_quality.py` | 新建 | 12 |
