"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity } from "lucide-react";
import { useHealth } from "@/lib/hooks";

export function HealthCard() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) return <Skeleton className="h-28" />;
  if (isError || !data) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        </CardHeader>
        <CardContent>
          <Badge variant="destructive">离线</Badge>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        <Activity className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <Badge variant={data.status === "healthy" ? "default" : "secondary"}>
          {data.status === "healthy" ? "正常运行" : "部分降级"}
        </Badge>
        <p className="mt-2 text-xs text-muted-foreground">
          数据库: {data.db.ok ? "正常" : "异常"} · 调度器:{" "}
          {data.scheduler.running ? "运行中" : "已停止"} · v{data.version}
        </p>
      </CardContent>
    </Card>
  );
}
