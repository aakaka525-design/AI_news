import { API_BASE_URL } from "./api-config";
import type {
  AnomaliesResponse,
  AnomalyStats,
  FreshnessResponse,
  HealthResponse,
  HotspotsResponse,
  NewsListResponse,
  RatingStats,
  ResearchReportsResponse,
  RssResponse,
  SchedulerJobsResponse,
  SentimentStats,
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
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
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

// Calendar
export const fetchTradingDay = (date?: string) =>
  fetchApi<TradingDayResponse>(
    "/api/calendar/is_trading_day",
    date ? { date } : {},
  );

// Freshness
export const fetchFreshness = () =>
  fetchApi<FreshnessResponse>("/api/integrity/freshness");
