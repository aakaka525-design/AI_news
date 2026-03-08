// ===== News =====
export interface NewsItem {
  id: number;
  title: string;
  content: string;
  content_html: string;
  received_at: string;
  cleaned_data?: {
    summary?: string;
    facts?: Array<{ fact: string; category: string }>;
    hotspots?: string[];
    keywords?: string[];
    cleaned_at?: string;
  } | null;
  source?: string | null;
}

export interface NewsListResponse {
  total: number;
  data: NewsItem[];
}

// ===== Hotspots =====
export interface HotspotItem {
  keyword: string;
  count: number;
}

export interface HotspotsResponse {
  total: number;
  data: HotspotItem[];
}

// ===== RSS =====
export interface RssItem {
  id: number;
  title: string;
  link?: string;
  summary?: string;
  source?: string;
  published?: string;
  sentiment_score?: number;
  sentiment_label?: string;
}

export interface RssResponse {
  total: number;
  data: RssItem[];
}

export interface SentimentStats {
  analyzed_count: number;
  pending_count: number;
  distribution: {
    positive?: number;
    neutral?: number;
    negative?: number;
    [key: string]: number | undefined;
  };
}

// ===== Research Reports =====
export interface ResearchReport {
  id?: number;
  ts_code?: string;
  stock_name?: string;
  title: string;
  institution?: string;
  rating?: string;
  target_price?: number | null;
  publish_date?: string;
  key_points?: string[];
  sentiment_score?: number | null;
}

export interface ResearchReportsResponse {
  total: number;
  data: ResearchReport[];
}

export interface RatingStats {
  [rating: string]: number;
}

// ===== Anomalies =====
export interface AnomalySignal {
  id?: number;
  stock_code: string;
  stock_name?: string;
  date?: string;
  signal_type: string;
  description?: string;
  severity?: string;
}

export interface AnomaliesResponse {
  total: number;
  data: AnomalySignal[];
}

export interface AnomalyStats {
  [signal_type: string]: number;
}

// ===== Stocks =====
export interface StockBasicItem {
  ts_code: string;
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
  area?: string;
  list_date?: string;
  close?: number | null;
  pct_chg?: number | null;
  amount?: number | null;
  turnover_rate?: number | null;
  total_mv?: number | null;
}

export interface StockListResponse {
  total: number;
  page: number;
  page_size: number;
  data: StockBasicItem[];
}

export interface ValuationItem {
  trade_date: string;
  pe?: number | null;
  pe_ttm?: number | null;
  pb?: number | null;
  ps?: number | null;
  ps_ttm?: number | null;
  dv_ratio?: number | null;
  dv_ttm?: number | null;
  total_mv?: number | null;
  circ_mv?: number | null;
  total_share?: number | null;
  float_share?: number | null;
  turnover_rate?: number | null;
  volume_ratio?: number | null;
}

export interface StockProfileResponse {
  ts_code: string;
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
  area?: string;
  exchange?: string;
  list_date?: string;
  fullname?: string;
  is_hs?: string;
  valuation?: ValuationItem | null;
}

export interface ValuationHistoryItem {
  trade_date: string;
  pe_ttm?: number | null;
  pb?: number | null;
  ps_ttm?: number | null;
  dv_ttm?: number | null;
  total_mv?: number | null;
}

export interface ValuationHistoryResponse {
  data: ValuationHistoryItem[];
}

export interface StockDailyItem {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pre_close?: number;
  change?: number;
  pct_chg?: number;
  vol?: number;
  amount?: number;
  turnover_rate?: number;
}

export interface StockDailyResponse {
  data: StockDailyItem[];
}

export interface IndexItem {
  ts_code: string;
  trade_date: string;
  open?: number;
  high?: number;
  low?: number;
  close: number;
  pre_close?: number;
  change?: number;
  pct_chg: number;
  vol?: number;
  amount?: number;
  up_count?: number | null;
  down_count?: number | null;
}

