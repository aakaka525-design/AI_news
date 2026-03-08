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
  useFullAnalysis,
  useIntraday,
} from "@/lib/hooks";
import { useTradingSession } from "@/lib/use-trading-session";
import { WatchlistButton } from "@/components/watchlist-button";
import type {
  MoneyFlowItem,
  DragonTigerItem,
  ResearchReport,
  FullAnalysis,
} from "@/lib/types";

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

/* ---------- AI Full Analysis Card ---------- */

function AnalysisSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-48" />
      </CardHeader>
      <CardContent className="space-y-4">
        <Skeleton className="h-4 w-32" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
        <Skeleton className="h-32" />
      </CardContent>
    </Card>
  );
}

function FullAnalysisCard({ data }: { data: FullAnalysis }) {
  const { pattern, support_resistance: sr, sector_rank, market, announcements, generated_at } = data;

  const genTime = new Date(generated_at).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">AI 综合分析</CardTitle>
          <span className="text-xs text-muted-foreground">生成时间: {genTime}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 1. 技术形态摘要 */}
        <div>
          <h4 className="text-sm font-semibold mb-2">技术形态</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">均线排列</p>
              <Badge
                variant="secondary"
                className={`mt-1 ${pattern.ma_arrangement === "多头排列" ? "bg-red-100 text-red-700" : pattern.ma_arrangement === "空头排列" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"}`}
              >
                {pattern.ma_arrangement}
              </Badge>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">价格位置</p>
              <p className="text-sm font-bold mt-1">
                {pattern.above_ma20 ? (
                  <span className="text-red-500">MA20 上方</span>
                ) : (
                  <span className="text-green-500">MA20 下方</span>
                )}
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">量比</p>
              <p className={`text-sm font-bold mt-1 ${pattern.vol_ratio >= 1.5 ? "text-red-500" : pattern.vol_ratio <= 0.5 ? "text-green-500" : ""}`}>
                {pattern.vol_ratio.toFixed(2)}
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">近期振幅</p>
              <p className="text-sm font-bold mt-1">
                {pattern.recent_low.toFixed(2)} - {pattern.recent_high.toFixed(2)}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 mt-2">
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">现价</p>
              <p className="text-sm font-bold mt-1">{pattern.price.toFixed(2)}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">MA5</p>
              <p className="text-sm font-bold mt-1">{pattern.ma5.toFixed(2)}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">MA10</p>
              <p className="text-sm font-bold mt-1">{pattern.ma10.toFixed(2)}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">MA20</p>
              <p className="text-sm font-bold mt-1">{pattern.ma20.toFixed(2)}</p>
            </div>
          </div>
        </div>

        {/* 2. 支撑阻力位 */}
        <div>
          <h4 className="text-sm font-semibold mb-2">支撑 / 阻力位</h4>
          <div className="rounded-md border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">级别</th>
                  <th className="px-3 py-2 text-right font-medium text-red-500">阻力位</th>
                  <th className="px-3 py-2 text-right font-medium text-green-500">支撑位</th>
                </tr>
              </thead>
              <tbody>
                {[3, 2, 1].map((level) => {
                  const rKey = `R${level}` as keyof typeof sr;
                  const sKey = `S${level}` as keyof typeof sr;
                  return (
                    <tr key={level} className="border-t">
                      <td className="px-3 py-2 font-medium">第{level}级</td>
                      <td className="px-3 py-2 text-right text-red-500 font-mono">
                        {sr[rKey].toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right text-green-500 font-mono">
                        {sr[sKey].toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 3. 板块排名 */}
        {sector_rank.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2">板块排名</h4>
            <div className="space-y-2">
              {sector_rank.map((sr_item, idx) => (
                <div key={idx} className="flex items-center gap-3 rounded-md border p-3">
                  <Badge variant="outline" className="shrink-0">{sr_item.type}</Badge>
                  <span className="text-sm font-medium">{sr_item.sector}</span>
                  <span className="ml-auto text-sm">
                    排名 <span className="font-bold">{sr_item.rank}</span> / {sr_item.total}
                  </span>
                  <Badge
                    variant="secondary"
                    className={`shrink-0 ${sr_item.rps_20 >= 80 ? "bg-red-100 text-red-700" : sr_item.rps_20 <= 20 ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"}`}
                  >
                    RPS: {sr_item.rps_20.toFixed(1)}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. 大盘环境 */}
        <div>
          <h4 className="text-sm font-semibold mb-2">大盘环境</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">指数</p>
              <p className="text-sm font-bold mt-1">{market.index}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">收盘</p>
              <p className="text-sm font-bold mt-1">{market.close.toFixed(2)}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">涨跌幅</p>
              <p className={`text-sm font-bold mt-1 ${market.change_pct >= 0 ? "text-red-500" : "text-green-500"}`}>
                {market.change_pct >= 0 ? "+" : ""}{market.change_pct.toFixed(2)}%
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">趋势</p>
              <p className="text-sm font-bold mt-1">
                {market.above_ma5 ? (
                  <span className="text-red-500">MA5 上方</span>
                ) : (
                  <span className="text-green-500">MA5 下方</span>
                )}
              </p>
            </div>
          </div>
        </div>

        {/* 5. 最新公告 */}
        {announcements.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2">最新公告</h4>
            <div className="space-y-1">
              {announcements.map((ann, idx) => (
                <div key={idx} className="flex items-start gap-2 text-sm py-1.5 border-b last:border-b-0">
                  <span className="text-muted-foreground shrink-0">{ann.date}</span>
                  <span>{ann.title}</span>
                </div>
              ))}
            </div>
          </div>
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
  const { data: analysisData, isLoading: analysisLoading, isError: analysisError } = useFullAnalysis(tsCode);

  // 盘中实时数据
  const { isTrading, statusText } = useTradingSession();
  const { data: intradayData } = useIntraday(tsCode, isTrading);

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
          <WatchlistButton tsCode={tsCode} />
        </div>
        <div className="flex gap-2 mt-2 flex-wrap items-center">
          {profile.industry && <Badge variant="secondary">{profile.industry}</Badge>}
          {profile.market && <Badge variant="outline">{profile.market}</Badge>}
          <Badge
            variant="outline"
            className={
              isTrading
                ? "border-red-500 text-red-500"
                : "border-muted-foreground text-muted-foreground"
            }
          >
            {statusText}
          </Badge>
        </div>

        {/* 价格 + 涨跌幅 */}
        <div className="mt-3 flex items-end gap-4 flex-wrap">
          {isTrading && intradayData?.price != null ? (
            <>
              <span className="text-3xl font-bold tabular-nums">
                {intradayData.price.toFixed(2)}
              </span>
              {intradayData.change_pct != null && (
                <span
                  className={`text-lg font-semibold ${
                    intradayData.change_pct >= 0 ? "text-red-500" : "text-green-500"
                  }`}
                >
                  {intradayData.change_pct >= 0 ? "+" : ""}
                  {intradayData.change_pct.toFixed(2)}%
                </span>
              )}
              {intradayData.volume != null && (
                <span className="text-sm text-muted-foreground">
                  成交量: {(intradayData.volume / 10000).toFixed(2)} 万手
                </span>
              )}
              {intradayData.update_time && (
                <span className="text-xs text-muted-foreground">
                  更新: {intradayData.update_time}
                </span>
              )}
            </>
          ) : (
            <>
              {val?.pe_ttm != null && dailyData?.data?.[0]?.close != null ? (
                <>
                  <span className="text-3xl font-bold tabular-nums">
                    {dailyData.data[0].close.toFixed(2)}
                  </span>
                  {dailyData.data[0].pct_chg != null && (
                    <span
                      className={`text-lg font-semibold ${
                        (dailyData.data[0].pct_chg ?? 0) >= 0
                          ? "text-red-500"
                          : "text-green-500"
                      }`}
                    >
                      {(dailyData.data[0].pct_chg ?? 0) >= 0 ? "+" : ""}
                      {dailyData.data[0].pct_chg?.toFixed(2)}%
                    </span>
                  )}
                </>
              ) : null}
            </>
          )}
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

      {/* AI Full Analysis */}
      {analysisLoading ? (
        <AnalysisSkeleton />
      ) : analysisError ? (
        <Card>
          <CardContent className="p-6 text-center text-muted-foreground">
            暂无分析数据
          </CardContent>
        </Card>
      ) : analysisData ? (
        <FullAnalysisCard data={analysisData} />
      ) : null}

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
