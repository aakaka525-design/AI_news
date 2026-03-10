import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScoreSummaryCard } from "@/components/scores/score-summary-card";
import type { StockScoreResponse } from "@/lib/types";

const scoredData: StockScoreResponse = {
  ts_code: "000001.SZ",
  trade_date: "20260310",
  score: 72.5,
  score_version: "v1",
  status: "scored",
  exclusion_reason: null,
  experimental: true,
  coverage_ratio: 0.83,
  low_confidence: false,
  buckets: {
    price_trend: { score: 80.0, weight_nominal: 0.4, weight_effective: 0.38, coverage_ratio: 1.0 },
    flow: { score: 65.0, weight_nominal: 0.3, weight_effective: 0.25, coverage_ratio: 0.5 },
    fundamentals: { score: 70.0, weight_nominal: 0.3, weight_effective: 0.3, coverage_ratio: 1.0 },
  },
  factors: [
    {
      factor_key: "rps_composite",
      bucket: "price_trend",
      available: true,
      raw_value: 85.0,
      normalized_value: 0.85,
      weight_nominal: 0.2,
      weight_effective: 0.2,
      staleness_trading_days: 0,
      source_key: "tushare",
      source_table: "stock_rps",
      data_date: "20260310",
    },
    {
      factor_key: "northbound_flow",
      bucket: "flow",
      available: false,
      raw_value: null,
      normalized_value: null,
      weight_nominal: 0.15,
      weight_effective: 0,
      staleness_trading_days: 0,
      source_key: "tushare",
      source_table: "ts_hk_hold",
      data_date: null,
    },
  ],
};

const excludedData: StockScoreResponse = {
  ts_code: "000001.SZ",
  trade_date: "20260310",
  score: null,
  score_version: "v1",
  status: "excluded",
  exclusion_reason: "st",
  experimental: true,
  coverage_ratio: null,
  low_confidence: false,
  buckets: {},
  factors: [],
};

const lowConfidenceData: StockScoreResponse = {
  ...scoredData,
  low_confidence: true,
  coverage_ratio: 0.33,
};

describe("ScoreSummaryCard", () => {
  it("renders scored stock with total score and buckets", () => {
    render(<ScoreSummaryCard data={scoredData} />);
    expect(screen.getByText("综合评分")).toBeDefined();
    expect(screen.getByText("72.5")).toBeDefined();
    expect(screen.getByText("80.0")).toBeDefined(); // price_trend
    expect(screen.getByText("65.0")).toBeDefined(); // flow
    expect(screen.getByText("70.0")).toBeDefined(); // fundamentals
    expect(screen.getByText("实验版")).toBeDefined();
  });

  it("renders excluded stock with reason badge", () => {
    render(<ScoreSummaryCard data={excludedData} />);
    expect(screen.getByText("--")).toBeDefined();
    expect(screen.getByText("st")).toBeDefined();
  });

  it("renders null score as empty state", () => {
    const noScoreData: StockScoreResponse = {
      ...scoredData,
      score: null,
      status: "scored",
    };
    render(<ScoreSummaryCard data={noScoreData} />);
    expect(screen.getByText("暂无评分数据")).toBeDefined();
  });

  it("shows low confidence badge when low_confidence is true", () => {
    render(<ScoreSummaryCard data={lowConfidenceData} />);
    expect(screen.getByText("低置信")).toBeDefined();
  });

  it("factor details are hidden by default", () => {
    render(<ScoreSummaryCard data={scoredData} />);
    expect(screen.getByText("因子明细 (2)")).toBeDefined();
    // Factor details should not be visible
    expect(screen.queryByText("rps_composite")).toBeNull();
  });

  it("expands factor details on click", () => {
    render(<ScoreSummaryCard data={scoredData} />);
    fireEvent.click(screen.getByText("因子明细 (2)"));
    expect(screen.getByText("rps_composite")).toBeDefined();
    expect(screen.getByText("northbound_flow")).toBeDefined();
    // Unavailable factor shows badge
    expect(screen.getByText("缺失")).toBeDefined();
  });
});
