"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useDebounce } from "@/lib/use-debounce";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { PriceHistoryChart } from "@/components/charts/price-history-chart";
import { usePolymarketMarkets, usePolymarketHistory } from "@/lib/hooks";
import type { PolymarketMarket } from "@/lib/types";
import {
  TAG_ZH,
  TAG_FILTERS,
  OUTCOME_ZH,
  formatRelativeTime,
  formatFreshness,
} from "@/lib/polymarket-utils";
import { ChevronDown, ChevronUp, Target, TrendingUp, Clock } from "lucide-react";

function OutcomeBar({
  outcomes,
  prices,
  size = "sm",
}: {
  outcomes?: string[] | null;
  prices?: number[] | null;
  size?: "sm" | "lg";
}) {
  if (!prices || prices.length === 0 || !outcomes) return null;

  const h = size === "lg" ? "h-6" : "h-4";
  const textSize = size === "lg" ? "text-sm" : "text-xs";

  return (
    <div className="space-y-1.5">
      {outcomes.map((outcome, i) => {
        const price = prices[i];
        if (price == null) return null;
        const pct = (price * 100).toFixed(0);
        const isYes = i === 0;
        const barColor = isYes ? "bg-emerald-500" : "bg-rose-400";
        const label = OUTCOME_ZH[outcome] ?? outcome;
        return (
          <div key={outcome} className="flex items-center gap-2">
            <span
              className={`${textSize} w-10 shrink-0 font-medium ${isYes ? "text-emerald-600" : "text-rose-500"}`}
            >
              {label}
            </span>
            <div className={`flex-1 ${h} rounded bg-muted overflow-hidden`}>
              <div
                className={`h-full rounded ${barColor} transition-all duration-500`}
                style={{ width: `${price * 100}%` }}
              />
            </div>
            <span
              className={`${textSize} font-bold tabular-nums w-12 text-right`}
            >
              {pct}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MarketCard({
  market,
  onClick,
}: {
  market: PolymarketMarket;
  onClick: () => void;
}) {
  const yesPrice = market.outcome_prices?.[0];
  const yesPct = yesPrice != null ? (yesPrice * 100).toFixed(0) : null;

  return (
    <Card
      className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex gap-3">
          {/* Thumbnail */}
          {market.image && (
            <img
              src={market.image}
              alt=""
              className="w-14 h-14 rounded-lg object-cover shrink-0"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          )}
          <div className="flex-1 min-w-0">
            {/* Question */}
            <p className="text-sm font-medium leading-snug line-clamp-2">
              {market.question_zh || market.question}
            </p>
            {/* Tags + deadline */}
            <div className="flex flex-wrap items-center gap-1 mt-1.5">
              {market.tags?.slice(0, 3).map((tag) => (
                <Badge
                  key={tag}
                  variant="secondary"
                  className="text-[10px] px-1.5 py-0"
                >
                  {TAG_ZH[tag] ?? tag}
                </Badge>
              ))}
              {market.end_date && (() => {
                const rel = formatRelativeTime(market.end_date);
                return rel ? (
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    <Clock className="inline h-3 w-3 mr-0.5 -mt-px" />
                    {rel === "已截止" ? rel : `${rel}截止`}
                  </span>
                ) : null;
              })()}
            </div>
          </div>
          {/* Big probability circle */}
          {yesPct && (
            <div className="shrink-0 flex flex-col items-center justify-center">
              <div
                className={`w-14 h-14 rounded-full border-[3px] flex items-center justify-center ${
                  Number(yesPct) >= 50
                    ? "border-emerald-500 text-emerald-600"
                    : "border-rose-400 text-rose-500"
                }`}
              >
                <span className="text-base font-bold tabular-nums">
                  {yesPct}%
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-0.5">
                是
              </span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function PolymarketPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { data, isLoading, isError } = usePolymarketMarkets(200);
  const [selected, setSelected] = useState<PolymarketMarket | null>(null);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 200);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "closed">("all");
  const [descExpanded, setDescExpanded] = useState(false);
  const history = usePolymarketHistory(selected?.condition_id ?? null);

  const markets = data?.data ?? [];

  // 关闭 Sheet 时清除 URL 中的 market 参数，防止 useEffect 重新打开
  const closeSheet = useCallback(() => {
    setSelected(null);
    const params = new URLSearchParams(searchParams.toString());
    if (params.has("market")) {
      params.delete("market");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    }
  }, [searchParams, router, pathname]);

  // Auto-open market from URL search param (deep link from dashboard)
  const marketParam = searchParams.get("market");
  useEffect(() => {
    if (marketParam && markets.length > 0 && !selected) {
      const found = markets.find((m) => m.condition_id === marketParam);
      if (found) setSelected(found);
    }
  }, [marketParam, markets, selected]);

  // Filter
  const filtered = useMemo(() => {
    let result = markets;
    if (statusFilter === "active") {
      result = result.filter((m) => m.active && !m.closed);
    } else if (statusFilter === "closed") {
      result = result.filter((m) => m.closed || !m.active);
    }
    if (activeTag) {
      result = result.filter((m) => m.tags?.includes(activeTag));
    }
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter(
        (m) =>
          m.question.toLowerCase().includes(q) ||
          (m.question_zh && m.question_zh.toLowerCase().includes(q)) ||
          m.tags?.some(
            (tag) =>
              tag.toLowerCase().includes(q) ||
              (TAG_ZH[tag] ?? "").toLowerCase().includes(q)
          )
      );
    }
    return result;
  }, [markets, activeTag, debouncedSearch, statusFilter]);

  // Data freshness — take the most recent updated_at across all markets
  const latestUpdate = useMemo(() => {
    let max: string | null = null;
    for (const m of markets) {
      if (m.updated_at && (!max || m.updated_at > max)) max = m.updated_at;
    }
    return max;
  }, [markets]);

  // Stats
  const totalMarkets = markets.length;
  const highConfidence = markets.filter((m) => {
    const p = m.outcome_prices?.[0];
    return p != null && (p >= 0.9 || p <= 0.1);
  }).length;
  const ending7d = markets.filter((m) => {
    if (!m.end_date) return false;
    const diff =
      new Date(m.end_date).getTime() - Date.now();
    return diff > 0 && diff < 7 * 86400000;
  }).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">预测市场</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Polymarket 活跃预测市场 — 实时概率追踪
        </p>
      </div>

      {/* Stats cards */}
      {isLoading ? (
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-500/10">
                <Target className="h-5 w-5 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{totalMarkets}</p>
                <p className="text-xs text-muted-foreground">活跃市场</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/10">
                <TrendingUp className="h-5 w-5 text-emerald-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{highConfidence}</p>
                <p className="text-xs text-muted-foreground">
                  高确定性 (&gt;90%)
                </p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-500/10">
                <Clock className="h-5 w-5 text-amber-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{ending7d}</p>
                <p className="text-xs text-muted-foreground">7天内截止</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Data freshness */}
      {latestUpdate && (
        <p className="text-xs text-muted-foreground -mt-3">
          数据{formatFreshness(latestUpdate)}
        </p>
      )}

      {/* Search + Status + Tag filters */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            placeholder="搜索市场问题..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />
          <div className="flex gap-1">
            {([
              { value: "all", label: "全部" },
              { value: "active", label: "活跃" },
              { value: "closed", label: "已截止" },
            ] as const).map((s) => (
              <Badge
                key={s.value}
                variant={statusFilter === s.value ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => setStatusFilter(s.value)}
              >
                {s.label}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge
            variant={activeTag === null ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setActiveTag(null)}
          >
            全部
          </Badge>
          {TAG_FILTERS.map((t) => (
            <Badge
              key={t.value}
              variant={activeTag === t.value ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setActiveTag(activeTag === t.value ? null : t.value)}
            >
              {t.label}
            </Badge>
          ))}
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="text-sm text-destructive py-8 text-center">
          数据加载失败，请稍后重试
        </div>
      )}

      {/* Market cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          没有匹配的市场
        </p>
      ) : (
        <ScrollArea className="h-[calc(100vh-24rem)]">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pr-3">
            {filtered.map((market) => (
              <MarketCard
                key={market.condition_id}
                market={market}
                onClick={() => {
                  setSelected(market);
                  setDescExpanded(false);
                }}
              />
            ))}
          </div>
        </ScrollArea>
      )}

      {/* Detail sheet */}
      <Sheet
        open={selected !== null}
        onOpenChange={(open) => { if (!open) closeSheet(); }}
      >
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle className="text-base leading-tight pr-6">
              {selected?.question_zh || selected?.question || "市场详情"}
            </SheetTitle>
            <SheetDescription className="flex items-center gap-2">
              {selected?.end_date && (
                <span>
                  截止:{" "}
                  {new Date(selected.end_date).toLocaleDateString("zh-CN")}
                  {" "}
                  <span className="text-muted-foreground">
                    ({formatRelativeTime(selected.end_date)})
                  </span>
                </span>
              )}
              {selected?.active && (
                <Badge
                  variant="outline"
                  className="text-[10px] text-emerald-600 border-emerald-300"
                >
                  活跃
                </Badge>
              )}
            </SheetDescription>
          </SheetHeader>

          {selected && (
            <div className="mt-4 space-y-5">
              {/* Outcome bars */}
              <OutcomeBar
                outcomes={selected.outcomes}
                prices={selected.outcome_prices}
                size="lg"
              />

              {/* Price history chart */}
              <div>
                <h3 className="text-sm font-medium mb-2">概率走势</h3>
                {history.isLoading ? (
                  <Skeleton className="h-[280px] rounded-lg" />
                ) : (
                  <div className="rounded-lg border p-2">
                    <PriceHistoryChart
                      snapshots={history.data?.data ?? []}
                      outcomes={selected.outcomes}
                    />
                  </div>
                )}
              </div>

              {/* Description (collapsible) */}
              {selected.description && (
                <div>
                  <button
                    className="flex items-center gap-1 text-sm font-medium hover:text-primary transition-colors"
                    onClick={() => setDescExpanded(!descExpanded)}
                  >
                    市场规则
                    {descExpanded ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </button>
                  {descExpanded && (
                    <p className="mt-2 text-sm text-muted-foreground whitespace-pre-line leading-relaxed">
                      {selected.description}
                    </p>
                  )}
                </div>
              )}

              {/* Tags */}
              {selected.tags && selected.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {selected.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-xs">
                      {TAG_ZH[tag] ?? tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
