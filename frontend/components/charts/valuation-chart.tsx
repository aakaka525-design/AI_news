"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import type { ValuationHistoryItem } from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Metric = "pe_ttm" | "pb" | "ps_ttm" | "dv_ttm";

const METRICS: { key: Metric; label: string; unit: string; color: string }[] = [
  { key: "pe_ttm", label: "PE(TTM)", unit: "", color: "#3b82f6" },
  { key: "pb", label: "PB", unit: "", color: "#f59e0b" },
  { key: "ps_ttm", label: "PS(TTM)", unit: "", color: "#a855f7" },
  { key: "dv_ttm", label: "股息率", unit: "%", color: "#22c55e" },
];

interface ValuationChartProps {
  data: ValuationHistoryItem[];
}

export function ValuationChart({ data }: ValuationChartProps) {
  const [activeMetric, setActiveMetric] = useState<Metric>("pe_ttm");

  if (data.length === 0) {
    return <p className="text-muted-foreground text-sm">暂无估值历史数据</p>;
  }

  const meta = METRICS.find((m) => m.key === activeMetric)!;

  // Sort ascending for chart
  const sorted = [...data].sort((a, b) => a.trade_date.localeCompare(b.trade_date));

  const dates = sorted.map((d) => {
    const s = d.trade_date;
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  });
  const values = sorted.map((d) => d[activeMetric] ?? null);

  const option = {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: Array<{ name: string; value: number | null }>) => {
        const p = params[0];
        return `${p.name}<br/>${meta.label}: ${p.value != null ? p.value.toFixed(2) : "—"}${meta.unit}`;
      },
    },
    grid: { left: "8%", right: "4%", top: "8%", bottom: "12%" },
    xAxis: {
      type: "category" as const,
      data: dates,
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: "value" as const,
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        type: "line" as const,
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: meta.color },
        areaStyle: { color: `${meta.color}15` },
      },
    ],
  };

  return (
    <div>
      <div className="flex gap-1 mb-3">
        {METRICS.map((m) => (
          <Button
            key={m.key}
            variant={activeMetric === m.key ? "default" : "outline"}
            size="sm"
            className="text-xs"
            onClick={() => setActiveMetric(m.key)}
          >
            {m.label}
          </Button>
        ))}
      </div>
      <ReactECharts option={option} style={{ height: 350 }} />
    </div>
  );
}
