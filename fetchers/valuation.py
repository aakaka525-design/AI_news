#!/usr/bin/env python3
"""
估值数据获取模块（baostock多实例并行）

获取A股个股历史PE/PB/PS数据
数据源：baostock
"""

import sqlite3
import subprocess
import tempfile
import time
import os
from datetime import datetime, timedelta
from pathlib import Path

# 使用公共数据库模块
from fetchers.db import STOCKS_DB_PATH

# Worker脚本模板 - 输出到CSV
WORKER_SCRIPT = '''
import baostock as bs
import logging
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

codes = sys.argv[1].split(",")
start_date = sys.argv[2]
end_date = sys.argv[3]
output_file = sys.argv[4]

bs.login()

results = []
for code in codes:
    try:
        bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,peTTM,pbMRQ,psTTM",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"
        )
        if rs.error_code == "0":
            while rs.next():
                row = rs.get_row_data()
                if row[1] or row[2]:
                    pe = row[1] if row[1] else ""
                    pb = row[2] if row[2] else ""
                    ps = row[3] if row[3] else ""
                    results.append(f"{code},{row[0]},{pe},{pb},{ps}")
    except Exception as e:
        logger.warning("获取估值数据失败 code=%s: %s", code, e)

bs.logout()

with open(output_file, "w") as f:
    f.write("\\n".join(results))
print(len(results))
'''


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_connection():
    """获取数据库连接（保持向后兼容）。"""
    import sqlite3
    conn = sqlite3.connect(STOCKS_DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_valuation_table():
    """初始化估值表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_valuation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            pe_ttm REAL,
            pb REAL,
            ps_ttm REAL,
            total_mv REAL,
            circ_mv REAL,
            industry TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_val_code ON stock_valuation(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_val_date ON stock_valuation(date)")
    conn.commit()
    conn.close()
    log("估值表初始化完成")


def get_stock_codes():
    """获取所有股票代码"""
    conn = get_connection()
    cursor = conn.execute("SELECT code FROM stocks")
    codes = [r[0] for r in cursor.fetchall()]
    conn.close()
    return codes


def fetch_valuation_history(days: int = 30, workers: int = 8):
    """获取历史估值数据（多实例并行）"""
    log(f"📊 获取历史估值数据（最近{days}天，{workers}进程）...")

    codes = get_stock_codes()
    log(f"   待获取: {len(codes)} 只股票")

    # 日期范围
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 创建临时目录
    tmp_dir = tempfile.mkdtemp()
    script_path = os.path.join(tmp_dir, 'worker.py')
    with open(script_path, 'w') as f:
        f.write(WORKER_SCRIPT)

    # 分片
    chunk_size = (len(codes) + workers - 1) // workers
    chunks = [codes[i:i+chunk_size] for i in range(0, len(codes), chunk_size)]

    log(f"   分配: {len(chunks)} 个进程，每进程约 {chunk_size} 只")

    start_time = time.time()

    # 启动所有worker
    processes = []
    output_files = []
    for i, chunk in enumerate(chunks):
        output_file = os.path.join(tmp_dir, f'output_{i}.csv')
        output_files.append(output_file)

        p = subprocess.Popen([
            'python3', script_path,
            ','.join(chunk),
            start_date,
            end_date,
            output_file
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append(p)

    log(f"   已启动 {len(processes)} 个进程，等待完成...")

    # 等待所有完成
    for p in processes:
        p.wait()

    elapsed = time.time() - start_time
    log(f"   获取完成，用时 {elapsed:.1f}秒，开始导入数据库...")

    # 合并写入数据库
    conn = get_connection()
    total = 0

    for output_file in output_files:
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(',')
                    if len(parts) >= 4:
                        code, date, pe, pb = parts[:4]
                        ps = parts[4] if len(parts) > 4 else None

                        conn.execute("""
                            INSERT OR REPLACE INTO stock_valuation
                            (stock_code, date, pe_ttm, pb, ps_ttm, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            code,
                            date,
                            float(pe) if pe else None,
                            float(pb) if pb else None,
                            float(ps) if ps else None,
                            datetime.now().isoformat()
                        ))
                        total += 1

    conn.commit()
    conn.close()

    # 清理
    for f in output_files:
        if os.path.exists(f):
            os.unlink(f)
    os.unlink(script_path)
    os.rmdir(tmp_dir)

    log(f"   ✅ 估值数据: 共 {total} 条")
    return total


def main():
    import argparse
    parser = argparse.ArgumentParser(description="估值数据获取（baostock）")
    parser.add_argument("--days", type=int, default=30, help="获取最近N天数据")
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    args = parser.parse_args()

    log("=" * 50)
    log(f"估值数据获取（baostock，{args.days}天，{args.workers}进程）")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)

    init_valuation_table()
    fetch_valuation_history(args.days, args.workers)

    # 统计
    conn = get_connection()
    cursor = conn.execute("""
        SELECT COUNT(*), COUNT(DISTINCT date), COUNT(DISTINCT stock_code), MIN(date), MAX(date)
        FROM stock_valuation
    """)
    count, days_count, stocks_count, min_date, max_date = cursor.fetchone()
    conn.close()

    log(f"📊 估值数据: {count} 条，{stocks_count} 只股票，{days_count} 个交易日")
    if min_date and max_date:
        log(f"   日期范围: {min_date} ~ {max_date}")
    log("✅ 完成!")


if __name__ == "__main__":
    main()
