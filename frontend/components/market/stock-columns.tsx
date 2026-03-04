"use client";

import Link from "next/link";
import { ColumnDef } from "@tanstack/react-table";
import type { StockBasicItem } from "@/lib/types";

function formatAmount(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 100000) return `${(v / 100000).toFixed(2)} 亿`;
  if (v >= 10) return `${v.toFixed(0)} 万`;
  return `${v.toFixed(2)} 万`;
}

function formatMv(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 10000) return `${(v / 10000).toFixed(1)} 亿`;
  return `${v.toFixed(0)} 万`;
}

export const stockColumns: ColumnDef<StockBasicItem>[] = [
  {
    accessorKey: "ts_code",
    header: "代码",
    cell: ({ row }) => (
      <Link
        href={`/market/${row.original.ts_code}`}
        className="text-primary hover:underline font-mono"
      >
        {row.original.ts_code}
      </Link>
    ),
  },
  {
    accessorKey: "name",
    header: "名称",
  },
  {
    accessorKey: "close",
    header: "最新价",
    cell: ({ getValue }) => {
      const v = getValue() as number | null | undefined;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "pct_chg",
    header: "涨跌幅",
    cell: ({ getValue }) => {
      const v = getValue() as number | null | undefined;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return (
        <span className={`font-medium ${color}`}>
          {v >= 0 ? "+" : ""}{v.toFixed(2)}%
        </span>
      );
    },
  },
  {
    accessorKey: "amount",
    header: "成交额",
    cell: ({ getValue }) => {
      const v = getValue() as number | null | undefined;
      return <span className="text-muted-foreground">{formatAmount(v)}</span>;
    },
  },
  {
    accessorKey: "total_mv",
    header: "总市值",
    cell: ({ getValue }) => {
      const v = getValue() as number | null | undefined;
      return <span className="text-muted-foreground">{formatMv(v)}</span>;
    },
  },
  {
    accessorKey: "industry",
    header: "行业",
    cell: ({ getValue }) => (
      <span className="text-muted-foreground">{(getValue() as string) ?? "—"}</span>
    ),
  },
  {
    accessorKey: "market",
    header: "市场",
    cell: ({ getValue }) => (
      <span className="text-xs">{(getValue() as string) ?? "—"}</span>
    ),
  },
];
