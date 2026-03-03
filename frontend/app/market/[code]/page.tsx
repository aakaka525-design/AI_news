"use client";

import { use } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable, ColumnDef } from "@/components/ui/data-table";
import { KlineChart } from "@/components/charts/kline-chart";
import {
  useStockProfile,
  useStockDaily,
  useMoneyFlow,
  useDragonTiger,
} from "@/lib/hooks";
import type { MoneyFlowItem, DragonTigerItem } from "@/lib/types";

const flowColumns: ColumnDef<MoneyFlowItem>[] = [
  { accessorKey: "trade_date", header: "日期" },
  { accessorKey: "flow_type", header: "类型" },
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
    header: "占比(%)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? `${v.toFixed(2)}%` : "—";
    },
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
];

const dragonColumns: ColumnDef<DragonTigerItem>[] = [
  { accessorKey: "trade_date", header: "日期" },
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
  { accessorKey: "reason", header: "上榜原因" },
  {
    accessorKey: "inst_buy",
    header: "机构买入(万)",
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return v != null ? v.toFixed(2) : "—";
    },
  },
];

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-lg font-bold mt-1">{value}</p>
      </CardContent>
    </Card>
  );
}

function fmtMv(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 10000) return `${(v / 10000).toFixed(2)} 亿`;
  return `${v.toFixed(2)} 万`;
}

export default function StockDetailPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = use(params);
  const tsCode = decodeURIComponent(code);

  const { data: profile, isLoading: profileLoading } = useStockProfile(tsCode);
  const { data: dailyData, isLoading: dailyLoading } = useStockDaily(tsCode, 250);
  const { data: flowData } = useMoneyFlow(undefined, undefined, tsCode, 20);
  const { data: dragonData } = useDragonTiger(undefined, tsCode, 20);

  if (profileLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-[400px]" />
      </div>
    );
  }

  if (!profile) {
    return <div className="text-muted-foreground">未找到股票 {tsCode}</div>;
  }

  const val = profile.valuation;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{profile.name}</h1>
          <span className="font-mono text-muted-foreground">{profile.ts_code}</span>
        </div>
        <div className="flex gap-2 mt-2">
          {profile.industry && <Badge variant="secondary">{profile.industry}</Badge>}
          {profile.market && <Badge variant="outline">{profile.market}</Badge>}
        </div>
      </div>

      {/* Valuation stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="PE(TTM)" value={val?.pe_ttm != null ? val.pe_ttm.toFixed(2) : "—"} />
        <StatCard label="PB" value={val?.pb != null ? val.pb.toFixed(2) : "—"} />
        <StatCard label="总市值" value={fmtMv(val?.total_mv)} />
        <StatCard label="换手率" value={val?.turnover_rate != null ? `${val.turnover_rate.toFixed(2)}%` : "—"} />
      </div>

      {/* K-line chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">K 线图 (近250日)</CardTitle>
        </CardHeader>
        <CardContent>
          {dailyLoading ? (
            <Skeleton className="h-[400px]" />
          ) : (
            <KlineChart data={dailyData?.data ?? []} />
          )}
        </CardContent>
      </Card>

      {/* Tabs: money flow + dragon tiger */}
      <Tabs defaultValue="flow">
        <TabsList>
          <TabsTrigger value="flow">资金流向</TabsTrigger>
          <TabsTrigger value="dragon">龙虎榜</TabsTrigger>
        </TabsList>
        <TabsContent value="flow" className="mt-4">
          <DataTable columns={flowColumns} data={flowData?.data ?? []} />
        </TabsContent>
        <TabsContent value="dragon" className="mt-4">
          <DataTable columns={dragonColumns} data={dragonData?.data ?? []} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
