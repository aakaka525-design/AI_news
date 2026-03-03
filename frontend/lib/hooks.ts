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
  triggerJob,
  pauseJob,
  resumeJob,
  fetchRssManual,
  fetchResearchManual,
  detectAnomaliesManual,
  analyzeManual,
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
