#!/usr/bin/env python3
"""
财务指标与行业数据获取脚本

使用 akshare 获取：
1. 业绩预告/业绩快报
2. 航运指数（BDI）
3. 个股日行情（换手率、量比等）

存入 stocks.db 数据库
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

from src.analysis.technical import macd as calc_macd
from src.analysis.technical import rsi as calc_rsi

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import STOCKS_DB_PATH, get_connection


def init_indicator_tables():
    """初始化指标相关表"""
    conn = get_connection()

    # 业绩预告
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            report_date TEXT NOT NULL,
            indicator TEXT,
            change_type TEXT,
            forecast_value TEXT,
            change_pct TEXT,
            change_reason TEXT,
            forecast_type TEXT,
            last_year_value REAL,
            announce_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, report_date, indicator)
        )
    """)

    # 航运指数（BDI等）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shipping_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            index_name TEXT NOT NULL,
            value REAL,
            change_pct REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, index_name)
        )
    """)

    # 个股日行情（用于计算换手率、均线等）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            close REAL,
            high REAL,
            low REAL,
            volume REAL,
            amount REAL,
            amplitude REAL,
            change_pct REAL,
            turnover_rate REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)

    # 财务指标（ROE、现金流、增长率等）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_financials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            roe REAL,
            roe_avg REAL,
            net_profit REAL,
            net_profit_yoy REAL,
            revenue REAL,
            revenue_yoy REAL,
            deducted_profit REAL,
            operating_cashflow REAL,
            cashflow_profit_ratio REAL,
            gross_margin REAL,
            net_margin REAL,
            debt_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, report_date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_technicals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            ma5 REAL,
            ma10 REAL,
            ma20 REAL,
            ma60 REAL,
            rsi14 REAL,
            macd REAL,
            macd_signal REAL,
            macd_hist REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_rps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            rps_10 REAL,
            rps_20 REAL,
            rps_50 REAL,
            rps_120 REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)

    # 索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_code ON earnings_forecast(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_forecast(report_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shipping_date ON shipping_index(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_code ON stock_daily(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON stock_daily(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_financials_code ON stock_financials(stock_code)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_technicals_code_date ON stock_technicals(stock_code, date)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rps_code_date ON stock_rps(stock_code, date)")

    conn.commit()
    conn.close()
    logger.info("指标数据表初始化完成")


def fetch_earnings_forecast(report_date: str = None):
    """获取业绩预告"""
    if not report_date:
        # 默认获取当季末
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        year = now.year if quarter > 1 else now.year - 1
        quarter = quarter if quarter > 1 else 4
        quarter_end = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        report_date = f"{year}{quarter_end[quarter]}"

    logger.info("获取业绩预告（报告期：%s）...", report_date)
    try:
        df = ak.stock_yjyg_em(date=report_date)
        conn = get_connection()

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO earnings_forecast 
                    (stock_code, stock_name, report_date, indicator, change_type,
                     forecast_value, change_pct, change_reason, forecast_type,
                     last_year_value, announce_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(row.get("股票代码", "")),
                        row.get("股票简称", ""),
                        report_date,
                        row.get("预测指标", ""),
                        row.get("业绩变动", ""),
                        str(row.get("预测数值", "")),
                        str(row.get("业绩变动幅度", "")),
                        row.get("业绩变动原因", ""),
                        row.get("预告类型", ""),
                        row.get("上年同期值", None),
                        str(row.get("公告日期", "")),
                        datetime.now().isoformat(),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("保存业绩预告记录失败: %s", e)

        conn.commit()
        conn.close()
        logger.info("保存 %d 条业绩预告", count)
        return count
    except Exception as e:
        logger.warning("获取业绩预告失败: %s", e)
        return 0


def fetch_shipping_indices():
    """获取航运指数"""
    logger.info("获取航运指数...")

    indices = [
        ("BDI", ak.macro_shipping_bdi, "波罗的海干散货指数"),
        ("BPI", ak.macro_shipping_bpi, "波罗的海巴拿马型运费指数"),
        ("BCI", ak.macro_shipping_bci, "波罗的海海岬型运费指数"),
    ]

    conn = get_connection()
    total = 0

    for code, api_func, name in indices:
        try:
            df = api_func()
            count = 0
            for _, row in df.tail(100).iterrows():  # 只保存最近100条
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO shipping_index 
                        (date, index_name, value, change_pct, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            str(row.get("日期", "")),
                            code,
                            row.get("最新值", None),
                            row.get("涨跌幅", None),
                            datetime.now().isoformat(),
                        ),
                    )
                    count += 1
                except Exception:  # noqa: BLE001
                    pass
            logger.info("   %s(%s): %d 条", code, name, count)
            total += count
        except Exception as e:
            logger.warning("%s 获取失败: %s", code, e)

    conn.commit()
    conn.close()
    logger.info("共保存 %d 条航运指数数据", total)
    return total


def fetch_commodity_futures():
    """获取行业关键商品期货价格（工业硅、碳酸锂等）"""
    logger.info("获取行业商品期货价格...")

    # 行业关键期货品种
    commodities = [
        ("SI0", "工业硅", "光伏"),
        ("LC0", "碳酸锂", "锂电"),
        ("AU0", "黄金", "贵金属"),
        ("CU0", "铜", "有色金属"),
        ("I0", "铁矿石", "钢铁"),
        ("RB0", "螺纹钢", "钢铁"),
        ("OI0", "菜籽油", "油脂"),
        ("EB0", "苯乙烯", "化工"),
    ]

    conn = get_connection()

    # 创建商品价格表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commodity_futures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            industry TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commodity_date ON commodity_futures(date)")

    total = 0
    for symbol, name, industry in commodities:
        try:
            df = ak.futures_main_sina(symbol=symbol)
            if df.empty:
                continue

            count = 0
            for _, row in df.tail(60).iterrows():  # 最近60个交易日
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO commodity_futures 
                        (date, symbol, name, industry, open, high, low, close, volume, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            str(row.get("日期", "")),
                            symbol,
                            name,
                            industry,
                            row.get("开盘价", None),
                            row.get("最高价", None),
                            row.get("最低价", None),
                            row.get("收盘价", None),
                            row.get("成交量", None),
                            datetime.now().isoformat(),
                        ),
                    )
                    count += 1
                except Exception:  # noqa: BLE001
                    pass
            logger.info("   %s(%s): %d 条", symbol, name, count)
            total += count
        except Exception as e:
            logger.warning("%s 获取失败: %s", symbol, e)

    conn.commit()
    conn.close()
    logger.info("共保存 %d 条商品期货数据", total)
    return total


def fetch_stock_financials(stock_codes: list = None):
    """获取个股财务指标（ROE、现金流比率等）"""
    if not stock_codes:
        # 从龙虎榜获取热门股票
        conn = get_connection()
        cursor = conn.execute("""
            SELECT DISTINCT stock_code FROM lhb_institution 
            ORDER BY date DESC LIMIT 30
        """)
        stock_codes = [r[0] for r in cursor.fetchall()]
        conn.close()

    if not stock_codes:
        stock_codes = ["600519", "000001", "300750"]  # 默认

    logger.info("获取财务指标（%d 只股票）...", len(stock_codes))

    conn = get_connection()
    count = 0

    for i, code in enumerate(stock_codes):
        try:
            # 构造 symbol（沪市 sh，深市 sz）
            if code.startswith("6"):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"

            df = ak.stock_financial_abstract(symbol=symbol)
            if df.empty:
                continue

            # 转置数据框，去重列名
            df = df.set_index("指标").T
            df = df.drop("选项", errors="ignore")
            df = df.loc[:, ~df.columns.duplicated()]  # 去除重复列名

            # 辅助函数：安全获取数值
            def safe_get(series_or_val):
                if series_or_val is None:
                    return None
                if hasattr(series_or_val, "iloc"):
                    return series_or_val.iloc[0] if len(series_or_val) > 0 else None
                return series_or_val

            # 获取最近的报告期
            for report_date in list(df.index)[:4]:  # 最近4个季度
                try:
                    row = df.loc[report_date]

                    # 安全取值
                    cashflow = safe_get(row.get("经营现金流量净额", None))
                    profit = safe_get(row.get("净利润", None))
                    cashflow_ratio = None
                    if cashflow and profit and profit != 0:
                        try:
                            cashflow_ratio = round(float(cashflow) / float(profit), 4)
                        except Exception:  # noqa: BLE001
                            pass

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO stock_financials 
                        (stock_code, report_date, roe, roe_avg, net_profit, net_profit_yoy,
                         revenue, revenue_yoy, deducted_profit, operating_cashflow,
                         cashflow_profit_ratio, gross_margin, net_margin, debt_ratio, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            code,
                            report_date,
                            safe_get(row.get("净资产收益率(ROE)", None)),
                            safe_get(row.get("净资产收益率_平均", None)),
                            profit,
                            safe_get(row.get("归属母公司净利润增长率", None)),
                            safe_get(row.get("营业总收入", None)),
                            safe_get(row.get("营业总收入增长率", None)),
                            safe_get(row.get("扣非净利润", None)),
                            cashflow,
                            cashflow_ratio,
                            safe_get(row.get("毛利率", None)),
                            safe_get(row.get("销售净利率", None)),
                            safe_get(row.get("资产负债率", None)),
                            datetime.now().isoformat(),
                        ),
                    )
                    count += 1
                except Exception:  # noqa: BLE001
                    pass

            if (i + 1) % 10 == 0:
                logger.info("   [%d/%d] 已处理...", i + 1, len(stock_codes))

        except Exception as e:
            logger.warning("获取股票 %s 财务指标失败: %s", code, e)

    conn.commit()
    conn.close()
    logger.info("保存 %d 条财务指标数据", count)
    return count


def fetch_stock_daily(stock_code: str, days: int = 60):
    """获取个股日行情（含换手率），带数据验证"""
    try:
        from src.data_ingestion.akshare.models import StockDaily
        from src.database.connection import insert_validated, validate_and_create

        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")
        if df.empty:
            return 0

        conn = get_connection()
        count = 0

        for _, row in df.tail(days).iterrows():
            validated = validate_and_create(
                StockDaily,
                {
                    "stock_code": stock_code,
                    "date": str(row.get("日期", "")),
                    "open": row.get("开盘"),
                    "close": row.get("收盘"),
                    "high": row.get("最高"),
                    "low": row.get("最低"),
                    "volume": row.get("成交量"),
                    "amount": row.get("成交额"),
                    "amplitude": row.get("振幅"),
                    "change_pct": row.get("涨跌幅"),
                    "turnover_rate": row.get("换手率"),
                },
            )
            if validated and insert_validated(
                conn, "stock_daily", validated, ["stock_code", "date"]
            ):
                count += 1

        conn.commit()
        conn.close()
        return count
    except Exception as e:
        logger.warning("获取个股 %s 日行情失败: %s", stock_code, e)
        return 0


def fetch_hot_stocks_daily():
    """获取热门股票的日行情"""
    logger.info("获取热门股票日行情...")

    # 从龙虎榜获取热门股票
    conn = get_connection()
    cursor = conn.execute("""
        SELECT DISTINCT stock_code FROM lhb_institution 
        ORDER BY date DESC LIMIT 50
    """)
    hot_stocks = [r[0] for r in cursor.fetchall()]
    conn.close()

    if not hot_stocks:
        # 默认一些热门股
        hot_stocks = ["000001", "600519", "300750", "601318", "002594"]

    total = 0
    for i, code in enumerate(hot_stocks[:30]):  # 限制30只
        count = fetch_stock_daily(code)
        if count > 0:
            total += count
            logger.info("   [%d/%d] %s: %d 条", i + 1, min(30, len(hot_stocks)), code, count)

    logger.info("共保存 %d 条日行情数据", total)
    return total


def calculate_all_indicators():
    """计算所有股票的历史指标（RPS + 技术面）"""
    logger.info("开始计算历史指标 (ma5/10/20, rps_10/20/50)...")

    conn = get_connection()

    # 1. 获取所有股票的日K数据 (Pandas加速处理)
    # 为节省内存，这里只取需要的字段
    # 注意：SQlite读取大量数据可能较慢，但比循环几千次快
    logger.info("   加载日K数据...")
    try:
        df = pd.read_sql("SELECT stock_code, date, close, volume FROM stock_daily", conn)
    except Exception as e:
        logger.error("读取日K数据失败: %s", e)
        return

    if df.empty:
        logger.warning("无日K数据")
        return

    # 转换日期格式
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["stock_code", "date"])

    logger.info("   计算 %d 条日K线的指标...", len(df))

    # 定义计算函数（对每个group调用）
    def compute_group_metrics(group):
        # 1. 均线
        group["ma5"] = group["close"].rolling(window=5).mean().round(2)
        group["ma10"] = group["close"].rolling(window=10).mean().round(2)
        group["ma20"] = group["close"].rolling(window=20).mean().round(2)
        group["ma60"] = group["close"].rolling(window=60).mean().round(2)
        group["vol_ma5"] = group["volume"].rolling(window=5).mean().round(2)

        # 2. 涨幅 (用于RPS)
        group["chg_10"] = group["close"].pct_change(10).round(4)
        group["chg_20"] = group["close"].pct_change(20).round(4)
        group["chg_50"] = group["close"].pct_change(50).round(4)
        group["chg_60"] = group["close"].pct_change(60).round(4)  # 添加 60 日涨幅

        # MACD
        dif, dea, hist = calc_macd(group["close"])
        group["macd_dif"] = dif
        group["macd_dea"] = dea
        group["macd_hist"] = hist

        # RSI
        group["rsi14"] = calc_rsi(group["close"], 14)

        return group

    # 并行计算或直接groupby apply (Pandas优化过，通常够快)
    df_result = df.groupby("stock_code", group_keys=False).apply(compute_group_metrics)

    # 清理NaN (前几天无法计算均线)
    df_result = df_result.dropna(subset=["ma5"])  # 至少要有MA5

    # 准备写入技术指标库
    # is_bullish: ma5>ma10>ma20
    df_result["is_bullish"] = (
        (df_result["ma5"] > df_result["ma10"]) & (df_result["ma10"] > df_result["ma20"])
    ).astype(int)
    # breakup_ma20: complex logic, simplify to close > ma20
    df_result["breakup_ma20"] = (df_result["close"] > df_result["ma20"]).astype(int)

    # 转换为list tuples批量插入
    # tech_data: code, date, ma5, ma10, ma20, ma60, vol_ma5, is_ma_bullish, breakup_ma20
    tech_columns = [
        "stock_code",
        "date",
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "vol_ma5",
        "is_bullish",
        "breakup_ma20",
    ]

    # 格式化日期字符串
    df_result["date_str"] = df_result["date"].dt.strftime("%Y-%m-%d")

    logger.info("   写入技术指标表...")
    # 分批写入防内存溢出
    batch_size = 50000
    rows = []

    cursor = conn.cursor()
    count = 0

    for _, row in df_result.iterrows():
        rows.append(
            (
                row["stock_code"],
                row["date_str"],
                row["ma5"],
                row["ma10"],
                row["ma20"],
                row["ma60"],
                row["vol_ma5"],
                row["is_bullish"],
                row["breakup_ma20"],
                row.get("rsi14"),
                row.get("macd_dif"),
                row.get("macd_dea"),
                row.get("macd_hist"),
            )
        )

        if len(rows) >= batch_size:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO stock_technicals
                (stock_code, date, ma5, ma10, ma20, ma60, volume_ma5,
                 is_ma_bullish, breakup_ma20,
                 rsi14, macd, macd_signal, macd_hist,
                 updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                rows,
            )
            conn.commit()
            count += len(rows)
            rows = []
            logger.info("   已写入 %d 条...", count)

    if rows:
        cursor.executemany(
            """
            INSERT OR REPLACE INTO stock_technicals
            (stock_code, date, ma5, ma10, ma20, ma60, volume_ma5,
             is_ma_bullish, breakup_ma20,
             rsi14, macd, macd_signal, macd_hist,
             updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            rows,
        )
        conn.commit()
        count += len(rows)
    logger.info("技术指标写入完成: %d 条", count)

    # --- 计算 RPS (横截面) ---
    logger.info("   计算每日 RPS 排名 (10/20/50/60日)...")

    # 按日期分组计算 Rank
    # 仅保留需要的列
    rps_df = df_result[["date", "stock_code", "chg_10", "chg_20", "chg_50", "chg_60"]].dropna(
        subset=["chg_10"]
    )

    def compute_daily_rps(day_group):
        total = len(day_group)
        if total < 10:
            return day_group  # 数据太少不计算

        # rps_10
        day_group["rank_10"] = (day_group["chg_10"].rank(pct=True) * 100).round(2)
        # rps_20
        day_group["rank_20"] = (day_group["chg_20"].rank(pct=True) * 100).round(2)
        # rps_50
        day_group["rank_50"] = (day_group["chg_50"].rank(pct=True) * 100).round(2)
        # rps_60
        day_group["rank_60"] = (day_group["chg_60"].rank(pct=True) * 100).round(2)

        return day_group

    if not rps_df.empty:
        rps_result = rps_df.groupby("date", group_keys=False).apply(compute_daily_rps)

        # 写入 RPS 表
        # stock_code, date, rps_10, rps_20, rps_50
        logger.info("   写入 RPS 表...")
        rps_result["date_str"] = rps_result["date"].dt.strftime("%Y-%m-%d")

        rows_rps = []
        count_rps = 0

        for _, row in rps_result.iterrows():
            # fillna(0) for safety
            r10 = row.get("rank_10", 0)
            r20 = row.get("rank_20", 0)
            r50 = row.get("rank_50", 0)
            r60 = row.get("rank_60", 0)  # 添加 rps_60

            rows_rps.append((row["stock_code"], row["date_str"], r10, r20, r50, r60))

            if len(rows_rps) >= batch_size:
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO stock_rps
                    (stock_code, date, rps_10, rps_20, rps_50, rps_60, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    rows_rps,
                )
                conn.commit()
                count_rps += len(rows_rps)
                rows_rps = []
                logger.info("   已写入 %d 条...", count_rps)

        if rows_rps:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO stock_rps
                (stock_code, date, rps_10, rps_20, rps_50, rps_60, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                rows_rps,
            )
            conn.commit()
            count_rps += len(rows_rps)

        logger.info("RPS 计算完成: %d 条", count_rps)

    conn.close()


