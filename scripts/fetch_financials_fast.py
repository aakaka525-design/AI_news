#!/usr/bin/env python3
"""
高速财务数据抓取脚本 (智能分层模式)

策略:
1. 财务指标(PEG等): 全量抓取 (使用批量接口高效完成)
2. 现金流: 仅抓取"潜在候选股" (跌幅>30%) (由于不支持批量，仅抓取重点目标)

候选股筛选:
- 基于 ts_weekly 计算过去 3 年跌幅
- 如果跌幅 > 30%，标记为候选
- 仅对候选股抓取现金流 (数量减少 80%+)

速率控制:
- 全局约 280 请求/分钟 (安全值)
"""

import sys
import os
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.data_ingestion.tushare.client import get_tushare_client
from src.database.connection import get_connection

# 配置
BATCH_SIZE = 80          # 财务指标批量大小
BATCH_WORKERS = 5        # 批量抓取线程数
SINGLE_WORKERS = 10      # 单股抓取线程数
START_DATE = '20220101'  # 3年数据

log_lock = threading.Lock()
db_lock = threading.Lock()

def log(msg: str):
    with log_lock:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

class SmartFetcher:
    def __init__(self):
        self.client = get_tushare_client()
        
    def get_all_stocks(self) -> List[str]:
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT ts_code FROM ts_stock_basic")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_candidates(self) -> Set[str]:
        """筛选跌幅>30%的候选股"""
        log("🔍 筛选重点候选股 (跌幅 > 30%)...")
        conn = get_connection()
        try:
            # 简单计算: (当前价 - 3年高点)/3年高点 < -0.3
            sql = '''
            WITH max_p AS (
                SELECT ts_code, MAX(high) as h 
                FROM ts_weekly WHERE trade_date >= ? 
                GROUP BY ts_code
            ),
            curr_p AS (
                SELECT ts_code, close as c 
                FROM ts_weekly 
                WHERE trade_date = (SELECT MAX(trade_date) FROM ts_weekly)
            )
            SELECT m.ts_code 
            FROM max_p m JOIN curr_p c ON m.ts_code = c.ts_code
            WHERE (c.c - m.h)/m.h < -0.3
            '''
            cursor = conn.execute(sql, (START_DATE,))
            candidates = set(row[0] for row in cursor.fetchall())
            total = len(self.get_all_stocks()) or 1
            reduction = max(0.0, 100 - len(candidates) / total * 100)
            log(f"✅ 找到 {len(candidates)} 只候选股 (现金流抓取量减少约 {reduction:.1f}%)")
            return candidates
        except Exception as e:
            log(f"⚠️ 筛选候选股失败 ({e})，将抓取全量")
            return set()
        finally:
            conn.close()

    def save_fina(self, data: List[tuple]):
        if not data: return
        with db_lock:
            conn = get_connection()
            try:
                conn.executemany('''
                    INSERT OR REPLACE INTO ts_fina_indicator
                    (ts_code, ann_date, end_date, eps, roe, roa, netprofit_yoy, 
                     or_yoy, grossprofit_margin, debt_to_assets, current_ratio, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ''', data)
                conn.commit()
            except Exception as e:
                log(f"❌ 写入Fina失败: {e}")
            finally:
                conn.close()

    def save_cash(self, data: List[tuple]):
        if not data: return
        with db_lock:
            conn = get_connection()
            try:
                conn.executemany(
                    '''
                    INSERT INTO ts_cashflow
                    (ts_code, ann_date, end_date, n_cashflow_act,
                     n_cashflow_inv_act, n_cash_flows_fnc_act,
                     c_paid_for_fixed_assets, updated_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(ts_code, ann_date, end_date) DO UPDATE SET
                        n_cashflow_act = COALESCE(excluded.n_cashflow_act, ts_cashflow.n_cashflow_act),
                        n_cashflow_inv_act = COALESCE(excluded.n_cashflow_inv_act, ts_cashflow.n_cashflow_inv_act),
                        n_cash_flows_fnc_act = COALESCE(excluded.n_cash_flows_fnc_act, ts_cashflow.n_cash_flows_fnc_act),
                        c_paid_for_fixed_assets = COALESCE(excluded.c_paid_for_fixed_assets, ts_cashflow.c_paid_for_fixed_assets),
                        updated_at = excluded.updated_at
                    ''',
                    data,
                )
                conn.commit()
            except Exception as e:
                log(f"❌ 写入Cash失败: {e}")
            finally:
                conn.close()

    def fetch_fina_batch(self, codes: List[str]):
        """批量抓取财务指标"""
        ts_codes = ",".join(codes)
        res = []
        updated = datetime.now().isoformat()
        try:
            df = self.client.fina_indicator(ts_code=ts_codes, start_date=START_DATE)
            if df is not None:
                for _, row in df.iterrows():
                    res.append((
                        row.get('ts_code'), row.get('ann_date'), row.get('end_date'),
                        row.get('eps'), row.get('roe'), row.get('roa'), 
                        row.get('netprofit_yoy'), row.get('or_yoy'), 
                        row.get('grossprofit_margin'), row.get('debt_to_assets'), 
                        row.get('current_ratio'), updated
                    ))
            self.save_fina(res)
            time.sleep(2.0) # 5线程 * 2s = 2.5req/s = 150rpm
            return len(res)
        except Exception as e:
            log(f"⚠️ Fina批次失败: {e}")
            time.sleep(3)
            return 0

    def fetch_cash_single(self, code: str):
        """单股抓取现金流"""
        res = []
        updated = datetime.now().isoformat()
        try:
            df = self.client.cashflow(ts_code=code, start_date=START_DATE)
            if df is not None:
                for _, row in df.iterrows():
                    res.append((
                        row.get('ts_code'), row.get('ann_date'), row.get('end_date'),
                        row.get('n_cashflow_act'), row.get('n_cashflow_inv_act'),
                        row.get('n_cash_flows_fnc_act'),
                        row.get('c_pay_acq_const_fiolta'),
                        updated,
                    ))
            self.save_cash(res)
            time.sleep(2.0) # 10线程 * 2s = 5req/s = 300rpm
            return len(res)
        except Exception as e:
            log(f"⚠️ Cash失败 ({code}): {e}")
            time.sleep(3)
            return 0

    def get_stale_cashflow_codes(self, universe: List[str], days: int = 120) -> List[str]:
        """获取现金流缺失或过期的股票代码。"""
        conn = get_connection()
        try:
            threshold = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            stale = []
            for code in universe:
                row = conn.execute(
                    "SELECT MAX(end_date) FROM ts_cashflow WHERE ts_code = ?",
                    (code,),
                ).fetchone()
                max_end_date = row[0] if row else None
                if not max_end_date or max_end_date < threshold:
                    stale.append(code)
            return stale
        finally:
            conn.close()

    def run(self):
        log("🚀 启动全量财务数据抓取 (增量模式)...")
        all_stocks = self.get_all_stocks()
        candidate_stocks = self.get_candidates()
        if candidate_stocks:
            cashflow_universe = [code for code in all_stocks if code in candidate_stocks]
        else:
            cashflow_universe = all_stocks
        
        # 1. 抓取全量财务指标 (批量高效，本身就很快，可以保留全量或者也做检查)
        # 考虑到财务指标是按批次的，且速度极快 (2-3分钟)，全量刷新一遍能保证数据是最新的。
        # 这里保持全量抓取 Fina Indicator。
        log(f"\nPhase 1: 抓取全市场财务指标 ({len(all_stocks)} 只)...")
        batches = [all_stocks[i:i+BATCH_SIZE] for i in range(0, len(all_stocks), BATCH_SIZE)]
        
        with ThreadPoolExecutor(max_workers=BATCH_WORKERS) as executor:
            futures = {executor.submit(self.fetch_fina_batch, b): i for i, b in enumerate(batches)}
            count = 0
            for future in as_completed(futures):
                count += future.result()
                if futures[future] % 10 == 0:
                    print(f"\r   进度: {futures[future]+1}/{len(batches)} 批", end="", flush=True)
        log(f"\n✅ 财务指标完成: {count} 条")

        # 2. 抓取现金流 (增量抓取)
        target_stocks = self.get_stale_cashflow_codes(cashflow_universe)
        
        if not target_stocks:
            log("\n✅ 目标股票现金流数据已是最新，无需抓取。")
            return

        log(f"\nPhase 2: 抓取增量现金流数据 (共 {len(target_stocks)} 只)...")
        log(f"   (候选池规模 {len(cashflow_universe)} 只)")
        log("⚠️ 注意: Tushare 频率限制 (300次/分)。")
        
        with ThreadPoolExecutor(max_workers=SINGLE_WORKERS) as executor:
            futures = {executor.submit(self.fetch_cash_single, code): i for i, code in enumerate(target_stocks)}
            count = 0
            done = 0
            for future in as_completed(futures):
                count += future.result()
                done += 1
                if done % 50 == 0:
                     print(f"\r   进度: {done}/{len(target_stocks)} ({done/len(target_stocks)*100:.1f}%)", end="", flush=True)
        log(f"\n✅ 现金流补全完成: {count} 条")

if __name__ == "__main__":
    SmartFetcher().run()
