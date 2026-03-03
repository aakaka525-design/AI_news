import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchHealth,
  fetchHotspots,
  fetchSentimentStats,
  fetchAnomalies,
  fetchAnomalyStats,
  fetchReports,
  fetchRatingStats,
  fetchNews,
  fetchRss,
  fetchSchedulerJobs,
  fetchFreshness,
  fetchTradingDay,
  fetchIntegrityCheck,
  fetchNewsFacts,
  triggerJob,
  pauseJob,
  resumeJob,
  fetchRssManual,
  fetchResearchManual,
  detectAnomaliesManual,
  analyzeManual,
  fetchStocks,
  fetchStockIndustries,
  fetchStockProfile,
  fetchStockDaily,
  fetchMarketOverview,
  fetchMoneyFlow,
  fetchDragonTiger,
  fetchSectors,
} from "./api";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 60_000 });

export const useHotspots = () =>
  useQuery({ queryKey: ["hotspots"], queryFn: fetchHotspots });

export const useSentimentStats = () =>
  useQuery({ queryKey: ["sentiment-stats"], queryFn: fetchSentimentStats });

export const useAnomalies = (stockCode?: string, days = 7, limit = 50) =>
  useQuery({
    queryKey: ["anomalies", stockCode, days, limit],
    queryFn: () => fetchAnomalies(stockCode, days, limit),
  });

export const useAnomalyStats = () =>
  useQuery({ queryKey: ["anomaly-stats"], queryFn: fetchAnomalyStats });

export const useReports = (stockCode?: string, limit = 20) =>
  useQuery({
    queryKey: ["reports", stockCode, limit],
    queryFn: () => fetchReports(stockCode, limit),
  });

export const useRatingStats = () =>
  useQuery({ queryKey: ["rating-stats"], queryFn: fetchRatingStats });

export const useNews = (limit = 50) =>
  useQuery({ queryKey: ["news", limit], queryFn: () => fetchNews(limit) });

export const useRss = (limit = 50) =>
  useQuery({ queryKey: ["rss", limit], queryFn: () => fetchRss(limit) });

export const useSchedulerJobs = () =>
  useQuery({ queryKey: ["scheduler-jobs"], queryFn: fetchSchedulerJobs });

export function useJobAction() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["scheduler-jobs"] });

  const trigger = useMutation({ mutationFn: triggerJob, onSuccess: invalidate });
  const pause = useMutation({ mutationFn: pauseJob, onSuccess: invalidate });
  const resume = useMutation({ mutationFn: resumeJob, onSuccess: invalidate });

  return { trigger, pause, resume };
}

export const useFreshness = () =>
  useQuery({ queryKey: ["freshness"], queryFn: fetchFreshness });

export const useIntegrityCheck = () =>
  useQuery({ queryKey: ["integrity-check"], queryFn: fetchIntegrityCheck, enabled: false });

export const useNewsFacts = (newsId: number | null) =>
  useQuery({
    queryKey: ["news-facts", newsId],
    queryFn: () => fetchNewsFacts(newsId!),
    enabled: newsId !== null,
  });

export function useManualActions() {
  const qc = useQueryClient();

  const fetchRss = useMutation({
    mutationFn: fetchRssManual,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rss"] }),
  });
  const fetchResearch = useMutation({
    mutationFn: fetchResearchManual,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
  const detectAnomalies = useMutation({
    mutationFn: detectAnomaliesManual,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["anomalies"] }),
  });
  const analyze = useMutation({
    mutationFn: analyzeManual,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["news"] }),
  });

  return { fetchRss, fetchResearch, detectAnomalies, analyze };
}

export const useTradingDay = (date?: string) =>
  useQuery({ queryKey: ["trading-day", date], queryFn: () => fetchTradingDay(date) });

// ===== Stocks =====

export const useStocks = (
  page = 1,
  pageSize = 20,
  search?: string,
  industry?: string,
  market?: string,
) =>
  useQuery({
    queryKey: ["stocks", page, pageSize, search, industry, market],
    queryFn: () => fetchStocks(page, pageSize, search, industry, market),
    placeholderData: (prev) => prev,
  });

export const useStockIndustries = () =>
  useQuery({ queryKey: ["stock-industries"], queryFn: fetchStockIndustries });

export const useStockProfile = (tsCode: string) =>
  useQuery({
    queryKey: ["stock-profile", tsCode],
    queryFn: () => fetchStockProfile(tsCode),
    enabled: !!tsCode,
  });

export const useStockDaily = (tsCode: string, limit = 250) =>
  useQuery({
    queryKey: ["stock-daily", tsCode, limit],
    queryFn: () => fetchStockDaily(tsCode, undefined, undefined, limit),
    enabled: !!tsCode,
  });

export const useMarketOverview = (tradeDate?: string) =>
  useQuery({
    queryKey: ["market-overview", tradeDate],
    queryFn: () => fetchMarketOverview(tradeDate),
  });

export const useMoneyFlow = (tradeDate?: string, flowType?: string, tsCode?: string, limit = 50) =>
  useQuery({
    queryKey: ["money-flow", tradeDate, flowType, tsCode, limit],
    queryFn: () => fetchMoneyFlow(tradeDate, flowType, tsCode, limit),
  });

export const useDragonTiger = (tradeDate?: string, tsCode?: string, limit = 50) =>
  useQuery({
    queryKey: ["dragon-tiger", tradeDate, tsCode, limit],
    queryFn: () => fetchDragonTiger(tradeDate, tsCode, limit),
  });

export const useSectors = (blockType?: string, tradeDate?: string, limit = 50) =>
  useQuery({
    queryKey: ["sectors", blockType, tradeDate, limit],
    queryFn: () => fetchSectors(blockType, tradeDate, limit),
  });
