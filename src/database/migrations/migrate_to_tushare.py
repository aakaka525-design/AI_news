#!/usr/bin/env python3
"""
Tushare 数据库迁移脚本

功能：
1. 初始化所有 Tushare 格式的表
2. 将旧数据迁移到新表（可选）
3. 验证迁移结果

⚠️ 警告：此脚本会创建新表，不会删除旧表。
如需完全重建，请手动备份并删除 stocks.db。
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 数据库路径
STOCKS_DB_PATH = PROJECT_ROOT / "data" / "stocks.db"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(STOCKS_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 表定义
# ============================================================

TS_TABLES = {
    "ts_stock_basic": """
        CREATE TABLE IF NOT EXISTS ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            area TEXT,
            industry TEXT,
            fullname TEXT,
            market TEXT,
            exchange TEXT,
            list_status TEXT DEFAULT 'L',
            list_date TEXT,
            delist_date TEXT,
            is_hs TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "ts_daily": """
        CREATE TABLE IF NOT EXISTS ts_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            adj_factor REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """,
    
    "ts_daily_basic": """
        CREATE TABLE IF NOT EXISTS ts_daily_basic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            volume_ratio REAL,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            ps_ttm REAL,
            dv_ratio REAL,
            dv_ttm REAL,
            total_mv REAL,
            circ_mv REAL,
            total_share REAL,
            float_share REAL,
            free_share REAL,
            turnover_rate REAL,
            turnover_rate_f REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """,
    
    "ts_fina_indicator": """
        CREATE TABLE IF NOT EXISTS ts_fina_indicator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            eps REAL,
            dt_eps REAL,
            bps REAL,
            ocfps REAL,
            grps REAL,
            roe REAL,
            roe_waa REAL,
            roe_dt REAL,
            roa REAL,
            npta REAL,
            roic REAL,
            grossprofit_margin REAL,
            netprofit_margin REAL,
            op_of_gr REAL,
            or_yoy REAL,
            op_yoy REAL,
            tp_yoy REAL,
            netprofit_yoy REAL,
            dt_netprofit_yoy REAL,
            debt_to_assets REAL,
            current_ratio REAL,
            quick_ratio REAL,
            ar_turn REAL,
            inv_turn REAL,
            fa_turn REAL,
            assets_turn REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """,
    
    "ts_top_list": """
        CREATE TABLE IF NOT EXISTS ts_top_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            name TEXT,
            close REAL,
            pct_change REAL,
            turnover_rate REAL,
            amount REAL,
            l_sell REAL,
            l_buy REAL,
            l_amount REAL,
            net_amount REAL,
            net_rate REAL,
            amount_rate REAL,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code)
        )
    """,
    
    "ts_top_inst": """
        CREATE TABLE IF NOT EXISTS ts_top_inst (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            exalter TEXT,
            side TEXT,
            buy REAL,
            buy_rate REAL,
            sell REAL,
            sell_rate REAL,
            net_buy REAL,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code, exalter, side)
        )
    """,
    
    "ts_moneyflow": """
        CREATE TABLE IF NOT EXISTS ts_moneyflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            buy_sm_vol REAL,
            buy_md_vol REAL,
            buy_lg_vol REAL,
            buy_elg_vol REAL,
            sell_sm_vol REAL,
            sell_md_vol REAL,
            sell_lg_vol REAL,
            sell_elg_vol REAL,
            buy_sm_amount REAL,
            buy_md_amount REAL,
            buy_lg_amount REAL,
            buy_elg_amount REAL,
            sell_sm_amount REAL,
            sell_md_amount REAL,
            sell_lg_amount REAL,
            sell_elg_amount REAL,
            net_mf_vol REAL,
            net_mf_amount REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """,
    
    "ts_hsgt_top10": """
        CREATE TABLE IF NOT EXISTS ts_hsgt_top10 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            name TEXT,
            close REAL,
            change REAL,
            rank INTEGER,
            market_type TEXT,
            amount REAL,
            net_amount REAL,
            buy REAL,
            sell REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code, market_type)
        )
    """,
    "ts_cashflow": """
        CREATE TABLE IF NOT EXISTS ts_cashflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            n_cashflow_act REAL,
            n_cashflow_inv_act REAL,
            n_cash_flows_fnc_act REAL,
            c_paid_for_fixed_assets REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, ann_date, end_date)
        )
    """,
    "ts_hk_hold": """
        CREATE TABLE IF NOT EXISTS ts_hk_hold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            vol REAL,
            ratio REAL,
            exchange TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date, exchange)
        )
    """,
    "ts_cyq_perf": """
        CREATE TABLE IF NOT EXISTS ts_cyq_perf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            cost_5pct REAL,
            cost_15pct REAL,
            cost_50pct REAL,
            cost_85pct REAL,
            cost_95pct REAL,
            weight_avg REAL,
            winner_rate REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """,
    "ts_top10_holders": """
        CREATE TABLE IF NOT EXISTS ts_top10_holders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            holder_name TEXT NOT NULL,
            hold_amount REAL,
            hold_ratio REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, ann_date, end_date, holder_name)
        )
    """,
}

