"""
Tushare 数据源适配器

统一的 Tushare API 客户端，包含：
- 限流控制（300请求/分钟）
- 指数退避重试
- 常用接口封装

使用前需设置环境变量：TUSHARE_TOKEN
"""

import os
import sys
import time
import functools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import pandas as pd

# 添加项目根目录到 sys.path (src/data_ingestion/tushare -> 项目根)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# 限流器
from src.utils.rate_limiter import rate_limit, TUSHARE_BUCKET


# ============================================================
# 配置
# ============================================================

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_tushare_token() -> str:
    """从环境变量获取 Tushare Token"""
    token = os.getenv('TUSHARE_TOKEN')
    if not token:
        raise ValueError(
            "未设置 TUSHARE_TOKEN 环境变量！\n"
            "请在 .env 文件中添加: TUSHARE_TOKEN=your_token\n"
            "或设置环境变量: export TUSHARE_TOKEN=your_token"
        )
    return token


# ============================================================
# 重试装饰器
# ============================================================

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    指数退避重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        exceptions: 需要重试的异常类型
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        print(f"   ⚠️ 重试 {attempt + 1}/{max_retries}，等待 {delay:.1f}s: {e}")
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


# ============================================================
# Tushare 客户端
# ============================================================

class TushareAdapter:
    """
    Tushare API 统一适配器
    
    特性：
    - 自动限流（300请求/分钟）
    - 指数退避重试
    - 统一接口封装
    - 支持自定义 API URL
    
    Example:
        client = TushareAdapter()
        
        # 获取日线数据
        df = client.daily(ts_code='000001.SZ', start_date='20260101')
        
        # 获取财务指标
        df = client.fina_indicator(ts_code='000001.SZ')
    """
    
    def __init__(self, token: str = None, api_url: str = None):
        """
        初始化 Tushare 客户端
        
        Args:
            token: Tushare Token，默认从环境变量读取
            api_url: 自定义 API URL，默认从环境变量 TUSHARE_API_URL 读取
        """
        try:
            import tinyshare as ts
        except ImportError:
            raise ImportError("请先安装 tinyshare: pip install tinyshare --upgrade")
        
        self.token = token or get_tushare_token()
        self.api_url = api_url or os.getenv("TUSHARE_API_URL", "https://api.tushare.pro")
        
        ts.set_token(self.token)
        self.api = ts.pro_api(self.token)
        self._configure_api_client()
        
        self._request_count = 0
        self._start_time = time.time()
        
        log(f"✅ Tushare 客户端初始化完成 (API: {self.api_url})")

    def _configure_api_client(self):
        """
        Configure optional runtime behavior without relying on private tushare fields.
        """
        self.timeout = int(os.getenv("TUSHARE_TIMEOUT", "60"))

        # Keep custom endpoint as configuration metadata only. Different tushare
        # versions expose different internals, so we avoid touching private attrs.
        custom_api_url = os.getenv("TUSHARE_API_URL")
        if custom_api_url and custom_api_url != "https://api.tushare.pro":
            log("⚠️ 已检测到 TUSHARE_API_URL；当前适配器不再修改 tushare 私有字段，请通过官方配置方式设置网关。")
    
    def _log_request(self, api_name: str):
        """记录请求"""
        self._request_count += 1
        elapsed = time.time() - self._start_time
        rate = self._request_count / elapsed * 60 if elapsed > 0 else 0
        if self._request_count % 50 == 0:
            print(f"   📊 Tushare 请求统计: {self._request_count} 次, {rate:.1f} 次/分钟")
    
    # ============================================================
    # 行情数据
    # ============================================================
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def daily(
        self, 
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取日线数据
        
        Args:
            ts_code: 股票代码（如 000001.SZ）
            trade_date: 交易日期（YYYYMMDD）
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            DataFrame 包含: ts_code, trade_date, open, high, low, close, 
                          pre_close, change, pct_chg, vol, amount
        """
        self._log_request('daily')
        return self.api.daily(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def daily_basic(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取每日指标（PE、PB、换手率等）
        
        Returns:
            DataFrame 包含: ts_code, trade_date, turnover_rate, pe, pe_ttm,
                          pb, ps, ps_ttm, dv_ratio, dv_ttm, total_mv, circ_mv
        """
        self._log_request('daily_basic')
        return self.api.daily_basic(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def adj_factor(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取复权因子
        
        Returns:
            DataFrame 包含: ts_code, trade_date, adj_factor
        """
        self._log_request('adj_factor')
        return self.api.adj_factor(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )
    
    # ============================================================
    # 财务数据
    # ============================================================
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def fina_indicator(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None
    ) -> pd.DataFrame:
        """
        获取财务指标
        
        Returns:
            DataFrame 包含: ts_code, ann_date, end_date, eps, roe, roa,
                          grossprofit_margin, netprofit_yoy, or_yoy...
        """
        self._log_request('fina_indicator')
        return self.api.fina_indicator(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def income(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None
    ) -> pd.DataFrame:
        """
        获取利润表
        
        Returns:
            DataFrame 包含: ts_code, ann_date, end_date, revenue, 
                          operate_profit, total_profit, n_income...
        """
        self._log_request('income')
        return self.api.income(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def cashflow(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None,
        fields: str = None,
    ) -> pd.DataFrame:
        """获取现金流量表。"""
        self._log_request("cashflow")
        return self.api.cashflow(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
            fields=fields,
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def top10_holders(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None,
    ) -> pd.DataFrame:
        """获取前十大股东。"""
        self._log_request("top10_holders")
        return self.api.top10_holders(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def hk_hold(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        exchange: str = None,
    ) -> pd.DataFrame:
        """获取沪深港通持股。"""
        self._log_request("hk_hold")
        return self.api.hk_hold(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def cyq_perf(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """获取筹码分布。"""
        self._log_request("cyq_perf")
        return self.api.cyq_perf(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def margin_detail(
        self,
        trade_date: str = None,
        ts_code: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取融资融券个股明细

        Returns:
            DataFrame 包含: trade_date, ts_code, rzye(融资余额), rqye(融券余额),
                          rzmre(融资买入额), rqyl(融券余量), rzche(融资偿还额),
                          rqchl(融券偿还量), rqmcl(融券卖出量), rzrqye(融资融券余额)
        """
        self._log_request('margin_detail')
        return self.api.margin_detail(
            trade_date=trade_date,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def stk_holdernumber(
        self,
        ts_code: str = None,
        enddate: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取股东人数

        Returns:
            DataFrame 包含: ts_code, ann_date, end_date, holder_num
        """
        self._log_request('stk_holdernumber')
        return self.api.stk_holdernumber(
            ts_code=ts_code,
            enddate=enddate,
            start_date=start_date,
            end_date=end_date
        )

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
        """获取业绩快报"""
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
        """获取业绩预告"""
        self._log_request("forecast")
        return self.api.forecast(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def balancesheet(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None
    ) -> pd.DataFrame:
        """
        获取资产负债表
        """
        self._log_request('balancesheet')
        return self.api.balancesheet(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            period=period
        )
    
    # ============================================================
    # 资金数据
    # ============================================================
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def moneyflow(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取个股资金流向
        
        Returns:
            DataFrame 包含: ts_code, trade_date, buy_sm_vol, buy_md_vol,
                          buy_lg_vol, buy_elg_vol, net_mf_vol...
        """
        self._log_request('moneyflow')
        return self.api.moneyflow(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def hsgt_top10(
        self,
        trade_date: str = None,
        ts_code: str = None,
        start_date: str = None,
        end_date: str = None,
        market_type: str = None
    ) -> pd.DataFrame:
        """
        获取北向资金十大成交股
        
        Args:
            market_type: SH-沪股通, SZ-深股通
        """
        self._log_request('hsgt_top10')
        return self.api.hsgt_top10(
            trade_date=trade_date,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            market_type=market_type
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def ggt_top10(
        self,
        trade_date: str = None,
        ts_code: str = None,
        start_date: str = None,
        end_date: str = None,
        market_type: str = None
    ) -> pd.DataFrame:
        """
        获取南向资金十大成交股（港股通）
        """
        self._log_request('ggt_top10')
        return self.api.ggt_top10(
            trade_date=trade_date,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            market_type=market_type
        )
    
    # ============================================================
    # 龙虎榜
    # ============================================================
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def top_list(
        self,
        trade_date: str = None,
        ts_code: str = None
    ) -> pd.DataFrame:
        """
        获取龙虎榜每日明细
        
        Returns:
            DataFrame 包含: ts_code, trade_date, name, close, pct_change,
                          turnover_rate, amount, l_sell, l_buy, net_amount...
        """
        self._log_request('top_list')
        return self.api.top_list(
            trade_date=trade_date,
            ts_code=ts_code
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def top_inst(
        self,
        trade_date: str = None,
        ts_code: str = None
    ) -> pd.DataFrame:
        """
        获取龙虎榜机构明细
        """
        self._log_request('top_inst')
        return self.api.top_inst(
            trade_date=trade_date,
            ts_code=ts_code
        )
    
    # ============================================================
    # 指数数据
    # ============================================================

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def index_daily(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取指数日线行情

        Args:
            ts_code: 指数代码（如 000001.SH）
            trade_date: 交易日期（YYYYMMDD）
            start_date: 开始日期
            end_date: 结束日期
        """
        self._log_request('index_daily')
        return self.api.index_daily(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def ths_daily(
        self,
        ts_code: str = None,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取同花顺板块指数日线行情

        Args:
            ts_code: 板块指数代码
            trade_date: 交易日期（YYYYMMDD）
            start_date: 开始日期
            end_date: 结束日期
        """
        self._log_request('ths_daily')
        return self.api.ths_daily(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    # ============================================================
    # 股票基础信息
    # ============================================================
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def stock_basic(
        self,
        is_hs: str = None,
        list_status: str = 'L',
        exchange: str = None
    ) -> pd.DataFrame:
        """
        获取股票基础信息
        
        Args:
            is_hs: 是否沪深港通 (N/H/S)
            list_status: 上市状态 (L上市/D退市/P暂停上市)
            exchange: 交易所 (SSE上交所/SZSE深交所/BSE北交所)
            
        Returns:
            DataFrame 包含: ts_code, symbol, name, area, industry, 
                          list_date, market, exchange...
        """
        self._log_request('stock_basic')
        return self.api.stock_basic(
            is_hs=is_hs,
            list_status=list_status,
            exchange=exchange
        )
    
    @rate_limit()
    @retry_with_backoff(max_retries=3)
    def trade_cal(
        self,
        exchange: str = 'SSE',
        start_date: str = None,
        end_date: str = None,
        is_open: int = None
    ) -> pd.DataFrame:
        """
        获取交易日历
        
        Args:
            exchange: 交易所
            is_open: 是否交易日 (0休市/1交易)
        """
        self._log_request('trade_cal')
        return self.api.trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            is_open=is_open
        )
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def get_all_stocks(self) -> pd.DataFrame:
        """获取全部上市股票"""
        return self.stock_basic(list_status='L')
    
    def get_trading_days(
        self, 
        start_date: str = None, 
        end_date: str = None
    ) -> List[str]:
        """
        获取交易日列表
        
        Args:
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期
            
        Returns:
            交易日列表
        """
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
        
        df = self.trade_cal(start_date=start_date, end_date=end_date, is_open=1)
        return df['cal_date'].tolist()
    
    def get_stats(self) -> dict:
        """获取请求统计"""
        elapsed = time.time() - self._start_time
        return {
            'total_requests': self._request_count,
            'elapsed_seconds': round(elapsed, 2),
            'requests_per_minute': round(self._request_count / elapsed * 60, 2) if elapsed > 0 else 0
        }


# ============================================================
# 全局单例
# ============================================================

_client: Optional[TushareAdapter] = None


def get_tushare_client() -> TushareAdapter:
    """获取全局 Tushare 客户端单例"""
    global _client
    if _client is None:
        _client = TushareAdapter()
    return _client
