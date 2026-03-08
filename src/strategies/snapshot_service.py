"""
筛选器快照生成服务

将 RPS 和潜力筛选的 CLI 输出产品化为数据库快照，
供 API 直接读取，避免每次请求重新计算。

生成频率: 每日 17:15 (收盘数据入库后)
保留期: RPS/potential 60 个交易日, full_analysis 14 天
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from src.database.connection import get_connection

logger = logging.getLogger(__name__)

GENERATOR_VERSION = "v1.0"


def _get_latest_trade_date(conn) -> Optional[str]:
    """从 stock_rps 表获取最新交易日期。"""
    row = conn.execute("SELECT MAX(date) FROM stock_rps").fetchone()
    if row and row[0]:
        return row[0]
    return None


def _date_str_to_date(s: str) -> date:
    """将 YYYYMMDD 或 YYYY-MM-DD 字符串转为 date 对象。"""
    s = s.replace("-", "")
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def generate_rps_snapshot(target_date: Optional[str] = None) -> int:
    """
    生成 RPS 强度排名日快照。

    从 stock_rps 表读取全量 RPS 数据，按 rps_10 降序排名，
    写入 screen_rps_snapshot 表。

    Args:
        target_date: 目标交易日 (YYYYMMDD)，默认取最新

    Returns:
        写入条数
    """
    conn = get_connection()
    try:
        trade_date = target_date or _get_latest_trade_date(conn)
        if not trade_date:
            logger.warning("RPS 快照: 无可用交易日数据")
            return 0

        now = datetime.now()
        snapshot_dt = now.date()
        source_dt = _date_str_to_date(trade_date)

        # 查询全量 RPS 数据（按 rps_10 降序）
        rows = conn.execute("""
            SELECT r.stock_code, s.name,
                   r.rps_10, r.rps_20, r.rps_50,
                   COALESCE(r.rps_120, 0) as rps_120
            FROM stock_rps r
            LEFT JOIN stocks s ON r.stock_code = s.code
            WHERE r.date = ?
            ORDER BY r.rps_10 DESC
        """, (trade_date,)).fetchall()

        if not rows:
            logger.warning("RPS 快照: 交易日 %s 无 RPS 数据", trade_date)
            return 0

        # 清除当日已有快照（幂等）
        conn.execute(
            "DELETE FROM screen_rps_snapshot WHERE snapshot_date = ?",
            (snapshot_dt.isoformat(),)
        )

        # 批量插入
        count = 0
        for rank, row in enumerate(rows, 1):
            conn.execute("""
                INSERT INTO screen_rps_snapshot
                (snapshot_date, source_trade_date, generated_at, generator_version,
                 ts_code, stock_name, rps_10, rps_20, rps_50, rps_120, rank,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_dt.isoformat(), source_dt.isoformat(), now.isoformat(),
                GENERATOR_VERSION,
                row[0], row[1], row[2], row[3], row[4], row[5], rank,
                now.isoformat(), now.isoformat()
            ))
            count += 1

        conn.commit()
        logger.info("RPS 快照: 生成 %d 条记录 (交易日 %s)", count, trade_date)
        return count

    except Exception as e:
        logger.error("RPS 快照生成失败: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_potential_snapshot(top_n: int = 100) -> int:
    """
    生成多因子潜力股筛选日快照。

    调用 potential_screener.run_screening()，将结果写入
    screen_potential_snapshot 表。

    Args:
        top_n: 保留前 N 名

    Returns:
        写入条数
    """
    from src.strategies.potential_screener import run_screening

    try:
        top_df, full_df, _ = run_screening(top_n=top_n, detail=False)
    except Exception as e:
        logger.error("潜力筛选运行失败: %s", e)
        raise

    if full_df is None or full_df.empty:
        logger.warning("潜力快照: 筛选结果为空")
        return 0

    # 使用 top_df (已排序)
    df = top_df if top_df is not None and not top_df.empty else full_df.head(top_n)

    conn = get_connection()
    try:
        now = datetime.now()
        snapshot_dt = now.date()

        # 获取数据基于的交易日
        source_date = _get_latest_trade_date(conn)
        source_dt = _date_str_to_date(source_date) if source_date else snapshot_dt

        # 清除当日已有快照（幂等）
        conn.execute(
            "DELETE FROM screen_potential_snapshot WHERE snapshot_date = ?",
            (snapshot_dt.isoformat(),)
        )

        count = 0
        for rank, (_, row) in enumerate(df.iterrows(), 1):
            signals = row.get("signals", "-")
            if isinstance(signals, list):
                signals = json.dumps(signals, ensure_ascii=False)

            conn.execute("""
                INSERT INTO screen_potential_snapshot
                (snapshot_date, source_trade_date, generated_at, generator_version,
                 ts_code, stock_name, total_score, capital_score, trading_score,
                 fundamental_score, technical_score, signals, rank,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_dt.isoformat(), source_dt.isoformat(), now.isoformat(),
                GENERATOR_VERSION,
                row.get("ts_code", ""), row.get("name", ""),
                float(row.get("total_score", 0)),
                float(row.get("score_capital", 0)),
                float(row.get("score_trading", 0)),
                float(row.get("score_fundamental", 0)),
                float(row.get("score_technical", 0)),
                signals, rank,
                now.isoformat(), now.isoformat()
            ))
            count += 1

        conn.commit()
        logger.info("潜力快照: 生成 %d 条记录", count)
        return count

    except Exception as e:
        logger.error("潜力快照生成失败: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_full_analysis_snapshot(stock_codes: list[str]) -> int:
    """
    生成个股完整分析快照。

    对给定股票列表调用 run_analysis()，将结果写入
    analysis_full_snapshot 表。

    Args:
        stock_codes: 股票代码列表 (如 ["301033", "600519"])

    Returns:
        写入条数
    """
    from src.strategies.full_analysis import run_analysis

    if not stock_codes:
        return 0

    conn = get_connection()
    try:
        now = datetime.now()
        snapshot_dt = now.date()
        source_date = _get_latest_trade_date(conn)
        source_dt = _date_str_to_date(source_date) if source_date else snapshot_dt

        count = 0
        for code in stock_codes:
            try:
                result = run_analysis(code)
                if "error" in result:
                    logger.warning("分析 %s 失败: %s", code, result["error"])
                    continue

                # 获取股票名称
                name_row = conn.execute(
                    "SELECT name FROM stocks WHERE code = ?", (code,)
                ).fetchone()
                stock_name = name_row[0] if name_row else ""

                # 幂等: 替换当日已有记录
                conn.execute(
                    "DELETE FROM analysis_full_snapshot "
                    "WHERE snapshot_date = ? AND ts_code = ?",
                    (snapshot_dt.isoformat(), code),
                )
                conn.execute("""
                    INSERT INTO analysis_full_snapshot
                    (snapshot_date, source_trade_date, generated_at, generator_version,
                     ts_code, stock_name, analysis_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    snapshot_dt.isoformat(), source_dt.isoformat(), now.isoformat(),
                    GENERATOR_VERSION, code, stock_name,
                    json.dumps(result, ensure_ascii=False),
                    now.isoformat(), now.isoformat(),
                ))
                count += 1
                logger.info("完整分析快照: %s (%s)", code, stock_name)
            except Exception as e:
                logger.error("完整分析快照 %s 失败: %s", code, e)

        conn.commit()
        logger.info("完整分析快照: 生成 %d/%d 条记录", count, len(stock_codes))
        return count

    except Exception as e:
        logger.error("完整分析快照批量失败: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()


def get_analysis_snapshot(ts_code: str, target_date: Optional[str] = None) -> Optional[dict]:
    """
    获取单只股票的完整分析快照。若不存在则懒生成。

    Args:
        ts_code: 股票代码
        target_date: 目标日期 (YYYY-MM-DD)，默认今天

    Returns:
        分析结果 dict 或 None
    """
    conn = get_connection()
    try:
        dt = target_date or datetime.now().date().isoformat()
        row = conn.execute(
            "SELECT analysis_json FROM analysis_full_snapshot "
            "WHERE snapshot_date = ? AND ts_code = ?",
            (dt, ts_code),
        ).fetchone()

        if row:
            return json.loads(row[0])

        # 懒生成
        logger.info("懒生成完整分析: %s", ts_code)
        count = generate_full_analysis_snapshot([ts_code])
        if count > 0:
            row = conn.execute(
                "SELECT analysis_json FROM analysis_full_snapshot "
                "WHERE snapshot_date = ? AND ts_code = ?",
                (datetime.now().date().isoformat(), ts_code),
            ).fetchone()
            if row:
                return json.loads(row[0])

        return None
    finally:
        conn.close()


def cleanup_old_snapshots(max_rps_days: int = 90, max_analysis_days: int = 14):
    """
    清理超过保留期的快照。

    Args:
        max_rps_days: RPS/potential 保留天数（日历日，约 60 交易日）
        max_analysis_days: full_analysis 保留天数
    """
    conn = get_connection()
    try:
        rps_cutoff = (date.today() - timedelta(days=max_rps_days)).isoformat()
        analysis_cutoff = (date.today() - timedelta(days=max_analysis_days)).isoformat()

        r1 = conn.execute(
            "DELETE FROM screen_rps_snapshot WHERE snapshot_date < ?",
            (rps_cutoff,)
        )
        r2 = conn.execute(
            "DELETE FROM screen_potential_snapshot WHERE snapshot_date < ?",
            (rps_cutoff,)
        )
        r3 = conn.execute(
            "DELETE FROM analysis_full_snapshot WHERE snapshot_date < ?",
            (analysis_cutoff,)
        )
        conn.commit()

        total = (r1.rowcount or 0) + (r2.rowcount or 0) + (r3.rowcount or 0)
        if total > 0:
            logger.info("快照清理: 删除 %d 条过期记录", total)

    except Exception as e:
        logger.error("快照清理失败: %s", e)
        conn.rollback()
    finally:
        conn.close()


def ensure_snapshot_tables():
    """确保快照表存在（首次运行时创建）。"""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS screen_rps_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                source_trade_date DATE NOT NULL,
                generated_at TIMESTAMP NOT NULL,
                generator_version VARCHAR(16) NOT NULL DEFAULT 'v1.0',
                ts_code VARCHAR(12) NOT NULL,
                stock_name VARCHAR(50),
                rps_10 REAL,
                rps_20 REAL,
                rps_50 REAL,
                rps_120 REAL,
                rank INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_date, ts_code)
            );
            CREATE INDEX IF NOT EXISTS ix_screen_rps_date_rank
                ON screen_rps_snapshot(snapshot_date, rank);

            CREATE TABLE IF NOT EXISTS screen_potential_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                source_trade_date DATE NOT NULL,
                generated_at TIMESTAMP NOT NULL,
                generator_version VARCHAR(16) NOT NULL DEFAULT 'v1.0',
                ts_code VARCHAR(12) NOT NULL,
                stock_name VARCHAR(50),
                total_score REAL,
                capital_score REAL,
                trading_score REAL,
                fundamental_score REAL,
                technical_score REAL,
                signals TEXT,
                rank INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_date, ts_code)
            );
            CREATE INDEX IF NOT EXISTS ix_screen_potential_date_rank
                ON screen_potential_snapshot(snapshot_date, rank);

            CREATE TABLE IF NOT EXISTS analysis_full_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                source_trade_date DATE NOT NULL,
                generated_at TIMESTAMP NOT NULL,
                generator_version VARCHAR(16) NOT NULL DEFAULT 'v1.0',
                ts_code VARCHAR(12) NOT NULL,
                stock_name VARCHAR(50),
                analysis_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_date, ts_code)
            );
            CREATE INDEX IF NOT EXISTS ix_analysis_full_date
                ON analysis_full_snapshot(snapshot_date);
        """)
        conn.commit()
    finally:
        conn.close()


def run_daily_snapshots():
    """
    每日快照生成入口（由 APScheduler 调用）。

    执行顺序: 建表 → RPS 快照 → 潜力快照 → 清理过期
    """
    logger.info("开始生成每日快照...")
    ensure_snapshot_tables()

    rps_count = 0
    potential_count = 0

    try:
        rps_count = generate_rps_snapshot()
    except Exception as e:
        logger.error("RPS 快照任务失败: %s", e)

    try:
        potential_count = generate_potential_snapshot()
    except Exception as e:
        logger.error("潜力快照任务失败: %s", e)

    cleanup_old_snapshots()

    logger.info("每日快照完成: RPS=%d, Potential=%d", rps_count, potential_count)
    return {"rps": rps_count, "potential": potential_count}
