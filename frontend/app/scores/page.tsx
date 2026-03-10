"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useScoresRanking, useStockIndustries } from "@/lib/hooks";
import { ScoreRankingTable } from "@/components/scores/score-ranking-table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CalendarDays, FlaskConical } from "lucide-react";

const SORT_OPTIONS = [
  { value: "score", label: "综合评分" },
  { value: "price_trend", label: "趋势" },
  { value: "flow", label: "资金" },
  { value: "fundamentals", label: "基本面" },
] as const;

const PAGE_SIZE = 50;

export default function ScoresPage() {
  const router = useRouter();
  const [page, setPage] = useState(0);
  const [sortBy, setSortBy] = useState("score");
  const [industry, setIndustry] = useState<string | undefined>(undefined);
  const [includeLowConfidence, setIncludeLowConfidence] = useState(false);

  const { data, isLoading } = useScoresRanking(
    PAGE_SIZE,
    page * PAGE_SIZE,
    sortBy,
    industry,
    includeLowConfidence,
  );
  const { data: industries } = useStockIndustries();

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">综合评分排行</h1>

      {/* Context summary banner */}
      {data && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4">
            <div className="flex items-center gap-1.5 text-sm">
              <CalendarDays className="h-4 w-4 text-muted-foreground" />
              <span>{data.trade_date}</span>
            </div>
            <div className="flex items-center gap-1.5 text-sm">
              <FlaskConical className="h-4 w-4 text-muted-foreground" />
              <span>{data.score_version}</span>
              <Badge variant="outline" className="text-[10px]">
                实验版
              </Badge>
            </div>
            <span className="text-sm text-muted-foreground">
              共 {data.total} 只
            </span>
            <span className="text-sm text-muted-foreground">
              {includeLowConfidence ? "含低置信" : "已过滤低置信"}
            </span>
          </CardContent>
        </Card>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Sort */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">排序：</span>
          <div className="flex gap-1">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setSortBy(opt.value); setPage(0); }}
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  sortBy === opt.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:text-foreground"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Industry filter */}
        {industries && industries.length > 0 && (
          <select
            value={industry ?? ""}
            onChange={(e) => { setIndustry(e.target.value || undefined); setPage(0); }}
            className="rounded-md border bg-background px-2 py-1 text-xs"
          >
            <option value="">全部行业</option>
            {industries.map((ind) => (
              <option key={ind} value={ind}>
                {ind}
              </option>
            ))}
          </select>
        )}

        {/* Low confidence toggle */}
        <label className="flex items-center gap-1.5 text-xs cursor-pointer">
          <input
            type="checkbox"
            checked={includeLowConfidence}
            onChange={(e) => { setIncludeLowConfidence(e.target.checked); setPage(0); }}
            className="rounded"
          />
          <span className="text-muted-foreground">显示低置信</span>
        </label>
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton />
      ) : data ? (
        <>
          <ScoreRankingTable
            items={data.items}
            onRowClick={(tsCode) => router.push(`/market/${tsCode}`)}
          />
          {/* Pagination */}
          {data.total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-4 pt-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded-md border px-3 py-1 text-xs disabled:opacity-40"
              >
                上一页
              </button>
              <span className="text-xs text-muted-foreground">
                第 {page + 1} / {Math.ceil(data.total / PAGE_SIZE)} 页
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * PAGE_SIZE >= data.total}
                className="rounded-md border px-3 py-1 text-xs disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          )}
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
      <svg className="h-10 w-10 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p className="text-sm">暂无评分数据</p>
      <p className="text-xs mt-1">综合评分任务可能尚未执行</p>
    </div>
  );
}
