import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScoreRankingTable } from "@/components/scores/score-ranking-table";
import type { ScoreRankingItem } from "@/lib/types";

const mockItems: ScoreRankingItem[] = [
  {
    ts_code: "000001.SZ",
    name: "平安银行",
    industry: "银行",
    score: 85.0,
    price_trend_score: 90.0,
    flow_score: 80.0,
    fundamentals_score: 75.0,
    coverage_ratio: 1.0,
    low_confidence: false,
  },
  {
    ts_code: "600036.SH",
    name: "招商银行",
    industry: "银行",
    score: 72.5,
    price_trend_score: 70.0,
    flow_score: 65.0,
    fundamentals_score: 80.0,
    coverage_ratio: 0.83,
    low_confidence: false,
  },
  {
    ts_code: "300750.SZ",
    name: "宁德时代",
    industry: "电气设备",
    score: 55.0,
    price_trend_score: 40.0,
    flow_score: 50.0,
    fundamentals_score: 70.0,
    coverage_ratio: 0.5,
    low_confidence: true,
  },
];

describe("ScoreRankingTable", () => {
  it("renders empty state when no items", () => {
    render(<ScoreRankingTable items={[]} />);
    expect(screen.getByText("暂无评分数据")).toBeDefined();
  });

  it("renders ranking items with scores", () => {
    render(<ScoreRankingTable items={mockItems} />);
    expect(screen.getByText("平安银行")).toBeDefined();
    expect(screen.getByText("招商银行")).toBeDefined();
    expect(screen.getByText("宁德时代")).toBeDefined();
    expect(screen.getByText("85.0")).toBeDefined();
    expect(screen.getByText("72.5")).toBeDefined();
  });

  it("shows low confidence badge", () => {
    render(<ScoreRankingTable items={mockItems} />);
    const badges = screen.getAllByText("低置信");
    expect(badges.length).toBe(1); // only 宁德时代
  });

  it("displays industry column", () => {
    render(<ScoreRankingTable items={mockItems} />);
    expect(screen.getByText("电气设备")).toBeDefined();
  });

  it("calls onRowClick when row is clicked", () => {
    const handleClick = vi.fn();
    render(<ScoreRankingTable items={mockItems} onRowClick={handleClick} />);
    // Click on first stock name
    fireEvent.click(screen.getByText("平安银行"));
    expect(handleClick).toHaveBeenCalledWith("000001.SZ");
  });
});
