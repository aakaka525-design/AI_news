/** Shared constants and utilities for Polymarket components. */

/** English tag → Chinese display label */
export const TAG_ZH: Record<string, string> = {
  Politics: "政治",
  Finance: "金融",
  Sports: "体育",
  Crypto: "加密货币",
  AI: "AI",
  Tech: "科技",
  Culture: "文化",
  World: "国际",
  Science: "科学",
  Entertainment: "娱乐",
  Business: "商业",
};

/** Tag filter options (subset used for filter buttons) */
export const TAG_FILTERS: { value: string; label: string }[] = [
  { value: "Politics", label: "政治" },
  { value: "Finance", label: "金融" },
  { value: "Sports", label: "体育" },
  { value: "Crypto", label: "加密货币" },
  { value: "AI", label: "AI" },
  { value: "Tech", label: "科技" },
  { value: "Culture", label: "文化" },
  { value: "World", label: "国际" },
];

/** English outcome → Chinese display label */
export const OUTCOME_ZH: Record<string, string> = {
  Yes: "是",
  No: "否",
};

/** Format a date string as relative time in Chinese (e.g. "3天后", "2小时前", "已截止") */
export function formatRelativeTime(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  const absDiff = Math.abs(diff);
  const suffix = diff >= 0 ? "后" : "前";

  if (diff < 0 && absDiff < 60_000) return "已截止";

  const minutes = Math.floor(absDiff / 60_000);
  const hours = Math.floor(absDiff / 3_600_000);
  const days = Math.floor(absDiff / 86_400_000);
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);

  if (months >= 1) return `${months}个月${suffix}`;
  if (weeks >= 1) return `${weeks}周${suffix}`;
  if (days >= 1) return `${days}天${suffix}`;
  if (hours >= 1) return `${hours}小时${suffix}`;
  return `${minutes}分钟${suffix}`;
}

/** Short relative time label for compact display (e.g. "3天", "1周") */
export function shortRelativeTime(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  if (diff <= 0) return "已截止";
  const days = Math.floor(diff / 86_400_000);
  if (days >= 30) return `${Math.floor(days / 30)}月`;
  if (days >= 7) return `${Math.floor(days / 7)}周`;
  if (days >= 1) return `${days}天`;
  const hours = Math.floor(diff / 3_600_000);
  if (hours >= 1) return `${hours}时`;
  return `<1时`;
}

/** Format how long ago data was updated */
export function formatFreshness(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return "刚刚更新";
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes} 分钟前更新`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前更新`;
  const days = Math.floor(hours / 24);
  return `${days} 天前更新`;
}
