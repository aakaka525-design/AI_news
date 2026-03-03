#!/usr/bin/env python3
"""
高级财务数据抓取脚本 (Premium Data Fetcher)

功能:
1. 抓取每日指标 (Daily Basic): PE/PB/股息率 (dv_ttm) 等
2. 抓取筹码分布 (Cyq Perf): 成本分布、获利盘 (需要 5000+ 积分)
3. 抓取北向持仓 (HK Hold): 沪深港股通持股
4. 抓取十大股东 (Top10 Holders): 社保/基金持仓
5. 补充现金流 CAPEX (Cashflow Capex): 增量更新

Author: AI Assistant
Date: 2026-01-22
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.data_ingestion.tushare.client import get_tushare_client
from src.database.connection import get_connection

# 配置
MAX_WORKERS = 3         # 降低并发，因为高级接口限流更严
START_DATE = '20230101' # 抓取近3年数据

log_lock = threading.Lock()

def log(msg: str):
    with log_lock:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

class AdvancedFetcher:
    def __init__(self):
        self.client = get_tushare_client()
        self._ensure_runtime_schema()

    def _ensure_runtime_schema(self):
        """兼容旧库结构，补齐高级抓取依赖列。"""
        conn = get_connection()
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            table_columns = {}
            for table in [
                "ts_daily_basic",
                "ts_hk_hold",
                "ts_cyq_perf",
                "ts_top10_holders",
                "ts_cashflow",
            ]:
                try:
                    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                except Exception:
                    cols = set()
                table_columns[table] = cols

            if "volume_ratio" not in table_columns["ts_daily_basic"]:
                conn.execute("ALTER TABLE ts_daily_basic ADD COLUMN volume_ratio REAL")
            if "created_at" not in table_columns["ts_daily_basic"]:
                conn.execute("ALTER TABLE ts_daily_basic ADD COLUMN created_at TIMESTAMP")
            if "created_at" not in table_columns["ts_hk_hold"]:
                conn.execute("ALTER TABLE ts_hk_hold ADD COLUMN created_at TIMESTAMP")
            if "created_at" not in table_columns["ts_cyq_perf"]:
                conn.execute("ALTER TABLE ts_cyq_perf ADD COLUMN created_at TIMESTAMP")
            if "created_at" not in table_columns["ts_top10_holders"]:
                conn.execute("ALTER TABLE ts_top10_holders ADD COLUMN created_at TIMESTAMP")
            if "c_paid_for_fixed_assets" not in table_columns["ts_cashflow"]:
                conn.execute("ALTER TABLE ts_cashflow ADD COLUMN c_paid_for_fixed_assets REAL")
            conn.commit()
        finally:
            conn.close()
        
    def get_all_stocks(self) -> List[str]:
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT ts_code FROM ts_stock_basic")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_trade_dates(self, start_date: str) -> List[str]:
        for retry in range(5):
            try:
                df = self.client.trade_cal(exchange='SSE', start_date=start_date, is_open=1)
                return df['cal_date'].tolist()
            except Exception as e:
                log(f"⚠️ get_trade_dates 重试 {retry+1}/5: {e}")
                time.sleep(3)
        raise Exception("get_trade_dates 失败，请检查网络连接")

    def get_existing_daily_basic_dates(self) -> set:
        """获取已存在的 Daily Basic 日期"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT DISTINCT trade_date FROM ts_daily_basic")
            return set(row[0] for row in cursor.fetchall())
        finally:
            conn.close()

    def get_existing_hk_hold_dates(self) -> set:
        """获取已存在的 HK Hold 日期"""
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT DISTINCT trade_date FROM ts_hk_hold")
            return set(row[0] for row in cursor.fetchall())
        finally:
            conn.close()

    def get_latest_date(self, table: str, code_col: str, date_col: str, ts_code: str) -> str:
        """获取单只股票在某表中的最新日期。"""
        conn = get_connection()
        try:
            row = conn.execute(
                f"SELECT MAX({date_col}) FROM {table} WHERE {code_col} = ?",
                (ts_code,),
            ).fetchone()
            return row[0] if row and row[0] else ""
        finally:
            conn.close()

    def get_codes_without_capex(self) -> List[str]:
        """获取缺少 Capex 数据的股票代码 (仅检查2023年以后)"""
        conn = get_connection()
        try:
            # 只检查2023年以后的记录，忽略历史旧数据
            cursor = conn.execute("""
                SELECT DISTINCT ts_code FROM ts_cashflow 
                WHERE c_paid_for_fixed_assets IS NULL AND end_date >= '20230101'
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # 1. 每日指标 (Daily Basic) - 含股息率
    # =========================================================================
    def fetch_daily_basic(self, trade_date: str):
        """按日期抓取全市场每日指标"""
        try:
            # daily_basic 接口一次支持单日全市场
            df = self.client.daily_basic(
                trade_date=trade_date,
                fields=(
                    "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,"
                    "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,"
                    "free_share,total_mv,circ_mv"
                ),
            )
            if df is None or df.empty:
                return 0
            
            data = []
            updated = datetime.now()
            for _, row in df.iterrows():
                data.append(row.to_dict())
                data[-1]['updated_at'] = updated
                data[-1]['created_at'] = updated
            
            conn = get_connection()
            try:
                conn.executemany('''
                    INSERT OR REPLACE INTO ts_daily_basic 
                    (ts_code, trade_date, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share, free_share, total_mv, circ_mv, created_at, updated_at)
                    VALUES (:ts_code, :trade_date, :turnover_rate, :turnover_rate_f, :volume_ratio, :pe, :pe_ttm, :pb, :ps, :ps_ttm, :dv_ratio, :dv_ttm, :total_share, :float_share, :free_share, :total_mv, :circ_mv, :created_at, :updated_at)
                ''', data)
                conn.commit()
            finally:
                conn.close()
            return len(data)
        except Exception as e:
            log(f"⚠️ DailyBasic {trade_date} 失败: {e}")
            return 0

    # =========================================================================
    # 2. 北向持仓 (HK Hold)
    # =========================================================================
    def fetch_hk_hold(self, trade_date: str):
        """按日期抓取北向持仓"""
        try:
            df = self.client.hk_hold(trade_date=trade_date)
            if df is None or df.empty:
                return 0
            
            data = []
            updated = datetime.now()
            for _, row in df.iterrows():
                data.append((
                    row['ts_code'], row['trade_date'], row['vol'], row['ratio'], row['exchange'], updated, updated
                ))
            
            conn = get_connection()
            try:
                conn.executemany('INSERT OR REPLACE INTO ts_hk_hold (ts_code, trade_date, vol, ratio, exchange, created_at, updated_at) VALUES (?,?,?,?,?,?,?)', data)
                conn.commit()
            finally:
                conn.close()
            return len(data)
        except Exception as e:
            log(f"⚠️ HKHold {trade_date} 失败: {e}")
            return 0

    # =========================================================================
    # 3. 筹码分布 (Cyq Perf) - 耗分大户
    # =========================================================================
    def fetch_cyq_perf_single(self, ts_code: str):
        """按股票抓取筹码分布 (全历史)"""
        try:
            start_date = self.get_latest_date("ts_cyq_perf", "ts_code", "trade_date", ts_code) or START_DATE
            df = self.client.cyq_perf(ts_code=ts_code, start_date=start_date)
            if df is None or df.empty:
                return 0
            
            data = []
            updated = datetime.now()
            for _, row in df.iterrows():
                data.append(row.to_dict())
                data[-1]['updated_at'] = updated
                data[-1]['created_at'] = updated

            conn = get_connection()
            try:
                conn.executemany('''
                    INSERT OR REPLACE INTO ts_cyq_perf
                    (ts_code, trade_date, cost_5pct, cost_15pct, cost_50pct, cost_85pct, cost_95pct, weight_avg, winner_rate, created_at, updated_at)
                    VALUES (:ts_code, :trade_date, :cost_5pct, :cost_15pct, :cost_50pct, :cost_85pct, :cost_95pct, :weight_avg, :winner_rate, :created_at, :updated_at)
                ''', data)
                conn.commit()
            finally:
                conn.close()
            return len(data)
        except Exception as e:
            log(f"⚠️ CyqPerf {ts_code} 失败: {e}")
            time.sleep(1) # 失败退避
            return 0

    # =========================================================================
    # 4. 十大股东 (Top10 Holders)
    # =========================================================================
    def fetch_top10_holders(self, ts_code: str):
        try:
            start_date = self.get_latest_date("ts_top10_holders", "ts_code", "end_date", ts_code) or START_DATE
            df = self.client.top10_holders(ts_code=ts_code, start_date=start_date)
            if df is None or df.empty:
                return 0
                
            data = []
            updated = datetime.now()
            for _, row in df.iterrows():
                data.append(row.to_dict())
                data[-1]['updated_at'] = updated
                data[-1]['created_at'] = updated
                
            conn = get_connection()
            try:
                conn.executemany('''
                    INSERT OR REPLACE INTO ts_top10_holders
                    (ts_code, ann_date, end_date, holder_name, hold_amount, hold_ratio, created_at, updated_at)
                    VALUES (:ts_code, :ann_date, :end_date, :holder_name, :hold_amount, :hold_ratio, :created_at, :updated_at)
                ''', data)
                conn.commit()
            finally:
                conn.close()
            return len(data)
        except Exception as e:
            log(f"⚠️ Top10 {ts_code} 失败: {e}")
            return 0

    # =========================================================================
    # 5. 补充 Capex (修正 Cashflow)
    # =========================================================================
    def patch_capex(self, ts_code: str):
        """补充 Capex 字段"""
        try:
            # 3 线程 * 0.4s ≈ 450 requests/min，保守低于 500/min。
            time.sleep(0.4)
            # 修正字段名: c_pay_acq_const_fiolta (购建固定资产、无形资产和其他长期资产支付的现金)
            df = self.client.cashflow(
                ts_code=ts_code,
                start_date=START_DATE,
                fields='ts_code,ann_date,end_date,c_pay_acq_const_fiolta',
            )
            if df is None or df.empty:
                return 0
            
            data = []
            for _, row in df.iterrows():
                # Map c_pay_acq_const_fiolta -> c_paid_for_fixed_assets
                val = row['c_pay_acq_const_fiolta']
                data.append((val, row['ts_code'], row['end_date']))
            
            conn = get_connection()
            try:
                # 只更新已存在的记录 (假设之前脚本已跑过)
                conn.executemany('''
                    UPDATE ts_cashflow 
                    SET c_paid_for_fixed_assets = ? 
                    WHERE ts_code = ? AND end_date = ?
                ''', data)
                conn.commit()
            finally:
                conn.close()
            return len(data)
        except Exception as e:
            log(f"⚠️ Capex Patch {ts_code} 失败: {e}")
            return 0

    # =========================================================================
    # 主流程
    # =========================================================================
    def run(self):
        log("🚀 开始高级数据抓取 (增量模式)...")
        all_stocks = self.get_all_stocks()
        today = datetime.now().strftime('%Y%m%d')  # 今天日期
        all_dates = self.get_trade_dates(START_DATE)
        dates = [d for d in all_dates if d <= today]  # 只取历史日期

        # 1. Daily Basic (增量：跳过已存在日期)
        exist_daily_dates = self.get_existing_daily_basic_dates()
        target_dates = [d for d in dates if d not in exist_daily_dates]
        log(f"\n1️⃣ 抓取每日指标 (Daily Basic) - 需抓取 {len(target_dates)} 天 (跳过 {len(dates)-len(target_dates)} 天)")
        for d in target_dates:
            count = self.fetch_daily_basic(d)
            print(f"\r   {d}: {count} 条", end="", flush=True)
            time.sleep(0.3)
            
        # 2. HK Hold (增量：跳过已存在日期)
        exist_hk_dates = self.get_existing_hk_hold_dates()
        target_hk_dates = [d for d in dates if d not in exist_hk_dates]
        log(f"\n\n2️⃣ 抓取北向持仓 (HK Hold) - 需抓取 {len(target_hk_dates)} 天 (跳过 {len(dates)-len(target_hk_dates)} 天)")
        for d in target_hk_dates:
            count = self.fetch_hk_hold(d)
            print(f"\r   {d}: {count} 条", end="", flush=True)
            time.sleep(0.3)

        # 3. Top10 Holders (增量：按每只股票最新 end_date 续抓)
        target_top10 = all_stocks
        log(f"\n\n3️⃣ 抓取十大股东 (Top10) - 续抓 {len(target_top10)} 只")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self.fetch_top10_holders, code) for code in target_top10]
            done = 0
            for f in as_completed(futures):
                done += 1
                if done % 50 == 0:
                     print(f"\r   进度: {done}/{len(target_top10)} ({done/len(target_top10)*100:.1f}%)", end="", flush=True)

        # 4. Capex Patch (增量：仅更新缺少 Capex 的记录)
        capex_targets = self.get_codes_without_capex()
        log(f"\n\n4️⃣ 补充 Capex - 需更新 {len(capex_targets)} 只")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self.patch_capex, code) for code in capex_targets]
            done = 0
            for f in as_completed(futures):
                done += 1
                if done % 50 == 0:
                     print(f"\r   进度: {done}/{len(capex_targets)}", end="", flush=True)
        
        # 5. Cyq Perf (多线程 - 10000积分用户)
        log("\n\n5️⃣ 抓取筹码分布 (Cyq Perf) - 5线程加速...")
        cyq_targets = all_stocks
        log(f"   需续抓: {len(cyq_targets)} 只")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self.fetch_cyq_perf_single, code) for code in cyq_targets]
            done = 0
            for f in as_completed(futures):
                done += 1
                if done % 50 == 0:
                    print(f"\r   进度: {done}/{len(cyq_targets)} ({done/len(cyq_targets)*100:.1f}%)", end="", flush=True)

        log("\n✅ 所有高级数据抓取完成!")

if __name__ == "__main__":
    AdvancedFetcher().run()
