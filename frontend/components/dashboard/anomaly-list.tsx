"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle } from "lucide-react";
import { useAnomalies } from "@/lib/hooks";

export function AnomalyList() {
  const { data, isLoading } = useAnomalies(undefined, 3, 10);

  if (isLoading) return <Skeleton className="h-52" />;

  const items = data?.data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">最新异常信号</CardTitle>
        <AlertTriangle className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">近期无异常信号</p>
        ) : (
          <ScrollArea className="h-44">
            <div className="space-y-2">
              {items.map((item, i) => (
                <div
                  key={`${item.stock_code}-${item.signal_type}-${i}`}
                  className="flex items-center justify-between rounded-md border p-2 text-sm"
                >
                  <div>
                    <span className="font-medium">{item.stock_code}</span>
                    {item.stock_name && (
                      <span className="ml-1 text-muted-foreground">
                        {item.stock_name}
                      </span>
                    )}
                  </div>
                  <Badge variant="outline">{item.signal_type}</Badge>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
