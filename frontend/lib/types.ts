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
  stock_code?: string;
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
