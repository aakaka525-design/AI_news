"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSentimentStats } from "@/lib/hooks";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function SentimentPie() {
  const { data, isLoading } = useSentimentStats();

  if (isLoading) return <Skeleton className="h-52" />;

  const total = data?.analyzed_count ?? 0;
  const positive = data?.distribution?.positive ?? 0;
  const neutral = data?.distribution?.neutral ?? 0;
  const negative = data?.distribution?.negative ?? 0;

  if (!data || total === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">市场情绪</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暂无情感分析数据</p>
        </CardContent>
      </Card>
    );
  }

  const option = {
    tooltip: { trigger: "item" as const },
    series: [
      {
        type: "pie" as const,
        radius: ["40%", "70%"],
        data: [
          { value: positive, name: "积极", itemStyle: { color: "#22c55e" } },
          { value: neutral, name: "中性", itemStyle: { color: "#94a3b8" } },
          { value: negative, name: "消极", itemStyle: { color: "#ef4444" } },
        ],
        label: { formatter: "{b}: {d}%" },
      },
    ],
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">市场情绪</CardTitle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} style={{ height: 200 }} />
      </CardContent>
    </Card>
  );
}
