"use client";

import { use, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable, ColumnDef } from "@/components/ui/data-table";
import { KlineChart, type TimeRange } from "@/components/charts/kline-chart";
import { ValuationChart } from "@/components/charts/valuation-chart";
import {
  useStockProfile,
  useStockDaily,
  useMoneyFlow,
  useDragonTiger,
  useValuationHistory,
  useReports,
} from "@/lib/hooks";
import type { MoneyFlowItem, DragonTigerItem, ResearchReport } from "@/lib/types";

const RANGE_LIMITS: Record<TimeRange, number> = {
  "1M": 22,
  "3M": 66,
  "6M": 132,
  "1Y": 250,
  "ALL": 1000,
};

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

const RATING_COLORS: Record<string, string> = {
  "买入": "bg-red-100 text-red-700",
  "增持": "bg-orange-100 text-orange-700",
  "中性": "bg-gray-100 text-gray-700",
  "减持": "bg-blue-100 text-blue-700",
  "卖出": "bg-green-100 text-green-700",
};

function ReportCard({ report }: { report: ResearchReport }) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <p className="text-sm font-medium leading-tight">{report.title}</p>
        <div className="flex items-center gap-2 flex-wrap">
          {report.institution && (
            <span className="text-xs text-muted-foreground">{report.institution}</span>
          )}
          {report.rating && (
            <Badge className={`text-xs ${RATING_COLORS[report.rating] ?? "bg-gray-100 text-gray-700"}`}>
              {report.rating}
            </Badge>
          )}
          {report.target_price != null && (
            <span className="text-xs text-red-500">目标价: {report.target_price}</span>
          )}
        </div>
        {report.publish_date && (
          <p className="text-xs text-muted-foreground">{report.publish_date}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function StockDetailPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = use(params);
  const tsCode = decodeURIComponent(code);
  const [range, setRange] = useState<TimeRange>("1Y");
  const limit = RANGE_LIMITS[range];

  const { data: profile, isLoading: profileLoading } = useStockProfile(tsCode);
  const { data: dailyData, isLoading: dailyLoading } = useStockDaily(tsCode, limit);
  const { data: flowData } = useMoneyFlow(undefined, undefined, tsCode, 20);
  const { data: dragonData } = useDragonTiger(undefined, tsCode, 20);
  const { data: valuationData } = useValuationHistory(tsCode);
  // Extract stock_code (symbol portion) for research reports
  const stockCode = tsCode.split(".")[0];
  const { data: reportsData } = useReports(stockCode, 20);

  if (profileLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
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

      {/* Valuation stats — expanded to 6 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard label="PE(TTM)" value={val?.pe_ttm != null ? val.pe_ttm.toFixed(2) : "—"} />
        <StatCard label="PB" value={val?.pb != null ? val.pb.toFixed(2) : "—"} />
        <StatCard label="PS(TTM)" value={val?.ps_ttm != null ? val.ps_ttm.toFixed(2) : "—"} />
        <StatCard label="总市值" value={fmtMv(val?.total_mv)} />
        <StatCard label="换手率" value={val?.turnover_rate != null ? `${val.turnover_rate.toFixed(2)}%` : "—"} />
        <StatCard
          label="股息率"
          value={val?.dv_ttm != null ? `${val.dv_ttm.toFixed(2)}%` : "—"}
        />
      </div>

      {/* K-line chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">K 线图</CardTitle>
        </CardHeader>
        <CardContent>
          {dailyLoading ? (
            <Skeleton className="h-[400px]" />
          ) : (
            <KlineChart
              data={dailyData?.data ?? []}
              activeRange={range}
              onRangeChange={setRange}
            />
          )}
        </CardContent>
      </Card>

      {/* Tabs: flow + dragon + valuation + reports */}
      <Tabs defaultValue="flow">
        <TabsList>
          <TabsTrigger value="flow">资金流向</TabsTrigger>
          <TabsTrigger value="dragon">龙虎榜</TabsTrigger>
          <TabsTrigger value="valuation">估值趋势</TabsTrigger>
          <TabsTrigger value="reports">研究报告</TabsTrigger>
        </TabsList>
        <TabsContent value="flow" className="mt-4">
          <DataTable columns={flowColumns} data={flowData?.data ?? []} />
        </TabsContent>
        <TabsContent value="dragon" className="mt-4">
          <DataTable columns={dragonColumns} data={dragonData?.data ?? []} />
        </TabsContent>
        <TabsContent value="valuation" className="mt-4">
          <ValuationChart data={valuationData?.data ?? []} />
        </TabsContent>
        <TabsContent value="reports" className="mt-4">
          {(reportsData?.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-sm">暂无相关研报</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {(reportsData?.data ?? []).map((report, i) => (
                <ReportCard key={report.id ?? i} report={report} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