export interface MarketOverviewResponse {
  data: IndexItem[];
}

export interface MoneyFlowItem {
  ts_code: string;
  trade_date: string;
  flow_type?: string;
  buy_elg_amount?: number | null;
  sell_elg_amount?: number | null;
  buy_lg_amount?: number | null;
  sell_lg_amount?: number | null;
  net_mf_amount?: number | null;
  net_mf_rate?: number | null;
  north_amount?: number | null;
  north_net?: number | null;
}

export interface MoneyFlowResponse {
  data: MoneyFlowItem[];
}

export interface DragonTigerItem {
  ts_code: string;
  trade_date: string;
  name?: string;
  close?: number;
  pct_chg?: number;
  turnover_rate?: number;
  amount?: number;
  l_buy?: number;
  l_sell?: number;
  net_amount?: number;
  net_rate?: number;
  reason?: string;
  inst_buy?: number | null;
  inst_sell?: number | null;
}

export interface DragonTigerResponse {
  data: DragonTigerItem[];
}

export interface SectorItem {
  block_code: string;
  block_name: string;
  block_type?: string;
  trade_date: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  pct_chg?: number;
  vol?: number;
  amount?: number;
  turnover_rate?: number;
  lead_stock?: string;
  up_count?: number | null;
  down_count?: number | null;
}

export interface SectorResponse {
  data: SectorItem[];
}

export interface IndustryListResponse {
  data: string[];
}

// ===== Health =====
export interface HealthResponse {
  status: "healthy" | "degraded";
  db: { url?: string; ok: boolean; error?: string | null };
  scheduler: { running: boolean; error?: string | null };
  version: string;
}

// ===== Scheduler =====
export interface SchedulerJob {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  next_run: string | null;
  last_run: string | null;
  last_result: string | null;
  run_count: number;
}

export interface SchedulerJobsResponse {
  running: boolean;
  jobs: SchedulerJob[];
}

// ===== Calendar =====
export interface TradingDayResponse {
  date: string;
  is_trading_day: boolean;
  latest_trading_day: string;
}

// ===== Data Freshness =====
export interface TableFreshness {
  table: string;
  latest_date?: string;
  row_count?: number;
  record_count?: number;
}

export interface FreshnessResponse {
  tables: TableFreshness[];
}

// ===== Polymarket =====
export interface PolymarketMarket {
  condition_id: string;
  question: string;
  question_zh?: string | null;
  description?: string | null;
  tags?: string[] | null;
  outcomes?: string[] | null;
  outcome_prices?: number[] | null;
  clob_token_ids?: string[] | null;
  image?: string | null;
  end_date?: string | null;
  active: boolean;
  closed: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PolymarketMarketsResponse {
  total: number;
  data: PolymarketMarket[];
}

export interface PolymarketSnapshot {
  id: number;
  market_id: string;
  outcome_prices: number[] | null;
  snapshot_time: string | null;
}

export interface PolymarketHistoryResponse {
  total: number;
  data: PolymarketSnapshot[];
}

// ===== Screener =====
export interface ScreenRpsItem {
  ts_code: string;
  stock_name: string | null;
  rps_10: number | null;
  rps_20: number | null;
  rps_50: number | null;
  rps_120: number | null;
  rank: number | null;
}

export interface ScreenRpsResponse {
  snapshot_date: string;
  source_trade_date: string;
  generated_at: string;
  total: number;
  items: ScreenRpsItem[];
}

export interface ScreenPotentialItem {
  ts_code: string;
  stock_name: string | null;
  total_score: number | null;
  capital_score: number | null;
  trading_score: number | null;
  fundamental_score: number | null;
  technical_score: number | null;
  signals: string | null;
  rank: number | null;
}

export interface ScreenPotentialResponse {
  snapshot_date: string;
  source_trade_date: string;
  generated_at: string;
  total: number;
  items: ScreenPotentialItem[];
}
