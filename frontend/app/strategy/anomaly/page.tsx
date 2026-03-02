"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAnomalies, useAnomalyStats } from "@/lib/hooks";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function StatsChart() {
  const { data, isLoading } = useAnomalyStats();

  if (isLoading) return <Skeleton className="h-52" />;
  if (!data || Object.keys(data).length === 0) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-sm text-muted-foreground">暂无异常统计数据</p>
        </CardContent>
      </Card>
    );
  }

  const entries = Object.entries(data).filter(([k]) => k !== "error");
  const option = {
    tooltip: { trigger: "axis" as const },
    xAxis: {
      type: "category" as const,
      data: entries.map(([k]) => k),
      axisLabel: { rotate: 30, fontSize: 11 },
    },
    yAxis: { type: "value" as const },
    series: [
      {
        type: "bar" as const,
        data: entries.map(([, v]) => v),
        itemStyle: { color: "#6366f1" },
      },
    ],
    grid: { left: 40, right: 20, bottom: 60, top: 20 },
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">信号分布</CardTitle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} style={{ height: 220 }} />
      </CardContent>
    </Card>
  );
}

export default function AnomalyPage() {
  const { data, isLoading } = useAnomalies(undefined, 7, 100);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">异常信号监控</h1>

      <StatsChart />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            最近 7 天异常信号（{data?.total ?? 0} 条）
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : (data?.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">近期无异常信号</p>
          ) : (
            <ScrollArea className="h-[calc(100vh-26rem)]">
              <div className="space-y-2">
                {(data?.data ?? []).map((item, i) => (
                  <div
                    key={`${item.stock_code}-${item.signal_type}-${i}`}
                    className="flex items-center justify-between rounded-md border p-3 text-sm"
                  >
                    <div>
                      <span className="font-medium">{item.stock_code}</span>
                      {item.stock_name && (
                        <span className="ml-2 text-muted-foreground">
                          {item.stock_name}
                        </span>
                      )}
                      {item.description && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {item.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{item.signal_type}</Badge>
                      {item.date && (
                        <span className="text-xs text-muted-foreground">
                          {item.date}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
