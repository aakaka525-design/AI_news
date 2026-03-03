"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, ColumnDef } from "@/components/ui/data-table";
import { useMoneyFlow } from "@/lib/hooks";
import type { MoneyFlowItem } from "@/lib/types";
import Link from "next/link";

const mainColumns: ColumnDef<MoneyFlowItem>[] = [
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
    accessorKey: "net_mf_amount",
    header: "主力净流入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return <span className={color}>{v.toFixed(2)}</span>;
    },
  },
  {
    accessorKey: "net_mf_rate",
    header: "净流入占比(%)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? `${v.toFixed(2)}%` : "—";
    },
  },
  {
    accessorKey: "buy_elg_amount",
    header: "超大单买(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "buy_lg_amount",
    header: "大单买(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
];

const northColumns: ColumnDef<MoneyFlowItem>[] = [
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
    accessorKey: "north_net",
    header: "北向净买(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return <span className={color}>{v.toFixed(2)}</span>;
    },
  },
  {
    accessorKey: "north_amount",
    header: "北向买入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "net_mf_amount",
    header: "主力净流入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      if (v == null) return "—";
      const color = v >= 0 ? "text-red-500" : "text-green-500";
      return <span className={color}>{v.toFixed(2)}</span>;
    },
  },
];

export default function FlowPage() {
  const [tradeDate, setTradeDate] = useState("");
  const [tab, setTab] = useState("main");

  const flowType = tab === "main" ? "main" : "north";
  const { data, isLoading } = useMoneyFlow(
    tradeDate || undefined,
    flowType,
    undefined,
    50,
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">资金流向</h1>

      <div className="flex items-center gap-3">
        <Input
          type="text"
          placeholder="交易日期 (YYYYMMDD)，留空取最新"
          value={tradeDate}
          onChange={(e) => setTradeDate(e.target.value)}
          className="max-w-xs"
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="main">主力资金</TabsTrigger>
          <TabsTrigger value="north">北向资金</TabsTrigger>
        </TabsList>
        <TabsContent value="main" className="mt-4">
          <DataTable columns={mainColumns} data={data?.data ?? []} isLoading={isLoading} />
        </TabsContent>
        <TabsContent value="north" className="mt-4">
          <DataTable columns={northColumns} data={data?.data ?? []} isLoading={isLoading} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