TS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ts_daily_code ON ts_daily(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_daily_date ON ts_daily(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_basic_code ON ts_daily_basic(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_basic_date ON ts_daily_basic(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_fina_code ON ts_fina_indicator(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_fina_date ON ts_fina_indicator(end_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_top_date ON ts_top_list(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_top_code ON ts_top_list(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_inst_date ON ts_top_inst(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_inst_code ON ts_top_inst(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_mf_code ON ts_moneyflow(ts_code)",
    "CREATE INDEX IF NOT EXISTS idx_ts_mf_date ON ts_moneyflow(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_hsgt_date ON ts_hsgt_top10(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_cashflow_code_date ON ts_cashflow(ts_code, end_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_hk_hold_date ON ts_hk_hold(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_cyq_perf_date ON ts_cyq_perf(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ts_top10_holders_code_date ON ts_top10_holders(ts_code, end_date)",
]


# ============================================================
# 迁移函数
# ============================================================

def init_all_tables():
    """初始化所有 Tushare 表"""
    log("=" * 50)
    log("初始化 Tushare 数据表")
    log("=" * 50)
    
    conn = get_connection()
    
    for table_name, create_sql in TS_TABLES.items():
        try:
            conn.execute(create_sql)
            log(f"   ✅ {table_name}")
        except Exception as e:
            log(f"   ❌ {table_name}: {e}")
    
    for index_sql in TS_INDEXES:
        try:
            conn.execute(index_sql)
        except Exception:
            pass
    
    conn.commit()
    conn.close()
    log("\n✅ 所有表初始化完成")


def migrate_daily_data():
    """
    将旧的 stock_daily 数据迁移到 ts_daily
    
    字段映射：
    - stock_code -> ts_code (添加后缀)
    - date -> trade_date (移除 -)
    - change_pct -> pct_chg
    - volume -> vol
    """
    log("\n📦 迁移日线数据...")
    
    conn = get_connection()
    
    # 检查旧表是否存在
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_daily'")
    if not cursor.fetchone():
        log("   ⚠️ 旧表 stock_daily 不存在，跳过迁移")
        return 0
    
    # 统计旧数据
    cursor = conn.execute("SELECT COUNT(*) FROM stock_daily")
    old_count = cursor.fetchone()[0]
    log(f"   旧数据: {old_count} 条")
    
    if old_count == 0:
        return 0
    
    # 迁移数据
    conn.execute("""
        INSERT OR IGNORE INTO ts_daily 
        (ts_code, trade_date, open, high, low, close, pct_chg, vol, amount, updated_at)
        SELECT 
            CASE 
                WHEN stock_code LIKE '6%' THEN stock_code || '.SH'
                ELSE stock_code || '.SZ'
            END as ts_code,
            REPLACE(date, '-', '') as trade_date,
            open, high, low, close,
            change_pct as pct_chg,
            volume as vol,
            amount,
            updated_at
        FROM stock_daily
    """)
    
    conn.commit()
    
    # 验证
    cursor = conn.execute("SELECT COUNT(*) FROM ts_daily")
    new_count = cursor.fetchone()[0]
    log(f"   新数据: {new_count} 条")
    
    conn.close()
    return new_count


def migrate_financials_data():
    """迁移财务数据"""
    log("\n📦 迁移财务数据...")
    
    conn = get_connection()
    
    # 检查旧表
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_financials'")
    if not cursor.fetchone():
        log("   ⚠️ 旧表 stock_financials 不存在，跳过迁移")
        return 0
    
    cursor = conn.execute("SELECT COUNT(*) FROM stock_financials")
    old_count = cursor.fetchone()[0]
    log(f"   旧数据: {old_count} 条")
    
    if old_count == 0:
        return 0
    
    # 迁移
    conn.execute("""
        INSERT OR IGNORE INTO ts_fina_indicator
        (ts_code, end_date, roe, netprofit_yoy, or_yoy, grossprofit_margin, 
         netprofit_margin, debt_to_assets, updated_at)
        SELECT
            CASE 
                WHEN stock_code LIKE '6%' THEN stock_code || '.SH'
                ELSE stock_code || '.SZ'
            END as ts_code,
            REPLACE(report_date, '-', '') as end_date,
            roe,
            net_profit_yoy as netprofit_yoy,
            revenue_yoy as or_yoy,
            gross_margin as grossprofit_margin,
            net_margin as netprofit_margin,
            debt_ratio as debt_to_assets,
            updated_at
        FROM stock_financials
    """)
    
    conn.commit()
    
    cursor = conn.execute("SELECT COUNT(*) FROM ts_fina_indicator")
    new_count = cursor.fetchone()[0]
    log(f"   新数据: {new_count} 条")
    
    conn.close()
    return new_count


def verify_migration():
    """验证迁移结果"""
    log("\n📊 验证迁移结果")
    log("-" * 40)
    
    conn = get_connection()
    
    tables = [
        'ts_stock_basic', 'ts_daily', 'ts_daily_basic',
        'ts_fina_indicator', 'ts_top_list', 'ts_moneyflow'
    ]
    
    for table in tables:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            # 获取日期范围（如果有）
            date_col = 'trade_date' if 'daily' in table or 'top' in table else 'end_date' if 'fina' in table else None
            date_range = ""
            if date_col:
                try:
                    cursor = conn.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM {table}")
                    min_d, max_d = cursor.fetchone()
                    if min_d and max_d:
                        date_range = f" ({min_d} ~ {max_d})"
                except Exception as e:
                    log(f"   {table}: 日期范围查询失败 ({date_col}): {e}")
            
            log(f"   {table}: {count:,} 条{date_range}")
        except Exception as e:
            log(f"   {table}: ❌ {e}")
    
    conn.close()


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 数据库迁移")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)
    
    # 检查环境变量
    token = os.getenv('TUSHARE_TOKEN')
    if not token:
        log("\n⚠️ 警告: 未设置 TUSHARE_TOKEN 环境变量")
        log("请在 .env 文件中添加: TUSHARE_TOKEN=your_token")
    
    # Step 1: 初始化表
    init_all_tables()
    
    # Step 2: 迁移旧数据
    log("\n开始数据迁移...")
    migrate_daily_data()
    migrate_financials_data()
    
    # Step 3: 验证
    verify_migration()
    
    log("\n" + "=" * 50)
    log("✅ 迁移完成!")
    log("=" * 50)
    log("\n后续步骤:")
    log("1. 运行 src/data_ingestion/tushare/daily.py 抓取最新行情")
    log("2. 运行 src/data_ingestion/tushare/financials.py 抓取财务数据")
    log("3. 旧表 (stock_daily, stock_financials 等) 可在验证无误后删除")


if __name__ == "__main__":
    main()
