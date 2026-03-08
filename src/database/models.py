#!/usr/bin/env python3
"""
AI-Ready 金融数据库模型

架构特点：
1. 分区策略：高频表支持按日期分区
2. 预计算复权价：qfq_close/hfq_close 避免运行时计算
3. 向量字段：embedding 支持 LLM 语义检索
4. 幂等性：UniqueConstraint + upsert 防重复

Author: Chief Financial Data Architect
Version: 2.0.0
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
import json
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, String, Integer, BigInteger, Float, 
    Text, Boolean, DateTime, Date, Numeric, JSON, Index,
    UniqueConstraint, ForeignKey, event, inspect
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON


Base = declarative_base()


def to_ts_code(code: str) -> str:
    """Convert 6-digit stock code to tushare format (e.g. 000001 -> 000001.SZ)."""
    raw = str(code or "").strip().upper()
    if not raw:
        return raw
    if "." in raw:
        return raw
    raw = raw.zfill(6)
    if raw.startswith(("6", "5")):
        return f"{raw}.SH"
    if raw.startswith(("4", "8", "9")):
        return f"{raw}.BJ"
    return f"{raw}.SZ"


def from_ts_code(ts_code: str) -> str:
    """Extract 6-digit stock code from tushare code."""
    raw = str(ts_code or "").strip().upper()
    return raw.split(".")[0] if "." in raw else raw


def format_date(date_value: Any) -> str:
    """Normalize date into YYYYMMDD."""
    if date_value is None:
        return ""
    raw = str(date_value).strip()
    if not raw:
        return ""
    if "-" in raw:
        return raw.replace("-", "")
    if "/" in raw:
        return raw.replace("/", "")
    return raw[:8]


# ============================================================
# 精度定义 (适用于金融数据)
# ============================================================

# 价格精度: 2位小数 (如 123.45)
PRICE = Numeric(12, 2)
# 涨跌幅精度: 4位小数 (如 0.1234 = 12.34%)
RATIO = Numeric(8, 4)
# 市值精度: 2位小数，支持万亿级 (如 50000.00亿)
MARKET_VALUE = Numeric(18, 2)
# 成交量: 整数 (手)
VOLUME = BigInteger()
# 成交额: 2位小数 (千元)
AMOUNT = Numeric(18, 2)
# 向量维度 (用于 embedding)
EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small


# ============================================================
# Mixin: 通用字段
# ============================================================

class TimestampMixin:
    """时间戳混入"""
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class TsCodeMixin:
    """Tushare 代码混入"""
    ts_code = Column(String(12), nullable=False, index=True, comment="股票代码 (000001.SZ)")


# ============================================================
# Reference: 参考数据
# ============================================================

class StockBasic(Base, TimestampMixin):
    """
    股票基础信息
    
    更新频率: 每日 (新股上市时)
    数据源: Tushare stock_basic
    """
    __tablename__ = 'ts_stock_basic'
    
    ts_code = Column(String(12), primary_key=True, comment="股票代码 (000001.SZ)")
    symbol = Column(String(6), nullable=False, index=True, comment="6位代码")
    name = Column(String(50), nullable=False, comment="股票名称")
    
    # 分类信息
    area = Column(String(20), comment="地区")
    industry = Column(String(50), index=True, comment="所属行业")
    market = Column(String(20), index=True, comment="市场 (主板/创业板/科创板/北交所)")
    exchange = Column(String(10), comment="交易所 (SSE/SZSE/BSE)")
    
    # 状态
    list_status = Column(String(1), default='L', comment="上市状态 (L/D/P)")
    list_date = Column(String(8), comment="上市日期 (YYYYMMDD)")
    delist_date = Column(String(8), comment="退市日期")
    is_hs = Column(String(1), comment="沪深港通 (N/H/S)")
    
    # 扩展字段 (AI 用)
    fullname = Column(String(100), comment="公司全称")
    cn_spell = Column(String(50), comment="拼音首字母")
    
    __table_args__ = (
        Index('ix_stock_basic_market_industry', 'market', 'industry'),
        {'comment': '股票基础信息表'}
    )


class TradeCal(Base, TimestampMixin):
    """
    交易日历
    
    更新频率: 年度
    用途: 判断是否交易日，计算交易日间隔
    """
    __tablename__ = 'trade_cal'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(10), nullable=False, comment="交易所")
    cal_date = Column(String(8), nullable=False, comment="日期")
    is_open = Column(Boolean, default=True, comment="是否交易日")
    pretrade_date = Column(String(8), comment="上一个交易日")
    
    __table_args__ = (
        UniqueConstraint('exchange', 'cal_date', name='uq_trade_cal'),
        Index('ix_trade_cal_date', 'cal_date'),
        {'comment': '交易日历表'}
    )


# ============================================================
# MarketData: 行情数据
# ============================================================

class StockDaily(Base, TimestampMixin, TsCodeMixin):
    """
    股票日线行情
    
    更新频率: 每日收盘后
    数据源: Tushare daily + adj_factor
    
    性能优化:
    - 预计算复权价 (qfq_close, hfq_close)
    - 按 trade_date 分区 (PostgreSQL)
    - 复合索引加速时间序列查询
    
    分区建议 (PostgreSQL):
        PARTITION BY RANGE (trade_date)
        每月一个分区，保留 10 年数据
    """
    __tablename__ = 'ts_daily'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # OHLCV (原始价格)
    open = Column(PRICE, comment="开盘价")
    high = Column(PRICE, comment="最高价")
    low = Column(PRICE, comment="最低价")
    close = Column(PRICE, comment="收盘价")
    pre_close = Column(PRICE, comment="昨收价")
    
    # 涨跌
    change = Column(PRICE, comment="涨跌额")
    pct_chg = Column(RATIO, comment="涨跌幅 (%)")
    
    # 成交
    vol = Column(VOLUME, comment="成交量 (手)")
    amount = Column(AMOUNT, comment="成交额 (千元)")
    
    # 🔥 复权因子 + 预计算复权价 (回测加速)
    adj_factor = Column(Numeric(10, 6), comment="复权因子")
    qfq_close = Column(PRICE, comment="前复权收盘价 (预计算)")
    hfq_close = Column(PRICE, comment="后复权收盘价 (预计算)")
    
    # 技术指标 (可选预计算)
    turnover_rate = Column(RATIO, comment="换手率 (%)")
    volume_ratio = Column(Numeric(6, 2), comment="量比")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_stock_daily'),
        Index('ix_stock_daily_code_date', 'ts_code', 'trade_date'),
        Index('ix_stock_daily_date', 'trade_date'),
        {
            'comment': '股票日线行情表',
            # PostgreSQL 分区注释
            # 'postgresql_partition_by': 'RANGE (trade_date)'
        }
    )
    
    @classmethod
    def compute_adj_prices(cls, close: float, adj_factor: float, latest_adj: float) -> dict:
        """
        计算复权价格
        
        Args:
            close: 收盘价
            adj_factor: 当日复权因子
            latest_adj: 最新复权因子
            
        Returns:
            {'qfq_close': 前复权价, 'hfq_close': 后复权价}
        """
        if not latest_adj:
            return {'qfq_close': None, 'hfq_close': None}
        return {
            'qfq_close': round(close * adj_factor / latest_adj, 2),
            'hfq_close': round(close * adj_factor, 2)
        }


class StockIndex(Base, TimestampMixin):
    """
    指数行情 (大盘择时)
    
    用途: 判断大盘趋势，控制仓位
    常用指数: 000001.SH (上证), 399001.SZ (深成), 399006.SZ (创业板)
    """
    __tablename__ = 'stock_index'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(12), nullable=False, index=True, comment="指数代码")
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # OHLCV
    open = Column(PRICE, comment="开盘")
    high = Column(PRICE, comment="最高")
    low = Column(PRICE, comment="最低")
    close = Column(PRICE, comment="收盘")
    pre_close = Column(PRICE, comment="昨收")
    change = Column(PRICE, comment="涨跌额")
    pct_chg = Column(RATIO, comment="涨跌幅 (%)")
    vol = Column(VOLUME, comment="成交量 (手)")
    amount = Column(AMOUNT, comment="成交额 (千元)")
    
    # 市场宽度指标 (可选)
    up_count = Column(Integer, comment="上涨家数")
    down_count = Column(Integer, comment="下跌家数")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_stock_index'),
        Index('ix_stock_index_code_date', 'ts_code', 'trade_date'),
        {'comment': '指数日线行情表'}
    )


class BlockDaily(Base, TimestampMixin):
    """
    板块指数 (行业轮动)
    
    用途: 识别热点板块，板块轮动策略
    数据源: Tushare 行业指数 / 概念指数
    """
    __tablename__ = 'block_daily'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    block_code = Column(String(20), nullable=False, index=True, comment="板块代码")
    block_name = Column(String(50), nullable=False, comment="板块名称")
    block_type = Column(String(20), index=True, comment="类型 (industry/concept/area)")
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # 行情
    open = Column(PRICE, comment="开盘")
    high = Column(PRICE, comment="最高")
    low = Column(PRICE, comment="最低")
    close = Column(PRICE, comment="收盘")
    pct_chg = Column(RATIO, comment="涨跌幅 (%)")
    vol = Column(VOLUME, comment="成交量")
    amount = Column(AMOUNT, comment="成交额")
    turnover_rate = Column(RATIO, comment="换手率")
    
    # 板块强度
    lead_stock = Column(String(12), comment="领涨股票代码")
    up_count = Column(Integer, comment="上涨个股数")
    down_count = Column(Integer, comment="下跌个股数")
    
    __table_args__ = (
        UniqueConstraint('block_code', 'trade_date', name='uq_block_daily'),
        Index('ix_block_daily_type_date', 'block_type', 'trade_date'),
        {'comment': '板块日线行情表'}
    )


# ============================================================
# AlternativeData: 另类数据 (AI 重点)
# ============================================================

class NewsFlash(Base, TimestampMixin):
    """
    新闻快讯 (AI 语义分析)
    
    用途: 舆情监控、事件驱动策略
    特点: 包含 embedding 向量用于语义检索
    
    Embedding 存储方案:
    - PostgreSQL: 使用 pgvector 扩展
    - SQLite: 使用 JSON 序列化
    - 未来: 接入向量数据库 (Pinecone, Milvus)
    """
    __tablename__ = 'news_flash'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 内容
    title = Column(String(500), nullable=False, comment="标题")
    content = Column(Text, comment="正文内容")
    summary = Column(Text, comment="AI 摘要")
    source = Column(String(100), index=True, comment="来源")
    url = Column(String(500), comment="原文链接")
    
    # 时间
    publish_time = Column(DateTime, index=True, comment="发布时间")
    
    # 关联
    ts_codes = Column(JSON, comment="相关股票代码列表")
    industries = Column(JSON, comment="相关行业列表")
    
    # 🔥 AI 字段
    embedding = Column(JSON, comment="语义向量 (1536维)")
    sentiment_score = Column(Numeric(4, 3), comment="情绪分数 (-1.000 ~ 1.000)")
    sentiment_label = Column(String(20), index=True, comment="情绪标签 (positive/negative/neutral)")
    importance = Column(Integer, default=0, comment="重要性 (0-10)")
    
    # 标签
    tags = Column(JSON, comment="标签列表")
    category = Column(String(50), index=True, comment="分类")
    
    __table_args__ = (
        Index('ix_news_publish_time', 'publish_time'),
        Index('ix_news_category', 'category'),
        {'comment': '新闻快讯表 (含向量)'}
    )
    
    def set_embedding(self, vector: List[float]):
        """设置 embedding 向量"""
        self.embedding = vector
    
    def get_embedding(self) -> Optional[List[float]]:
        """获取 embedding 向量"""
        return self.embedding if self.embedding else None


class ResearchReport(Base, TimestampMixin):
    """
    研究报告 (AI 解析)
    
    用途: 机构观点汇总、目标价追踪
    特点: 支持 LLM 解析结构化信息
    """
    __tablename__ = 'research_report'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 基本信息
    ts_code = Column(String(12), index=True, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    title = Column(String(500), nullable=False, comment="报告标题")
    
    # 机构
    institution = Column(String(100), index=True, comment="研究机构")
    analyst = Column(String(100), comment="分析师")
    
    # 评级
    rating = Column(String(20), index=True, comment="评级 (买入/增持/中性/减持/卖出)")
    rating_change = Column(String(20), comment="评级变动 (上调/维持/下调)")
    target_price = Column(PRICE, comment="目标价")
    target_price_change = Column(RATIO, comment="目标价变动幅度")
    
    # 内容
    content = Column(Text, comment="报告正文")
    summary = Column(Text, comment="AI 摘要")
    key_points = Column(JSON, comment="核心观点列表")
    
    # 🔥 AI 字段
    embedding = Column(JSON, comment="语义向量")
    sentiment_score = Column(Numeric(4, 3), comment="情绪分数")
    
    # 时间
    publish_date = Column(String(8), index=True, comment="发布日期")
    
    __table_args__ = (
        Index('ix_report_code_date', 'ts_code', 'publish_date'),
        Index('ix_report_institution', 'institution'),
        {'comment': '研究报告表 (含向量)'}
    )


class MoneyFlow(Base, TimestampMixin, TsCodeMixin):
    """
    资金流向 (主力追踪)
    
    用途: 主力资金监控、北向资金追踪
    数据源: Tushare moneyflow + hsgt_top10
    """
    __tablename__ = 'money_flow'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    flow_type = Column(String(20), index=True, comment="类型 (main/north/south)")
    
    # 主力资金 (大单+超大单)
    buy_elg_amount = Column(AMOUNT, comment="超大单买入 (万元)")
    sell_elg_amount = Column(AMOUNT, comment="超大单卖出 (万元)")
    buy_lg_amount = Column(AMOUNT, comment="大单买入 (万元)")
    sell_lg_amount = Column(AMOUNT, comment="大单卖出 (万元)")
    
    # 净流入
    net_mf_amount = Column(AMOUNT, comment="主力净流入 (万元)")
    net_mf_rate = Column(RATIO, comment="主力净流入占比 (%)")
    
    # 北向资金特有
    north_amount = Column(AMOUNT, comment="北向买入金额 (万元)")
    north_net = Column(AMOUNT, comment="北向净买入 (万元)")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', 'flow_type', name='uq_money_flow'),
        Index('ix_money_flow_date_type', 'trade_date', 'flow_type'),
        {'comment': '资金流向表'}
    )


class DragonTiger(Base, TimestampMixin, TsCodeMixin):
    """
    龙虎榜 (游资追踪)
    
    用途: 识别游资动向、短线热点
    数据源: Tushare top_list + top_inst
    """
    __tablename__ = 'dragon_tiger'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    name = Column(String(50), comment="股票名称")
    
    # 行情
    close = Column(PRICE, comment="收盘价")
    pct_chg = Column(RATIO, comment="涨跌幅 (%)")
    turnover_rate = Column(RATIO, comment="换手率 (%)")
    
    # 龙虎榜数据
    amount = Column(AMOUNT, comment="总成交额 (万元)")
    l_buy = Column(AMOUNT, comment="买入额 (万元)")
    l_sell = Column(AMOUNT, comment="卖出额 (万元)")
    net_amount = Column(AMOUNT, comment="净买入额 (万元)")
    net_rate = Column(RATIO, comment="净买入占比 (%)")
    
    # 上榜原因
    reason = Column(String(200), comment="上榜原因")
    
    # 机构参与
    inst_buy = Column(AMOUNT, comment="机构买入 (万元)")
    inst_sell = Column(AMOUNT, comment="机构卖出 (万元)")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_dragon_tiger'),
        Index('ix_dragon_tiger_date', 'trade_date'),
        {'comment': '龙虎榜表'}
    )


class TsDailyBasic(Base, TimestampMixin, TsCodeMixin):
    """
    股票每日指标 (Basic)
    
    更新频率: 每日
    数据源: Tushare daily_basic
    """
    __tablename__ = 'ts_daily_basic'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # 常用指标
    turnover_rate = Column(RATIO, comment="换手率 (%)")
    turnover_rate_f = Column(RATIO, comment="换手率(自由流通股) (%)")
    volume_ratio = Column(Numeric(6, 2), comment="量比")
    pe = Column(Numeric(10, 4), comment="PE")
    pe_ttm = Column(Numeric(10, 4), comment="PE_TTM")
    pb = Column(Numeric(10, 4), comment="PB")
    ps = Column(Numeric(10, 4), comment="PS")
    ps_ttm = Column(Numeric(10, 4), comment="PS_TTM")
    dv_ratio = Column(RATIO, comment="股息率 (%)")
    dv_ttm = Column(RATIO, comment="股息率_TTM (%)")
    total_share = Column(MARKET_VALUE, comment="总股本 (万股)")
    float_share = Column(MARKET_VALUE, comment="流通股本 (万股)")
    free_share = Column(MARKET_VALUE, comment="自由流通股本 (万股)")
    total_mv = Column(MARKET_VALUE, comment="总市值 (万元)")
    circ_mv = Column(MARKET_VALUE, comment="流通市值 (万元)")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_ts_daily_basic'),
        Index('ix_ts_daily_basic_date', 'trade_date'),
        {'comment': '每日指标表'}
    )


class TsCyqPerf(Base, TimestampMixin, TsCodeMixin):
    """
    每日筹码与分布 (Premium)
    
    用途: 成本分布、获利盘比例
    数据源: Tushare cyq_perf
    """
    __tablename__ = 'ts_cyq_perf'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # 成本分布
    cost_5pct = Column(PRICE, comment="5分位成本")
    cost_15pct = Column(PRICE, comment="15分位成本")
    cost_50pct = Column(PRICE, comment="50分位成本")
    cost_85pct = Column(PRICE, comment="85分位成本")
    cost_95pct = Column(PRICE, comment="95分位成本")
    weight_avg = Column(PRICE, comment="加权平均成本")
    
    # 获利情况
    winner_rate = Column(RATIO, comment="获利盘比例")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_ts_cyq_perf'),
        Index('ix_ts_cyq_perf_date', 'trade_date'),
        {'comment': '筹码分布表'}
    )


class TsHkHold(Base, TimestampMixin, TsCodeMixin):
    """
    沪深港股通持股 (Northbound)
    
    用途: 北向资金持仓追踪
    数据源: Tushare hk_hold
    """
    __tablename__ = 'ts_hk_hold'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(8), nullable=False, index=True, comment="交易日期")
    
    # 持仓
    vol = Column(BigInteger, comment="持股数量 (股)")
    ratio = Column(RATIO, comment="持股占比 (%)")
    exchange = Column(String(10), index=True, comment="类型 (SH/SZ/HK)")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_ts_hk_hold'),
        Index('ix_ts_hk_hold_date', 'trade_date'),
        {'comment': '沪深港股通持股表'}
    )


class TsCashflow(Base, TimestampMixin, TsCodeMixin):
    """
    现金流量表
    
    更新频率: 季报
    数据源: Tushare cashflow
    """
    __tablename__ = 'ts_cashflow'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ann_date = Column(String(8), nullable=False, index=True, comment="公告日期")
    end_date = Column(String(8), nullable=False, index=True, comment="报告期")
    
    # 经营
    n_cashflow_act = Column(AMOUNT, comment="经营活动产生的现金流量净额")
    
    # 投资
    n_cashflow_inv_act = Column(AMOUNT, comment="投资活动产生的现金流量净额")
    c_paid_for_fixed_assets = Column(AMOUNT, comment="购建固定资产等支付的现金 (Capex)")
    
    # 筹资
    n_cash_flows_fnc_act = Column(AMOUNT, comment="筹资活动产生的现金流量净额")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'ann_date', 'end_date', name='uq_ts_cashflow'),
        Index('ix_ts_cashflow_code_date', 'ts_code', 'end_date'),
        {'comment': '现金流量表'}
    )


class TsTop10Holders(Base, TimestampMixin, TsCodeMixin):
    """
    前十大股东
    
    用途: 社保/基金/主力追踪
    数据源: Tushare top10_holders
    """
    __tablename__ = 'ts_top10_holders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ann_date = Column(String(8), index=True, comment="公告日期")
    end_date = Column(String(8), index=True, comment="报告期")
    
    holder_name = Column(String(100), index=True, comment="股东名称")
    hold_amount = Column(BigInteger, comment="持有数量 (股)")
    hold_ratio = Column(RATIO, comment="持有比例 (%)")
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'ann_date', 'holder_name', name='uq_ts_top10_holders'),
        Index('ix_ts_top10_holders_name', 'holder_name'),
        {'comment': '前十大股东表'}
    )


# ============================================================
# Snapshot: 筛选器/分析快照 (产品化)
# ============================================================

class ScreenRpsSnapshot(Base, TimestampMixin):
    """
    RPS 强度排名日快照

    生成频率: 每日 17:15 (收盘数据入库后)
    保留期: 60 个交易日
    数据源: src/strategies/rps_screener.py
    """
    __tablename__ = 'screen_rps_snapshot'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, comment="快照生成日期")
    source_trade_date = Column(Date, nullable=False, comment="数据基于的最新交易日")
    generated_at = Column(DateTime, nullable=False, comment="实际生成时间")
    generator_version = Column(String(16), nullable=False, default="v1.0", comment="生成器版本")
    ts_code = Column(String(12), nullable=False, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    rps_10 = Column(Numeric(8, 4), comment="10日 RPS")
    rps_20 = Column(Numeric(8, 4), comment="20日 RPS")
    rps_50 = Column(Numeric(8, 4), comment="50日 RPS")
    rps_120 = Column(Numeric(8, 4), comment="120日 RPS")
    rank = Column(Integer, comment="综合排名")

    __table_args__ = (
        UniqueConstraint('snapshot_date', 'ts_code', name='uq_screen_rps_snapshot'),
        Index('ix_screen_rps_date_rank', 'snapshot_date', 'rank'),
        {'comment': 'RPS 筛选日快照表'}
    )


class ScreenPotentialSnapshot(Base, TimestampMixin):
    """
    多因子潜力股筛选日快照

    生成频率: 每日 17:15
    保留期: 60 个交易日
    数据源: src/strategies/potential_screener.py
    """
    __tablename__ = 'screen_potential_snapshot'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, comment="快照生成日期")
    source_trade_date = Column(Date, nullable=False, comment="数据基于的最新交易日")
    generated_at = Column(DateTime, nullable=False, comment="实际生成时间")
    generator_version = Column(String(16), nullable=False, default="v1.0", comment="生成器版本")
    ts_code = Column(String(12), nullable=False, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    total_score = Column(Numeric(8, 4), comment="总分 (满分100)")
    capital_score = Column(Numeric(8, 4), comment="资金面得分 (满分30)")
    trading_score = Column(Numeric(8, 4), comment="交易面得分 (满分25)")
    fundamental_score = Column(Numeric(8, 4), comment="基本面得分 (满分20)")
    technical_score = Column(Numeric(8, 4), comment="技术面得分 (满分25)")
    signals = Column(Text, comment="信号标签 JSON (如 [\"MACD金叉\", \"量价齐升\"])")
    rank = Column(Integer, comment="综合排名")

    __table_args__ = (
        UniqueConstraint('snapshot_date', 'ts_code', name='uq_screen_potential_snapshot'),
        Index('ix_screen_potential_date_rank', 'snapshot_date', 'rank'),
        {'comment': '潜力筛选日快照表'}
    )


class AnalysisFullSnapshot(Base, TimestampMixin):
    """
    个股完整分析快照

    生成频率: 每日预计算 30-40 只热门股 + 按需懒生成
    保留期: 14 天
    数据源: src/strategies/full_analysis.py
    """
    __tablename__ = 'analysis_full_snapshot'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, comment="快照生成日期")
    source_trade_date = Column(Date, nullable=False, comment="数据基于的最新交易日")
    generated_at = Column(DateTime, nullable=False, comment="实际生成时间")
    generator_version = Column(String(16), nullable=False, default="v1.0", comment="生成器版本")
    ts_code = Column(String(12), nullable=False, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    analysis_json = Column(Text, nullable=False, comment="完整分析结果 JSON")

    __table_args__ = (
        UniqueConstraint('snapshot_date', 'ts_code', name='uq_analysis_full_snapshot'),
        Index('ix_analysis_full_date', 'snapshot_date'),
        {'comment': '个股完整分析快照表'}
    )


# ============================================================
# Upsert Helper (幂等性保证)
# ============================================================

def upsert_data(session, model, data: List[Dict], unique_keys: List[str]):
    """
    批量 Upsert (Insert or Update)
    
    实现幂等性，防止重复运行爬虫导致主键冲突
    
    Args:
        session: SQLAlchemy session
        model: ORM 模型类
        data: 数据列表 (字典)
        unique_keys: 唯一键列表 (用于冲突检测)
        
    Usage:
        upsert_data(session, StockDaily, daily_data, ['ts_code', 'trade_date'])
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    
    if not data:
        return 0
    
    # 获取表对象
    table = model.__table__
    
    # 检测数据库类型
    dialect = session.bind.dialect.name
    
    if dialect == 'postgresql':
        # PostgreSQL: ON CONFLICT DO UPDATE
        stmt = pg_insert(table).values(data)
        update_cols = {c.name: c for c in stmt.excluded if c.name not in unique_keys}
        stmt = stmt.on_conflict_do_update(
            index_elements=unique_keys,
            set_=update_cols
        )
    elif dialect == 'sqlite':
        # SQLite: INSERT OR REPLACE
        stmt = sqlite_insert(table).values(data)
        update_cols = {c.name: stmt.excluded[c.name] for c in table.c if c.name not in unique_keys}
        stmt = stmt.on_conflict_do_update(
            index_elements=unique_keys,
            set_=update_cols
        )
    else:
        # 通用方案: 逐条处理
        count = 0
        for row in data:
            existing = session.query(model).filter_by(
                **{k: row[k] for k in unique_keys}
            ).first()
            if existing:
                for key, value in row.items():
                    setattr(existing, key, value)
            else:
                session.add(model(**row))
            count += 1
        session.commit()
        return count
    
    result = session.execute(stmt)
    session.commit()
    return result.rowcount


# ============================================================
# 数据库初始化
# ============================================================

def init_database(db_url: str | None = None, echo: bool = False):
    """
    初始化数据库
    
    Args:
        db_url: 数据库连接字符串
        echo: 是否打印 SQL
        
    Returns:
        engine, Session
    """
    if db_url is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "stocks.db"
        db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=echo)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("AI-Ready 金融数据库模型")
    print("=" * 60)
    
    # 初始化
    engine, Session = init_database(echo=False)
    
    # 打印表信息
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"\n📊 已创建 {len(tables)} 个表:")
    for table in tables:
        columns = inspector.get_columns(table)
        indexes = inspector.get_indexes(table)
        print(f"   - {table}: {len(columns)} 列, {len(indexes)} 索引")
    
    print("\n✅ 数据库初始化完成!")
