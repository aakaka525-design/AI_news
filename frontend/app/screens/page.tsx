"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useScreenRps, useScreenPotential } from "@/lib/hooks";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { DataTable, type ColumnDef } from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import type { ScreenRpsItem, ScreenPotentialItem } from "@/lib/types";
import { Clock, CalendarDays } from "lucide-react";

/* ---------- helpers ---------- */

function fmtNum(v: number | null | undefined, digits = 1) {
  if (v == null) return "—";
  return v.toFixed(digits);
}

function rpsColor(v: number | null | undefined) {
  if (v == null) return "";
  if (v >= 90) return "text-red-600 font-semibold";
  if (v >= 80) return "text-orange-500 font-medium";
  if (v >= 50) return "text-foreground";
  return "text-muted-foreground";
}

function scoreColor(v: number | null | undefined) {
  if (v == null) return "";
  if (v >= 80) return "text-red-600 font-semibold";
  if (v >= 60) return "text-orange-500 font-medium";
  if (v >= 40) return "text-foreground";
  return "text-muted-foreground";
}

/* ---------- column definitions ---------- */

const rpsColumns: ColumnDef<ScreenRpsItem, unknown>[] = [
  {
    accessorKey: "rank",
    header: "#",
    cell: ({ getValue }) => (
      <span className="text-muted-foreground">{getValue<number | null>() ?? "—"}</span>
    ),
    enableSorting: true,
  },
  {
    accessorKey: "ts_code",
    header: "代码",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue<string>()}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "stock_name",
    header: "名称",
    cell: ({ getValue }) => getValue<string | null>() ?? "—",
    enableSorting: false,
  },
  {
    accessorKey: "rps_10",
    header: "RPS10",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={rpsColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "rps_20",
    header: "RPS20",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={rpsColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "rps_50",
    header: "RPS50",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={rpsColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "rps_120",
    header: "RPS120",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={rpsColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
];

const potentialColumns: ColumnDef<ScreenPotentialItem, unknown>[] = [
  {
    accessorKey: "rank",
    header: "#",
    cell: ({ getValue }) => (
      <span className="text-muted-foreground">{getValue<number | null>() ?? "—"}</span>
    ),
    enableSorting: true,
  },
  {
    accessorKey: "ts_code",
    header: "代码",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue<string>()}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "stock_name",
    header: "名称",
    cell: ({ getValue }) => getValue<string | null>() ?? "—",
    enableSorting: false,
  },
  {
    accessorKey: "total_score",
    header: "综合评分",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={scoreColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "capital_score",
    header: "资金",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={scoreColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "trading_score",
    header: "交易",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={scoreColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "fundamental_score",
    header: "基本面",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={scoreColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "technical_score",
    header: "技术面",
    cell: ({ getValue }) => {
      const v = getValue<number | null>();
      return <span className={scoreColor(v)}>{fmtNum(v)}</span>;
    },
    enableSorting: true,
  },
  {
    accessorKey: "signals",
    header: "信号",
    cell: ({ getValue }) => {
      const v = getValue<string | null>();
      if (!v) return "—";
      const tags = v.split(",").map((s) => s.trim()).filter(Boolean);
      return (
        <div className="flex flex-wrap gap-1">
          {tags.slice(0, 3).map((tag) => (
            <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">
              {tag}
            </Badge>
          ))}
          {tags.length > 3 && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              +{tags.length - 3}
            </Badge>
          )}
        </div>
      );
    },
    enableSorting: false,
  },
];

/* ---------- freshness banner ---------- */

function FreshnessBanner({
  snapshotDate,
  sourceTradeDate,
  generatedAt,
  total,
}: {
  snapshotDate: string;
  sourceTradeDate: string;
  generatedAt: string;
  total: number;
}) {
  return (
    <Card>
      <CardContent className="py-3 px-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <CalendarDays className="h-4 w-4" />
            数据日期:
            <span className="font-medium text-foreground">{sourceTradeDate}</span>
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-4 w-4" />
            生成时间:
            <span className="font-medium text-foreground">
              {generatedAt.replace("T", " ").slice(0, 19)}
            </span>
          </span>
          <span className="text-muted-foreground">
            快照日期: <span className="font-medium text-foreground">{snapshotDate}</span>
          </span>
          <span className="text-muted-foreground">
            共 <span className="font-medium text-foreground">{total}</span> 条
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- loading skeleton ---------- */

function TableSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-10 w-full" />
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

/* ---------- empty state ---------- */

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
      <svg
        className="h-12 w-12 mb-4 opacity-30"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z"
        />
      </svg>
      <p className="text-sm">{message}</p>
    </div>
  );
}

/* ---------- main page ---------- */

export default function ScreensPage() {
  const router = useRouter();

  const { data: rpsData, isLoading: rpsLoading, error: rpsError } = useScreenRps();
  const { data: potentialData, isLoading: potentialLoading, error: potentialError } = useScreenPotential();

  const rpsItems = useMemo(() => rpsData?.items ?? [], [rpsData]);
  const potentialItems = useMemo(() => potentialData?.items ?? [], [potentialData]);

  function navigateToStock(tsCode: string) {
    router.push(`/market/${tsCode}`);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">智能筛选</h1>

      <Tabs defaultValue="rps">
        <TabsList>
          <TabsTrigger value="rps">RPS 强势股</TabsTrigger>
          <TabsTrigger value="potential">潜力筛选</TabsTrigger>
        </TabsList>

        {/* ===== RPS Tab ===== */}
        <TabsContent value="rps" className="space-y-4">
          {rpsLoading ? (
            <TableSkeleton />
          ) : rpsError ? (
            <EmptyState message={`加载失败: ${(rpsError as Error).message}`} />
          ) : rpsItems.length === 0 ? (
            <EmptyState message="暂无 RPS 筛选数据" />
          ) : (
            <>
              {rpsData && (
                <FreshnessBanner
                  snapshotDate={rpsData.snapshot_date}
                  sourceTradeDate={rpsData.source_trade_date}
                  generatedAt={rpsData.generated_at}
                  total={rpsData.total}
                />
              )}
              <DataTable
                columns={rpsColumns}
                data={rpsItems}
                onRowClick={(row) => navigateToStock(row.ts_code)}
              />
            </>
          )}
        </TabsContent>

        {/* ===== Potential Tab ===== */}
        <TabsContent value="potential" className="space-y-4">
          {potentialLoading ? (
            <TableSkeleton />
          ) : potentialError ? (
            <EmptyState message={`加载失败: ${(potentialError as Error).message}`} />
          ) : potentialItems.length === 0 ? (
            <EmptyState message="暂无潜力筛选数据" />
          ) : (
            <>
              {potentialData && (
                <FreshnessBanner
                  snapshotDate={potentialData.snapshot_date}
                  sourceTradeDate={potentialData.source_trade_date}
                  generatedAt={potentialData.generated_at}
                  total={potentialData.total}
                />
              )}
              <DataTable
                columns={potentialColumns}
                data={potentialItems}
                onRowClick={(row) => navigateToStock(row.ts_code)}
              />
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