def print_stats():
    """打印统计信息"""
    conn = get_connection()

    logger.info("指标数据统计:")

    tables = [
        ("earnings_forecast", "业绩预告"),
        ("shipping_index", "航运指数"),
        ("commodity_futures", "商品期货"),
        ("stock_daily", "个股日行情"),
        ("stock_rps", "RPS 相对强度"),
        ("stock_technicals", "技术指标"),
        ("stock_financials", "财务指标(ROE)"),
    ]

    for table, name in tables:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            logger.info("   %s: %d 条", name, count)
        except Exception:  # noqa: BLE001
            logger.info("   %s: 0 条", name)

    # 显示均线多头排列股票数
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM stock_technicals WHERE is_ma_bullish > 0")
        bullish = cursor.fetchone()[0]
        logger.info("   均线多头排列: %d 只", bullish)
    except Exception:  # noqa: BLE001
        pass

    conn.close()


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="财务指标与行业数据获取")
    parser.add_argument("--stats", action="store_true", help="只显示统计信息")
    parser.add_argument("--report-date", type=str, help="业绩预告报告期，如 20251231")
    args = parser.parse_args()

    if args.stats:
        print_stats()
        return

    print("=" * 50)
    print("财务指标与行业数据获取")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 50)

    init_indicator_tables()

    # 获取数据
    fetch_earnings_forecast(args.report_date)
    fetch_shipping_indices()
    fetch_commodity_futures()
    fetch_hot_stocks_daily()
    fetch_stock_financials()
    calculate_all_indicators()

    # 统计
    print_stats()
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
