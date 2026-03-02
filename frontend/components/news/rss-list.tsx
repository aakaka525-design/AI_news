"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRss } from "@/lib/hooks";

function sentimentColor(label?: string): "default" | "secondary" | "destructive" {
  if (label === "positive") return "default";
  if (label === "negative") return "destructive";
  return "secondary";
}

export function RssList() {
  const { data, isLoading } = useRss(100);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }

  const items = data?.data ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无 RSS 数据</p>;
  }

  return (
    <ScrollArea className="h-[calc(100vh-14rem)]">
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-sm font-medium leading-tight">
                  {item.link ? (
                    <a
                      href={item.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </CardTitle>
                {item.sentiment_label && (
                  <Badge
                    variant={sentimentColor(item.sentiment_label)}
                    className="shrink-0 text-xs"
                  >
                    {item.sentiment_label}
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {item.summary && (
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {item.summary}
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                {item.source} · {item.published}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  );
}
