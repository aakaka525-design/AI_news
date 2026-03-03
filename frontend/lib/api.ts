import { API_BASE_URL } from "./api-config";
import type {
  AnomaliesResponse,
  AnomalyStats,
  DragonTigerResponse,
  FreshnessResponse,
  HealthResponse,
  HotspotsResponse,
  IndustryListResponse,
  MarketOverviewResponse,
  MoneyFlowResponse,
  NewsListResponse,
  RatingStats,
  ResearchReportsResponse,
  RssResponse,
  SchedulerJobsResponse,
  SectorResponse,
  SentimentStats,
  StockDailyResponse,
  StockListResponse,
  StockProfileResponse,
  TradingDayResponse,
} from "./types";

async function fetchApi<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
  }
  const apiKey = process.env.NEXT_PUBLIC_DASHBOARD_API_KEY;
  const headers: HeadersInit = apiKey ? { "X-API-Key": apiKey } : {};
  const res = await fetch(url.toString(), { headers });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  const data: unknown = await res.json();
  if (data && typeof data === "object") {
    const payload = data as { error?: unknown; detail?: unknown };
    if (typeof payload.error === "string" && payload.error.trim()) {
      throw new Error(payload.error);
    }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      throw new Error(payload.detail);
    }
  }
  return data as T;
}

// Health
export const fetchHealth = () => fetchApi<HealthResponse>("/health");

// News
export const fetchNews = (limit = 50) =>
  fetchApi<NewsListResponse>("/api/news", { limit: String(limit) });

// Hotspots
export const fetchHotspots = () => fetchApi<HotspotsResponse>("/api/hotspots");

// RSS
export const fetchRss = (limit = 50) =>
  fetchApi<RssResponse>("/api/rss", { limit: String(limit) });

export const fetchSentimentStats = () =>
  fetchApi<SentimentStats>("/api/rss/sentiment_stats");

// Research Reports
export const fetchReports = (stockCode?: string, limit = 20) =>
  fetchApi<ResearchReportsResponse>("/api/research/reports", {
    ...(stockCode ? { stock_code: stockCode } : {}),
    limit: String(limit),
  });

export const fetchRatingStats = () =>
  fetchApi<RatingStats>("/api/research/stats");

// Anomalies
export const fetchAnomalies = (stockCode?: string, days = 7, limit = 50) =>
  fetchApi<AnomaliesResponse>("/api/anomalies", {
    ...(stockCode ? { stock_code: stockCode } : {}),
    days: String(days),
    limit: String(limit),
  });

export const fetchAnomalyStats = () =>
  fetchApi<AnomalyStats>("/api/anomalies/stats");

// Scheduler
export const fetchSchedulerJobs = () =>
  fetchApi<SchedulerJobsResponse>("/api/scheduler/jobs");

async function postApi<T>(path: string, body?: unknown): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  const apiKey = process.env.NEXT_PUBLIC_DASHBOARD_API_KEY;
  const headers: HeadersInit = { "Content-Type": "application/json", ...(apiKey ? { "X-API-Key": apiKey } : {}) };
  const res = await fetch(url.toString(), {
    method: "POST",
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  const data: unknown = await res.json();
  if (data && typeof data === "object") {
    const payload = data as { error?: unknown; detail?: unknown };
    if (typeof payload.error === "string" && payload.error.trim()) {
      throw new Error(payload.error);
    }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      throw new Error(payload.detail);
    }
  }
  return data as T;
}

export const triggerJob = (jobId: string) =>
  postApi<{ success: boolean; message: string; duration: number }>(`/api/scheduler/trigger/${jobId}`);

export const pauseJob = (jobId: string) =>
  postApi<{ message: string }>(`/api/scheduler/pause/${jobId}`);

export const resumeJob = (jobId: string) =>
  postApi<{ message: string }>(`/api/scheduler/resume/${jobId}`);

// News facts (detail)
export const fetchNewsFacts = (newsId: number) =>
  fetchApi<{
    title: string;
    summary: string;
    facts: Array<{ fact: string; category: string }>;
    hotspots: string[];
    keywords: string[];
    cleaned_at: string;
  }>(`/api/facts/${newsId}`);

