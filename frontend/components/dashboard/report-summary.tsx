"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileText } from "lucide-react";
import { useReports } from "@/lib/hooks";

export function ReportSummary() {
  const { data, isLoading } = useReports(undefined, 8);

  if (isLoading) return <Skeleton className="h-52" />;

  const items = data?.data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">最新研报</CardTitle>
        <FileText className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无研报数据</p>
        ) : (
          <ScrollArea className="h-44">
            <div className="space-y-2">
              {items.map((item, i) => (
                <div
                  key={`${item.ts_code ?? "unknown"}-${i}`}
                  className="flex items-start justify-between rounded-md border p-2 text-sm"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium">{item.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.institution} · {item.publish_date}
                    </p>
                  </div>
                  {item.rating && (
                    <Badge variant="secondary" className="ml-2 shrink-0">
                      {item.rating}
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
