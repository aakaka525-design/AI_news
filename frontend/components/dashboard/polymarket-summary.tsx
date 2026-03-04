"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Target, ArrowRight, Clock } from "lucide-react";
import { usePolymarketMarkets } from "@/lib/hooks";
import { TAG_ZH, shortRelativeTime } from "@/lib/polymarket-utils";

export function PolymarketSummary() {
  const { data, isLoading, isError } = usePolymarketMarkets(200);

  if (isLoading) return <Skeleton className="h-[340px]" />;

  if (isError) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">预测市场</CardTitle>
          <Target className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">数据加载失败，请稍后重试</p>
        </CardContent>
      </Card>
    );
  }

  const markets = data?.data ?? [];

  if (markets.length === 0) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">预测市场</CardTitle>
          <Target className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暂无预测市场数据</p>
        </CardContent>
      </Card>
    );
  }

  // Show top volatile / interesting markets (sort by how close to 50%)
  const sorted = [...markets].sort((a, b) => {
    const aP = a.outcome_prices?.[0] ?? 0;
    const bP = b.outcome_prices?.[0] ?? 0;
    return Math.abs(aP - 0.5) - Math.abs(bP - 0.5);
  });

  const top = sorted.slice(0, 8);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">预测市场热点</CardTitle>
        <Link
          href="/polymarket"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          查看全部
          <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[280px]">
          <div className="space-y-2">
            {top.map((m) => {
              const price = m.outcome_prices?.[0];
              const pct = price != null ? Math.round(price * 100) : null;
              const isHigh = pct != null && pct >= 50;
              return (
                <Link
                  key={m.condition_id}
                  href={`/polymarket?market=${m.condition_id}`}
                  className="flex items-center gap-3 rounded-md border p-2.5 hover:bg-muted/50 transition-colors"
                >
                  {m.image && (
                    <img
                      src={m.image}
                      alt=""
                      className="w-9 h-9 rounded object-cover shrink-0"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium leading-snug line-clamp-1">
                      {m.question_zh || m.question}
                    </p>
                    {m.tags && m.tags.length > 0 && (
                      <div className="flex gap-1 mt-0.5">
                        {m.tags.slice(0, 2).map((t) => (
                          <Badge
                            key={t}
                            variant="secondary"
                            className="text-[10px] px-1 py-0"
                          >
                            {TAG_ZH[t] ?? t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    {(() => {
                      const rel = m.end_date ? shortRelativeTime(m.end_date) : null;
                      return rel ? (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Clock className="h-3 w-3" />
                          {rel}
                        </span>
                      ) : null;
                    })()}
                    {pct != null && (
                      <div
                        className={`text-sm font-bold tabular-nums ${
                          isHigh ? "text-emerald-600" : "text-rose-500"
                        }`}
                      >
                        {pct}%
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
