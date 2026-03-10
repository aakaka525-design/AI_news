"use client";

import { Badge } from "@/components/ui/badge";
import type { ScoreRankingItem } from "@/lib/types";
import { type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";

function fmtScore(v: number | null | undefined, digits = 1) {
  if (v == null) return "--";
  return v.toFixed(digits);
}

function scoreColor(v: number | null | undefined) {
  if (v == null) return "";
  if (v >= 80) return "text-red-600 font-semibold";
  if (v >= 60) return "text-orange-500 font-medium";
  if (v >= 40) return "text-foreground";
  return "text-muted-foreground";
}

const columns: ColumnDef<ScoreRankingItem>[] = [
  {
    accessorKey: "rank",
    header: "#",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.index + 1}</span>
    ),
    size: 40,
  },
  {
    accessorKey: "ts_code",
    header: "代码",
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.ts_code}</span>
    ),
  },
  {
    accessorKey: "name",
    header: "名称",
    cell: ({ row }) => (
      <span className="truncate">{row.original.name ?? "--"}</span>
    ),
  },
  {
    accessorKey: "industry",
    header: "行业",
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground truncate">
        {row.original.industry ?? "--"}
      </span>
    ),
  },
  {
    accessorKey: "score",
    header: "综合评分",
    cell: ({ row }) => (
      <span className={scoreColor(row.original.score)}>
        {fmtScore(row.original.score)}
      </span>
    ),
  },
  {
    accessorKey: "price_trend_score",
    header: "趋势",
    cell: ({ row }) => (
      <span className={scoreColor(row.original.price_trend_score)}>
        {fmtScore(row.original.price_trend_score)}
      </span>
    ),
  },
  {
    accessorKey: "flow_score",
    header: "资金",
    cell: ({ row }) => (
      <span className={scoreColor(row.original.flow_score)}>
        {fmtScore(row.original.flow_score)}
      </span>
    ),
  },
  {
    accessorKey: "fundamentals_score",
    header: "基本面",
    cell: ({ row }) => (
      <span className={scoreColor(row.original.fundamentals_score)}>
        {fmtScore(row.original.fundamentals_score)}
      </span>
    ),
  },
  {
    accessorKey: "coverage_ratio",
    header: "覆盖",
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        {(row.original.coverage_ratio * 100).toFixed(0)}%
      </span>
    ),
  },
  {
    accessorKey: "low_confidence",
    header: "",
    cell: ({ row }) =>
      row.original.low_confidence ? (
        <Badge variant="outline" className="text-[9px]">
          低置信
        </Badge>
      ) : null,
    size: 60,
  },
];

interface ScoreRankingTableProps {
  items: ScoreRankingItem[];
  onRowClick?: (tsCode: string) => void;
}

export function ScoreRankingTable({ items, onRowClick }: ScoreRankingTableProps) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <svg className="h-10 w-10 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-sm">暂无评分数据</p>
      </div>
    );
  }

  return (
    <DataTable
      columns={columns}
      data={items}
      onRowClick={onRowClick ? (row) => onRowClick(row.ts_code) : undefined}
    />
  );
}