// AI Analysis result
export const fetchAnalysisResult = (analysisId: number) =>
  fetchApi<{
    id: number;
    date: string;
    input_count: number;
    analysis_summary: string;
    opportunities: Array<{
      type?: string;
      score?: number;
      title?: string;
      reasoning?: string;
    }>;
    analyzed_at: string;
  }>(`/api/analysis/${analysisId}`);

// Manual triggers
export const fetchRssManual = () =>
  postApi<{ status: string; fetched: number; sources: string[] }>("/api/rss/fetch");

export const fetchResearchManual = (stockCode?: string) =>
  postApi<{ fetched: number; saved?: number; stock_code?: string }>(
    "/api/research/fetch",
    stockCode ? { stock_code: stockCode } : undefined,
  );

export const detectAnomaliesManual = (stockCode?: string) =>
  postApi<{ result: Record<string, number>; stock_code?: string }>(
    "/api/anomalies/detect",
    stockCode ? { stock_code: stockCode } : undefined,
  );

export const analyzeManual = (date?: string) =>
  postApi<{ analysis_summary?: string; analysis_id?: number; input_count?: number; date?: string; error?: string }>(
    "/api/analyze",
    date ? { date } : undefined,
  );

// Integrity
export const fetchIntegrityCheck = () =>
  fetchApi<{
    generated_at: string;
    checks: { freshness: Array<{ name: string; status: string; latest_date?: string }>; daily_coverage?: Record<string, unknown>; anomalies?: Array<Record<string, unknown>> };
    summary: { stale_tables: number; empty_tables: number; low_coverage_days: number; total_issues: number };
  }>("/api/integrity/check");

// Calendar
export const fetchTradingDay = (date?: string) =>
  fetchApi<TradingDayResponse>(
    "/api/calendar/is_trading_day",
    date ? { date } : {},
  );

// Freshness
export const fetchFreshness = () =>
  fetchApi<FreshnessResponse>("/api/integrity/freshness");

// ===== Stocks =====

export const fetchStocks = (
  page = 1,
  pageSize = 20,
  search?: string,
  industry?: string,
  market?: string,
) =>
  fetchApi<StockListResponse>("/api/stocks", {
    page: String(page),
    page_size: String(pageSize),
    ...(search ? { search } : {}),
    ...(industry ? { industry } : {}),
    ...(market ? { market } : {}),
  });

export const fetchStockIndustries = () =>
  fetchApi<IndustryListResponse>("/api/stocks/industries");

export const fetchStockProfile = (tsCode: string) =>
  fetchApi<StockProfileResponse>(`/api/stocks/${tsCode}/profile`);

export const fetchStockDaily = (
  tsCode: string,
  startDate?: string,
  endDate?: string,
  limit = 250,
) =>
  fetchApi<StockDailyResponse>(`/api/stocks/${tsCode}/daily`, {
    limit: String(limit),
    ...(startDate ? { start_date: startDate } : {}),
    ...(endDate ? { end_date: endDate } : {}),
  });

export const fetchMarketOverview = (tradeDate?: string) =>
  fetchApi<MarketOverviewResponse>("/api/market/overview", {
    ...(tradeDate ? { trade_date: tradeDate } : {}),
  });

export const fetchMoneyFlow = (
  tradeDate?: string,
  flowType?: string,
  tsCode?: string,
  limit = 50,
) =>
  fetchApi<MoneyFlowResponse>("/api/money-flow", {
    limit: String(limit),
    ...(tradeDate ? { trade_date: tradeDate } : {}),
    ...(flowType ? { flow_type: flowType } : {}),
    ...(tsCode ? { ts_code: tsCode } : {}),
  });

export const fetchDragonTiger = (tradeDate?: string, tsCode?: string, limit = 50) =>
  fetchApi<DragonTigerResponse>("/api/dragon-tiger", {
    limit: String(limit),
    ...(tradeDate ? { trade_date: tradeDate } : {}),
    ...(tsCode ? { ts_code: tsCode } : {}),
  });

export const fetchSectors = (blockType?: string, tradeDate?: string, limit = 50) =>
  fetchApi<SectorResponse>("/api/sectors", {
    limit: String(limit),
    ...(blockType ? { block_type: blockType } : {}),
    ...(tradeDate ? { trade_date: tradeDate } : {}),
  });
