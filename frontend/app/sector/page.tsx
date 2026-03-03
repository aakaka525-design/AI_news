"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, ColumnDef } from "@/components/ui/data-table";
import { useSectors } from "@/lib/hooks";
import type { SectorItem } from "@/lib/types";

const columns: ColumnDef<SectorItem>[] = [
  {
    accessorKey: "block_name",
    header: "板块名称",
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
    accessorKey: "close",
    header: "收盘",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      return v != null ? v.toFixed(2) : "—";
    },
  },
  {
    accessorKey: "amount",
    header: "成交额",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      if (v == null) return "—";
      if (v >= 10000) return `${(v / 10000).toFixed(2)} 亿`;
      return `${v.toFixed(2)} 万`;
    },
  },
  {
    accessorKey: "turnover_rate",
    header: "换手率",
    cell: ({ getValue }) => {
      const v = getValue() as number | undefined;
      return v != null ? `${v.toFixed(2)}%` : "—";
    },
  },
  {
    accessorKey: "lead_stock",
    header: "领涨股",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{(getValue() as string) ?? "—"}</span>
    ),
  },
  {
    accessorKey: "up_count",
    header: "涨",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? <span className="text-red-500">{v}</span> : "—";
    },
  },
  {
    accessorKey: "down_count",
    header: "跌",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? <span className="text-green-500">{v}</span> : "—";
    },
  },
];

export default function SectorPage() {
  const [blockType, setBlockType] = useState("industry");

  const { data, isLoading } = useSectors(blockType, undefined, 50);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">板块行情</h1>

      <Tabs value={blockType} onValueChange={setBlockType}>
        <TabsList>
          <TabsTrigger value="industry">行业板块</TabsTrigger>
          <TabsTrigger value="concept">概念板块</TabsTrigger>
        </TabsList>
        <TabsContent value="industry" className="mt-4">
          <DataTable columns={columns} data={data?.data ?? []} isLoading={isLoading} />
        </TabsContent>
        <TabsContent value="concept" className="mt-4">
          <DataTable columns={columns} data={data?.data ?? []} isLoading={isLoading} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
