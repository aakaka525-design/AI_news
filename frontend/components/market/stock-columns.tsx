"use client";

import Link from "next/link";
import { ColumnDef } from "@tanstack/react-table";
import type { StockBasicItem } from "@/lib/types";

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
  {
    accessorKey: "area",
    header: "地区",
    cell: ({ getValue }) => (
      <span className="text-muted-foreground text-xs">{(getValue() as string) ?? "—"}</span>
    ),
  },
  {
    accessorKey: "list_date",
    header: "上市日期",
    cell: ({ getValue }) => {
      const v = getValue() as string | undefined;
      if (!v) return "—";
      return `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6, 8)}`;
    },
  },
];
