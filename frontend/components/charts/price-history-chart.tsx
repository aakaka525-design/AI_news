"use client";

import ReactECharts from "echarts-for-react";
import type { PolymarketSnapshot } from "@/lib/types";
import { OUTCOME_ZH } from "@/lib/polymarket-utils";

interface PriceHistoryChartProps {
  snapshots: PolymarketSnapshot[];
  outcomes?: string[] | null;
}

const COLORS = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6"];

export function PriceHistoryChart({ snapshots, outcomes }: PriceHistoryChartProps) {
  if (!snapshots || snapshots.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        暂无价格历史数据
      </p>
    );
  }

  // snapshots arrive newest-first; reverse for chronological order
  const sorted = [...snapshots].reverse();
  const times = sorted.map((s) =>
    s.snapshot_time
      ? new Date(s.snapshot_time).toLocaleString("zh-CN", {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "",
  );

  // Determine number of outcome series
  const samplePrices = sorted.find((s) => s.outcome_prices)?.outcome_prices ?? [];
  const seriesCount = samplePrices.length;

  const series = Array.from({ length: seriesCount }, (_, i) => ({
    name: OUTCOME_ZH[outcomes?.[i] ?? ""] ?? outcomes?.[i] ?? `结果 ${i + 1}`,
    type: "line" as const,
    smooth: true,
    symbol: "none",
    lineStyle: { width: 2 },
    data: sorted.map((s) => {
      const price = s.outcome_prices?.[i];
      return price != null ? +(price * 100).toFixed(1) : null;
    }),
    color: COLORS[i % COLORS.length],
  }));

  const option = {
    tooltip: {
      trigger: "axis" as const,
      valueFormatter: (v: number) => `${v}%`,
    },
    legend: {
      data: series.map((s) => s.name),
      bottom: 0,
    },
    grid: { left: 40, right: 16, top: 16, bottom: 36 },
    xAxis: {
      type: "category" as const,
      data: times,
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: "value" as const,
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}%" },
    },
    series,
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
