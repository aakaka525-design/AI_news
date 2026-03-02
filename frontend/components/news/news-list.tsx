"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useNews } from "@/lib/hooks";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

export function NewsList() {
  const { data, isLoading } = useNews(100);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }

  const items = data?.data ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无新闻数据</p>;
  }

  return (
    <ScrollArea className="h-[calc(100vh-14rem)]">
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-sm font-medium leading-tight">
                  {item.title}
                </CardTitle>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {item.received_at
                    ? formatDistanceToNow(new Date(item.received_at), {
                        addSuffix: true,
                        locale: zhCN,
                      })
                    : ""}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {item.cleaned_data?.summary ? (
                <p className="text-sm text-muted-foreground">
                  {item.cleaned_data.summary}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {item.content}
                </p>
              )}
              {item.cleaned_data?.hotspots &&
                item.cleaned_data.hotspots.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {item.cleaned_data.hotspots.map((h) => (
                      <Badge key={h} variant="outline" className="text-xs">
                        {h}
                      </Badge>
                    ))}
                  </div>
                )}
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  );
}
