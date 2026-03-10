"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { StockScoreResponse } from "@/lib/types";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

const BUCKET_LABELS: Record<string, string> = {
  price_trend: "趋势",
  flow: "资金",
  fundamentals: "基本面",
};

function scoreColor(v: number | null | undefined) {
  if (v == null) return "";
  if (v >= 80) return "text-red-600 font-semibold";
  if (v >= 60) return "text-orange-500 font-medium";
  if (v >= 40) return "text-foreground";
  return "text-muted-foreground";
}

function fmtScore(v: number | null | undefined) {
  if (v == null) return "--";
  return v.toFixed(1);
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return "--";
  return `${(v * 100).toFixed(0)}%`;
}

export function ScoreSummaryCard({ data }: { data: StockScoreResponse }) {
  const [expanded, setExpanded] = useState(false);

  if (data.status === "excluded") {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">综合评分</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-muted-foreground">--</span>
            <Badge variant="outline">{data.exclusion_reason || "excluded"}</Badge>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (data.score == null) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">综合评分</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暂无评分数据</p>
        </CardContent>
      </Card>
    );
  }

  const bucketEntries = Object.entries(data.buckets);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">综合评分</CardTitle>
          <div className="flex items-center gap-1.5">
            {data.experimental && (
              <Badge variant="outline" className="text-[10px]">
                实验版
              </Badge>
            )}
            {data.low_confidence && (
              <Badge variant="destructive" className="text-[10px]">
                低置信
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Layer 1: Total score */}
        <div className="flex items-baseline gap-3">
          <span className={`text-3xl font-bold ${scoreColor(data.score)}`}>
            {fmtScore(data.score)}
          </span>
          <span className="text-xs text-muted-foreground">
            {data.trade_date} / {data.score_version}
          </span>
          <span className="text-xs text-muted-foreground">
            覆盖 {fmtPct(data.coverage_ratio)}
          </span>
        </div>

        {/* Layer 2: Bucket summary */}
        <div className="grid grid-cols-3 gap-2">
          {bucketEntries.map(([key, bucket]) => (
            <div key={key} className="rounded-md border p-2 text-center">
              <p className="text-[10px] text-muted-foreground">
                {BUCKET_LABELS[key] || key}
              </p>
              <p className={`text-lg font-semibold ${scoreColor(bucket.score)}`}>
                {fmtScore(bucket.score)}
              </p>
              <p className="text-[10px] text-muted-foreground">
                权重 {fmtPct(bucket.weight_effective)}
              </p>
            </div>
          ))}
        </div>

        {/* Layer 3: Factor detail (collapsible) */}
        {data.factors.length > 0 && (
          <div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex w-full items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <span>因子明细 ({data.factors.length})</span>
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
            {expanded && (
              <div className="mt-2 space-y-1">
                {data.factors.map((f) => (
                  <div
                    key={f.factor_key}
                    className="flex items-center justify-between rounded-md border px-2 py-1 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{f.factor_key}</span>
                      {!f.available && (
                        <Badge variant="outline" className="text-[9px]">
                          缺失
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-muted-foreground">
                      <span>原始 {f.raw_value?.toFixed(2) ?? "--"}</span>
                      <span>归一 {f.normalized_value?.toFixed(2) ?? "--"}</span>
                      <span>权重 {fmtPct(f.weight_effective)}</span>
                      {f.staleness_trading_days > 0 && (
                        <span className="text-orange-500">
                          滞后{f.staleness_trading_days}日
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
