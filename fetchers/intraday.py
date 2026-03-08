"""盘中快照轮询 — 从 AkShare 拉取实时行情写入 intraday_snapshot。

股票池: RPS Top 30 ∪ Potential Top 20 → 去重后 ≤50 只
频率: 交易日 9:30-15:00 每 10 分钟
熔断: 连续 5 次失败暂停 30 分钟
"""

import logging
from datetime import datetime

from src.database.connection import get_connection

logger = logging.getLogger(__name__)

INTRADAY_POOL_SIZE = 50
_consecutive_failures = 0
_MAX_FAILURES = 5


def get_intraday_pool() -> list[str]:
    """获取盘中轮询股票池 = RPS Top 30 ∪ Potential Top 20 去重。"""
    conn = get_connection()
    try:
        codes: set[str] = set()

        # RPS Top 30
        rows = conn.execute(
            "SELECT ts_code FROM screen_rps_snapshot "
            "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM screen_rps_snapshot) "
            "ORDER BY rank ASC LIMIT 30"
        ).fetchall()
        for r in rows:
            codes.add(r[0])

        # Potential Top 20
        rows = conn.execute(
            "SELECT ts_code FROM screen_potential_snapshot "
            "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM screen_potential_snapshot) "
            "ORDER BY rank ASC LIMIT 20"
        ).fetchall()
        for r in rows:
            codes.add(r[0])

        pool = list(codes)[:INTRADAY_POOL_SIZE]
        logger.info("盘中股票池: %d 只", len(pool))
        return pool

    except Exception as e:
        logger.error("获取盘中股票池失败: %s", e)
        return []
    finally:
        conn.close()


def fetch_intraday_snapshot():
    """拉取实时行情并写入 intraday_snapshot 表。"""
    global _consecutive_failures

    if _consecutive_failures >= _MAX_FAILURES:
        logger.warning("熔断中: 连续 %d 次失败，跳过本轮", _consecutive_failures)
        return

    pool = get_intraday_pool()
    if not pool:
        logger.info("盘中股票池为空，跳过")
        return

    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()

        if df is None or df.empty:
            _consecutive_failures += 1
            logger.warning("AkShare 实时行情返回空 (failures: %d)", _consecutive_failures)
            return

        # 过滤股票池
        # AkShare 的代码列为 "代码" (6位纯数字)
        pool_codes = {c.split(".")[0] for c in pool}  # 去掉 .SH/.SZ 后缀
        mask = df["代码"].isin(pool_codes)
        filtered = df[mask]

        if filtered.empty:
            logger.warning("过滤后无匹配股票")
            return

        conn = get_connection()
        now = datetime.now()
        count = 0

        try:
            # 确保表存在
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intraday_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_code VARCHAR(12) NOT NULL,
                    price REAL,
                    change_pct REAL,
                    volume REAL,
                    amount REAL,
                    update_time TIMESTAMP NOT NULL,
                    UNIQUE(ts_code, update_time)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_intraday_ts_time
                ON intraday_snapshot(ts_code, update_time)
            """)

            for _, row in filtered.iterrows():
                code = str(row["代码"])
                # 恢复 ts_code 格式
                ts_code = next((c for c in pool if c.startswith(code)), code)

                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO intraday_snapshot "
                        "(ts_code, price, change_pct, volume, amount, update_time) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            ts_code,
                            float(row.get("最新价", 0) or 0),
                            float(row.get("涨跌幅", 0) or 0),
                            float(row.get("成交量", 0) or 0),
                            float(row.get("成交额", 0) or 0),
                            now.isoformat(),
                        ),
                    )
                    count += 1
                except Exception as e:
                    logger.warning("写入 %s 失败: %s", ts_code, e)

            conn.commit()
            _consecutive_failures = 0  # 重置
            logger.info("盘中快照: 写入 %d/%d 条", count, len(filtered))

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        _consecutive_failures += 1
        logger.error("盘中快照失败 (failures: %d): %s", _consecutive_failures, e)


def reset_circuit_breaker():
    """手动重置熔断器。"""
    global _consecutive_failures
    _consecutive_failures = 0
    logger.info("盘中熔断器已重置")
