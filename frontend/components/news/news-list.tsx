"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { useNews, useNewsFacts } from "@/lib/hooks";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

export function NewsList() {
  const { data, isLoading } = useNews(100);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const facts = useNewsFacts(selectedId);

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

  const selectedItem = items.find((i) => i.id === selectedId);

  return (
    <>
      <ScrollArea className="h-[calc(100vh-14rem)]">
        <div className="space-y-3">
          {items.map((item) => (
            <Card
              key={item.id}
              className="cursor-pointer transition-colors hover:bg-accent/50"
              onClick={() => setSelectedId(item.id)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium leading-tight">
                      {item.title}
                    </CardTitle>
                    {item.source && (
                      <Badge
                        variant={item.source === "polymarket" ? "default" : "secondary"}
                        className={`shrink-0 text-xs ${item.source === "polymarket" ? "bg-blue-500 hover:bg-blue-600" : ""}`}
                      >
                        {item.source === "polymarket" ? "Polymarket" : item.source}
                      </Badge>
                    )}
                  </div>
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

      <Sheet open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle className="text-base leading-tight">
              {selectedItem?.title ?? "新闻详情"}
            </SheetTitle>
            <SheetDescription>
              {selectedItem?.received_at
                ? formatDistanceToNow(new Date(selectedItem.received_at), {
                    addSuffix: true,
                    locale: zhCN,
                  })
                : ""}
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-4">
            {facts.isLoading ? (
              <Skeleton className="h-40" />
            ) : facts.data ? (
              <>
                <div>
                  <h3 className="text-sm font-medium mb-1">摘要</h3>
                  <p className="text-sm text-muted-foreground">{facts.data.summary}</p>
                </div>

                {facts.data.facts.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium mb-1">事实清单</h3>
                    <ul className="space-y-1">
                      {facts.data.facts.map((f, i) => (
                        <li key={i} className="text-sm text-muted-foreground flex gap-2">
                          <Badge variant="outline" className="shrink-0 text-xs">{f.category}</Badge>
                          <span>{f.fact}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {facts.data.hotspots.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium mb-1">热点关键词</h3>
                    <div className="flex flex-wrap gap-1">
                      {facts.data.hotspots.map((h) => (
                        <Badge key={h} variant="default" className="text-xs">{h}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {facts.data.keywords.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium mb-1">关键词</h3>
                    <div className="flex flex-wrap gap-1">
                      {facts.data.keywords.map((k) => (
                        <Badge key={k} variant="secondary" className="text-xs">{k}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {selectedItem?.content ?? "该新闻尚未进行数据清洗"}
              </p>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
