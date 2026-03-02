"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useSchedulerJobs, useFreshness, useHealth } from "@/lib/hooks";

export default function SettingsPage() {
  const health = useHealth();
  const scheduler = useSchedulerJobs();
  const freshness = useFreshness();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">系统设置</h1>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">系统状态</CardTitle>
        </CardHeader>
        <CardContent>
          {health.isLoading ? (
            <Skeleton className="h-16" />
          ) : health.data ? (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span>状态:</span>
                <Badge
                  variant={
                    health.data.status === "healthy" ? "default" : "secondary"
                  }
                >
                  {health.data.status}
                </Badge>
              </div>
              <p>数据库: {health.data.db.ok ? "正常" : "异常"}</p>
              <p>
                调度器: {health.data.scheduler.running ? "运行中" : "已停止"}
              </p>
              <p>版本: {health.data.version}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">无法连接后端</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">调度任务</CardTitle>
        </CardHeader>
        <CardContent>
          {scheduler.isLoading ? (
            <Skeleton className="h-32" />
          ) : (scheduler.data?.jobs ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">无调度任务</p>
          ) : (
            <div className="space-y-2">
              {scheduler.data!.jobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between rounded-md border p-3 text-sm"
                >
                  <div>
                    <p className="font-medium">{job.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {job.description}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      上次运行: {job.last_run ?? "无"} · 执行次数: {job.run_count}
                    </p>
                  </div>
                  <Badge variant={job.enabled ? "default" : "secondary"}>
                    {job.enabled ? "启用" : "禁用"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">数据新鲜度</CardTitle>
        </CardHeader>
        <CardContent>
          {freshness.isLoading ? (
            <Skeleton className="h-32" />
          ) : !(freshness.data?.tables ?? []).length ? (
            <p className="text-sm text-muted-foreground">无数据</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2">数据表</th>
                    <th className="pb-2">最新日期</th>
                    <th className="pb-2">行数</th>
                  </tr>
                </thead>
                <tbody>
                  {freshness.data!.tables.map((t) => (
                    <tr key={t.table} className="border-b">
                      <td className="py-2 font-mono text-xs">{t.table}</td>
                      <td className="py-2">{t.latest_date ?? "-"}</td>
                      <td className="py-2">{t.row_count ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
