"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { IndexItem } from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

interface MarketBreadthProps {
  indices: IndexItem[];
}

export function MarketBreadth({ indices }: MarketBreadthProps) {
  // Aggregate up/down counts from all indices (take the max pair, typically from 上证)
  let totalUp = 0;
  let totalDown = 0;
  for (const idx of indices) {
    if ((idx.up_count ?? 0) > totalUp) {
      totalUp = idx.up_count ?? 0;
      totalDown = idx.down_count ?? 0;
    }
  }

  if (totalUp === 0 && totalDown === 0) return null;

  const total = totalUp + totalDown;

  const option = {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
    },
    grid: { left: "3%", right: "3%", top: "10%", bottom: "10%", containLabel: true },
    xAxis: {
      type: "value" as const,
      max: total,
      show: false,
    },
    yAxis: {
      type: "category" as const,
      data: ["涨跌分布"],
      show: false,
    },
    series: [
      {
        name: "上涨",
        type: "bar" as const,
        stack: "total",
        data: [totalUp],
        itemStyle: { color: "#ef4444" },
        barWidth: 24,
        label: {
          show: true,
          position: "insideLeft" as const,
          formatter: `上涨 ${totalUp}`,
          fontSize: 12,
          color: "#fff",
        },
      },
      {
        name: "下跌",
        type: "bar" as const,
        stack: "total",
        data: [totalDown],
        itemStyle: { color: "#22c55e" },
        barWidth: 24,
        label: {
          show: true,
          position: "insideRight" as const,
          formatter: `下跌 ${totalDown}`,
          fontSize: 12,
          color: "#fff",
        },
      },
    ],
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">涨跌分布</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ReactECharts option={option} style={{ height: 60 }} />
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span className="text-red-500">上涨 {totalUp} 家 ({total ? ((totalUp / total) * 100).toFixed(1) : 0}%)</span>
          <span className="text-green-500">下跌 {totalDown} 家 ({total ? ((totalDown / total) * 100).toFixed(1) : 0}%)</span>
        </div>
      </CardContent>
    </Card>
  );
}
