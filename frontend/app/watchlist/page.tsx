"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { Star, Trash2 } from "lucide-react";
import { useWatchlist } from "@/lib/use-watchlist";
import { useStocks } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { StockBasicItem } from "@/lib/types";

/* ---------- helpers ---------- */

function formatAmount(v?: number | null): string {
  if (v == null) return "\u2014";
  if (v >= 100000) return `${(v / 100000).toFixed(2)} \u4ebf`;
  if (v >= 10) return `${v.toFixed(0)} \u4e07`;
  return `${v.toFixed(2)} \u4e07`;
}

/* ---------- empty state ---------- */

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
      <Star className="h-12 w-12 mb-4 opacity-30" />
      <p className="text-sm">{"\u6682\u65e0\u81ea\u9009\u80a1\uff0c\u8bf7\u5728\u4e2a\u80a1\u8be6\u60c5\u9875\u6dfb\u52a0"}</p>
    </div>
  );
}

/* ---------- loading skeleton ---------- */

function TableSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

/* ---------- main page ---------- */

export default function WatchlistPage() {
  const router = useRouter();
  const { codes, remove } = useWatchlist();

  // Fetch all stocks with a large page size and filter client-side.
  // We pass the first watchlist code as search to warm the query key,
  // but actually we fetch broadly and filter.
  const { data: stocksData, isLoading } = useStocks(
    1,
    5000, // large page to cover watchlist
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
  );

  const watchlistStocks: StockBasicItem[] = useMemo(() => {
    if (!stocksData?.data || codes.length === 0) return [];
    const codeSet = new Set(codes);
    // Filter and preserve watchlist order
    const stockMap = new Map<string, StockBasicItem>();
    for (const s of stocksData.data) {
      if (codeSet.has(s.ts_code)) {
        stockMap.set(s.ts_code, s);
      }
    }
    return codes
      .map((c) => stockMap.get(c))
      .filter((s): s is StockBasicItem => s !== undefined);
  }, [stocksData, codes]);

  if (codes.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">{"\u81ea\u9009\u80a1"}</h1>
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{"\u81ea\u9009\u80a1"}</h1>
        <Badge variant="secondary" className="text-sm">
          {codes.length} {"\u53ea"}
        </Badge>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left py-3 px-4 font-medium">{"\u4ee3\u7801"}</th>
                    <th className="text-left py-3 px-4 font-medium">{"\u540d\u79f0"}</th>
                    <th className="text-right py-3 px-4 font-medium">{"\u6700\u65b0\u4ef7"}</th>
                    <th className="text-right py-3 px-4 font-medium">{"\u6da8\u8dcc\u5e45"}</th>
                    <th className="text-right py-3 px-4 font-medium">{"\u6210\u4ea4\u989d"}</th>
                    <th className="text-center py-3 px-4 font-medium">{"\u64cd\u4f5c"}</th>
                  </tr>
                </thead>
                <tbody>
                  {watchlistStocks.map((stock) => {
                    const pctChg = stock.pct_chg;
                    const pctColor =
                      pctChg == null
                        ? ""
                        : pctChg >= 0
                          ? "text-red-500"
                          : "text-green-500";

                    return (
                      <tr
                        key={stock.ts_code}
                        className="border-b hover:bg-muted/30 cursor-pointer transition-colors"
                        onClick={() => router.push(`/market/${stock.ts_code}`)}
                      >
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs text-primary">
                            {stock.ts_code}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-medium">{stock.name}</td>
                        <td className="py-3 px-4 text-right">
                          {stock.close != null ? stock.close.toFixed(2) : "\u2014"}
                        </td>
                        <td className={`py-3 px-4 text-right font-medium ${pctColor}`}>
                          {pctChg != null
                            ? `${pctChg >= 0 ? "+" : ""}${pctChg.toFixed(2)}%`
                            : "\u2014"}
                        </td>
                        <td className="py-3 px-4 text-right text-muted-foreground">
                          {formatAmount(stock.amount)}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              remove(stock.ts_code);
                            }}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                  {/* Stocks in watchlist but not found in data */}
                  {codes
                    .filter((c) => !watchlistStocks.some((s) => s.ts_code === c))
                    .map((code) => (
                      <tr
                        key={code}
                        className="border-b hover:bg-muted/30 cursor-pointer transition-colors"
                        onClick={() => router.push(`/market/${code}`)}
                      >
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs text-primary">{code}</span>
                        </td>
                        <td className="py-3 px-4 text-muted-foreground">{"\u2014"}</td>
                        <td className="py-3 px-4 text-right text-muted-foreground">{"\u2014"}</td>
                        <td className="py-3 px-4 text-right text-muted-foreground">{"\u2014"}</td>
                        <td className="py-3 px-4 text-right text-muted-foreground">{"\u2014"}</td>
                        <td className="py-3 px-4 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              remove(code);
                            }}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
