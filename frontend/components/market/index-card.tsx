"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { IndexItem } from "@/lib/types";

const INDEX_NAMES: Record<string, string> = {
  "000001.SH": "上证指数",
  "399001.SZ": "深证成指",
  "399006.SZ": "创业板指",
  "000300.SH": "沪深300",
  "000016.SH": "上证50",
  "399005.SZ": "中小100",
};

export function IndexCard({ item }: { item: IndexItem }) {
  const name = INDEX_NAMES[item.ts_code] ?? item.ts_code;
  const isUp = item.pct_chg >= 0;
  const color = isUp ? "text-red-500" : "text-green-500";

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-medium">{name}</span>
          <span className="text-xs text-muted-foreground">{item.trade_date}</span>
        </div>
        <div className={`text-xl font-bold ${color}`}>
          {item.close?.toFixed(2)}
        </div>
        <div className="flex gap-3 mt-1 text-sm">
          <span className={color}>
            {isUp ? "+" : ""}{item.change?.toFixed(2)}
          </span>
          <span className={color}>
            {isUp ? "+" : ""}{item.pct_chg?.toFixed(2)}%
          </span>
        </div>
        {(item.up_count != null || item.down_count != null) && (
          <div className="flex gap-2 mt-2 text-xs text-muted-foreground">
            <span className="text-red-500">{item.up_count ?? "—"} 涨</span>
            <span className="text-green-500">{item.down_count ?? "—"} 跌</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
