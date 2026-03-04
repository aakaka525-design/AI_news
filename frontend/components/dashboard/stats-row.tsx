"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Newspaper,
  Target,
  Rss,
  AlertTriangle,
  Activity,
} from "lucide-react";
import { useHealth, useNews, usePolymarketMarkets, useRss, useAnomalies } from "@/lib/hooks";

interface StatItemProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}

function StatItem({ icon, label, value, sub, color }: StatItemProps) {
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg ${color}`}>{icon}</div>
        <div className="min-w-0">
          <p className="text-xl font-bold tabular-nums">{value}</p>
          <p className="text-xs text-muted-foreground truncate">{label}</p>
          {sub && (
            <p className="text-[10px] text-muted-foreground/70 truncate">
              {sub}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsRow() {
  const health = useHealth();
  const news = useNews(1);
  const polymarket = usePolymarketMarkets(1);
  const rss = useRss(1);
  const anomalies = useAnomalies(undefined, 7, 1);

  const isLoading =
    health.isLoading ||
    news.isLoading ||
    polymarket.isLoading;

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px]" />
        ))}
      </div>
    );
  }

  const isHealthy = health.data?.status === "healthy";

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <StatItem
        icon={<Activity className="h-4 w-4 text-blue-500" />}
        color="bg-blue-500/10"
        label="系统状态"
        value={isHealthy ? "正常" : "降级"}
        sub={`v${health.data?.version ?? "?"}`}
      />
      <StatItem
        icon={<Newspaper className="h-4 w-4 text-violet-500" />}
        color="bg-violet-500/10"
        label="新闻总数"
        value={news.data?.total ?? 0}
      />
      <StatItem
        icon={<Target className="h-4 w-4 text-emerald-500" />}
        color="bg-emerald-500/10"
        label="预测市场"
        value={polymarket.data?.total ?? 0}
      />
      <StatItem
        icon={<Rss className="h-4 w-4 text-amber-500" />}
        color="bg-amber-500/10"
        label="RSS 订阅"
        value={rss.data?.total ?? 0}
      />
      <StatItem
        icon={<AlertTriangle className="h-4 w-4 text-rose-500" />}
        color="bg-rose-500/10"
        label="异常信号"
        value={anomalies.data?.total ?? 0}
        sub="近7天"
      />
    </div>
  );
}
