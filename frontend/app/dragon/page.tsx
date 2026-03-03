"use client";

import { useState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { DataTable, ColumnDef } from "@/components/ui/data-table";
import { useDragonTiger } from "@/lib/hooks";
import type { DragonTigerItem } from "@/lib/types";

const columns: ColumnDef<DragonTigerItem>[] = [
  {
    accessorKey: "ts_code",
    header: "代码",
    cell: ({ getValue }) => (
      <Link
        href={`/market/${getValue() as string}`}
        className="text-primary hover:underline font-mono"
      >
        {getValue() as string}
      </Link>
    ),
  },
  {
    accessorKey: "name",
    header: "名称",
  },
  {
    accessorKey: "pct_chg",
    header: "涨跌幅",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return <span className={color}>{v.toFixed(2)}%</span>;
    },
  },
  {
    accessorKey: "net_amount",
    header: "净买入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return <span className={color}>{v.toFixed(2)}</span>;
    },
  },
  {
    accessorKey: "l_buy",
    header: "买入额(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "l_sell",
    header: "卖出额(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "reason",
    header: "上榜原因",
    cell: ({ getValue }) => (
      <span className="text-xs max-w-[200px] truncate block">
        {(getValue() as string) ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "inst_buy",
    header: "机构买入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "inst_sell",
    header: "机构卖出(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
];

export default function DragonPage() {
  const [tradeDate, setTradeDate] = useState("");

  const { data, isLoading } = useDragonTiger(tradeDate || undefined, undefined, 50);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">龙虎榜</h1>

      <div className="flex items-center gap-3">
        <Input
          type="text"
          placeholder="交易日期 (YYYYMMDD)，留空取最新"
          value={tradeDate}
          onChange={(e) => setTradeDate(e.target.value)}
          className="max-w-xs"
        />
      </div>

      <DataTable columns={columns} data={data?.data ?? []} isLoading={isLoading} />
    </div>
  );
}
