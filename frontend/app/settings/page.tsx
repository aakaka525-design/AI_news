"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSchedulerJobs, useFreshness, useHealth, useJobAction, useManualActions, useIntegrityCheck } from "@/lib/hooks";

export default function SettingsPage() {
  const health = useHealth();
  const scheduler = useSchedulerJobs();
  const freshness = useFreshness();
  const { trigger, pause, resume } = useJobAction();
  const { fetchRss, fetchResearch, detectAnomalies, analyze } = useManualActions();
  const integrityCheck = useIntegrityCheck();
  const [actionResults, setActionResults] = useState<Record<string, string>>({});
  const [analyzeDate, setAnalyzeDate] = useState<string>(
    () => new Date().toISOString().slice(0, 10),
  );

  const handleAction = async (key: string, fn: () => Promise<unknown>) => {
    setActionResults((prev) => ({ ...prev, [key]: "执行中..." }));
    try {
      const result = await fn();
      const msg = typeof result === "object" && result !== null
        ? JSON.stringify(result, null, 0).slice(0, 120)
        : "完成";
      setActionResults((prev) => ({ ...prev, [key]: msg }));
    } catch (e) {
      setActionResults((prev) => ({ ...prev, [key]: `失败: ${e instanceof Error ? e.message : "未知错误"}` }));
    }
  };

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
          <CardTitle className="text-sm font-medium">手动操作</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-4 max-w-xs">
            <p className="mb-1 text-xs text-muted-foreground">AI 分析日期</p>
            <Input
              type="date"
              value={analyzeDate}
              onChange={(e) => setAnalyzeDate(e.target.value)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { key: "rss", label: "抓取 RSS", desc: "手动抓取 RSS 订阅源", fn: () => fetchRss.mutateAsync(undefined) },
              { key: "research", label: "抓取研报", desc: "手动抓取研究报告", fn: () => fetchResearch.mutateAsync(undefined) },
              { key: "anomaly", label: "异常检测", desc: "运行异常信号检测", fn: () => detectAnomalies.mutateAsync(undefined) },
              { key: "analyze", label: "AI 分析", desc: "运行 AI 新闻分析", fn: () => analyze.mutateAsync(analyzeDate) },
            ].map((action) => (
              <div key={action.key} className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <p className="text-sm font-medium">{action.label}</p>
                  <p className="text-xs text-muted-foreground">{action.desc}</p>
                  {actionResults[action.key] && (
                    <p className="mt-1 text-xs text-muted-foreground truncate max-w-[200px]">
                      {actionResults[action.key]}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={actionResults[action.key] === "执行中..."}
                  onClick={() => handleAction(action.key, action.fn)}
                >
                  执行
                </Button>
              </div>
            ))}
          </div>
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
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={trigger.isPending}
                      onClick={() => trigger.mutate(job.id)}
                    >
                      执行
                    </Button>
                    {job.enabled ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={pause.isPending}
                        onClick={() => pause.mutate(job.id)}
                      >
                        暂停
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="default"
                        disabled={resume.isPending}
                        onClick={() => resume.mutate(job.id)}
                      >
                        恢复
                      </Button>
                    )}
                    <Badge variant={job.enabled ? "default" : "secondary"}>
                      {job.enabled ? "启用" : "禁用"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">数据完整性检查</CardTitle>
            <Button
              size="sm"
              variant="outline"
              disabled={integrityCheck.isFetching}
              onClick={() => integrityCheck.refetch()}
            >
              {integrityCheck.isFetching ? "检查中..." : "运行检查"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {integrityCheck.isFetching ? (
            <Skeleton className="h-32" />
          ) : !integrityCheck.data ? (
            <p className="text-sm text-muted-foreground">点击「运行检查」开始数据完整性检查</p>
          ) : (
            <div className="space-y-3">
              <div className="flex gap-4 text-sm">
                <span>陈旧表: <Badge variant={integrityCheck.data.summary.stale_tables > 0 ? "destructive" : "default"}>{integrityCheck.data.summary.stale_tables}</Badge></span>
                <span>空表: <Badge variant={integrityCheck.data.summary.empty_tables > 0 ? "destructive" : "default"}>{integrityCheck.data.summary.empty_tables}</Badge></span>
                <span>总问题: <Badge variant={integrityCheck.data.summary.total_issues > 0 ? "destructive" : "default"}>{integrityCheck.data.summary.total_issues}</Badge></span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2">数据表</th>
                      <th className="pb-2">状态</th>
                      <th className="pb-2">最新日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {integrityCheck.data.checks.freshness.map((item) => (
                      <tr key={item.name} className="border-b">
                        <td className="py-2 font-mono text-xs">{item.name}</td>
                        <td className="py-2">
                          <Badge variant={item.status === "ok" ? "default" : "destructive"}>
                            {item.status}
                          </Badge>
                        </td>
                        <td className="py-2 text-xs">{item.latest_date ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
                      <td className="py-2">{t.record_count ?? t.row_count ?? "-"}</td>
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
