"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { IndexCard } from "@/components/market/index-card";
import { MarketBreadth } from "@/components/market/market-breadth";
import { stockColumns } from "@/components/market/stock-columns";
import { useStocks, useStockIndustries, useMarketOverview } from "@/lib/hooks";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowUpDown } from "lucide-react";

const SORT_OPTIONS = [
  { label: "代码", value: "ts_code" },
  { label: "涨跌幅", value: "pct_chg" },
  { label: "成交额", value: "amount" },
  { label: "总市值", value: "total_mv" },
  { label: "换手率", value: "turnover_rate" },
] as const;

export default function MarketPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [industry, setIndustry] = useState("");
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<string>("desc");
  const pageSize = 20;

  const debouncedSearch = search.trim() || undefined;
  const debouncedIndustry = industry || undefined;

  const { data: overview, isLoading: overviewLoading } = useMarketOverview();
  const { data: stocksData, isLoading: stocksLoading } = useStocks(
    page,
    pageSize,
    debouncedSearch,
    debouncedIndustry,
    undefined,
    sortBy,
    sortOrder,
  );
  const { data: industries } = useStockIndustries();

  const stocks = stocksData?.data ?? [];
  const total = stocksData?.total ?? 0;
  const pageCount = Math.ceil(total / pageSize);

  const topIndices = (overview?.data ?? []).slice(0, 6);

  function handleSort(value: string) {
    if (sortBy === value) {
      setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(value);
      setSortOrder("desc");
    }
    setPage(1);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">市场行情</h1>

      {/* Index overview */}
      {overviewLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        topIndices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {topIndices.map((item) => (
              <IndexCard key={item.ts_code} item={item} />
            ))}
          </div>
        )
      )}

      {/* Market breadth */}
      {!overviewLoading && topIndices.length > 0 && (
        <MarketBreadth indices={topIndices} />
      )}

      {/* Filters + Sort */}
      <div className="flex flex-wrap gap-3 items-center">
        <Input
          placeholder="搜索代码/名称..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="max-w-xs"
        />
        <select
          value={industry}
          onChange={(e) => {
            setIndustry(e.target.value);
            setPage(1);
          }}
          className="h-9 rounded-md border bg-transparent px-3 text-sm"
        >
          <option value="">全部行业</option>
          {(industries?.data ?? []).map((ind) => (
            <option key={ind} value={ind}>
              {ind}
            </option>
          ))}
        </select>

        <div className="flex gap-1 ml-auto">
          {SORT_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={sortBy === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => handleSort(opt.value)}
              className="text-xs"
            >
              {opt.label}
              {sortBy === opt.value && (
                <ArrowUpDown className="ml-1 h-3 w-3" />
              )}
            </Button>
          ))}
        </div>
      </div>

      {/* Stock table */}
      <DataTable
        columns={stockColumns}
        data={stocks}
        isLoading={stocksLoading}
        pageCount={pageCount}
        pageIndex={page - 1}
        pageSize={pageSize}
        onPageChange={(p) => setPage(p + 1)}
        total={total}
      />
    </div>
  );
}
