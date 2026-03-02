"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useHotspots } from "@/lib/hooks";

export function HotspotCloud() {
  const { data, isLoading } = useHotspots();

  if (isLoading) return <Skeleton className="h-40" />;

  const items = data?.data ?? [];
  const maxCount = Math.max(...items.map((i) => i.count), 1);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">热点关键词</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {items.slice(0, 20).map((item) => {
            const scale = 0.75 + (item.count / maxCount) * 0.5;
            return (
              <Badge
                key={item.keyword}
                variant="outline"
                style={{ fontSize: `${scale}rem` }}
              >
                {item.keyword}
                <span className="ml-1 text-muted-foreground">{item.count}</span>
              </Badge>
            );
          })}
        </div>
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">暂无热点数据</p>
        )}
      </CardContent>
    </Card>
  );
}
