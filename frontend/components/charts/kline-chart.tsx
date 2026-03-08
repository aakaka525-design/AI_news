"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";

interface KlineItem {
  trade_date: string; // YYYYMMDD
  open: number;
  high: number;
  low: number;
  close: number;
  vol?: number;
}

export type TimeRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

interface KlineChartProps {
  data: KlineItem[];
  height?: number;
  showMA?: boolean;
  activeRange?: TimeRange;
  onRangeChange?: (range: TimeRange) => void;
}

const RANGE_OPTIONS: { label: string; value: TimeRange }[] = [
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "6M", value: "6M" },
  { label: "1Y", value: "1Y" },
  { label: "ALL", value: "ALL" },
];

// A 股配色常量（红涨绿跌）
const CHART_COLORS = {
  up: "#ef4444",
  down: "#22c55e",
  upAlpha: "#ef444480",
  downAlpha: "#22c55e80",
  text: "#9ca3af",
  grid: "#e5e7eb20",
  border: "#e5e7eb40",
} as const;

const MA_COLORS = {
  5: "#06b6d4",
  10: "#f59e0b",
  20: "#a855f7",
  60: "#22c55e",
} as const;

function toTime(dateStr: string): Time {
  const y = dateStr.slice(0, 4);
  const m = dateStr.slice(4, 6);
  const d = dateStr.slice(6, 8);
  return `${y}-${m}-${d}` as Time;
}

function calcMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += closes[j];
      result.push(sum / period);
    }
  }
  return result;
}

export function KlineChart({
  data,
  height = 400,
  showMA = true,
  activeRange,
  onRangeChange,
}: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    let chart: IChartApi;
    try {
      chart = createChart(containerRef.current, {
        height,
        layout: {
          background: { color: "transparent" },
          textColor: CHART_COLORS.text,
        },
        grid: {
          vertLines: { color: CHART_COLORS.grid },
          horzLines: { color: CHART_COLORS.grid },
        },
        crosshair: { mode: 0 },
        rightPriceScale: { borderColor: CHART_COLORS.border },
        timeScale: { borderColor: CHART_COLORS.border },
      });
    } catch (err) {
      console.error("Failed to create chart:", err);
      return;
    }
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      borderUpColor: CHART_COLORS.up,
      borderDownColor: CHART_COLORS.down,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
    });

    // Sort ascending by date for the chart
    const sorted = [...data].sort((a, b) => a.trade_date.localeCompare(b.trade_date));

    const candleData: CandlestickData[] = sorted.map((d) => ({
      time: toTime(d.trade_date),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    candleSeries.setData(candleData);

    // MA overlays
    if (showMA) {
      const closes = sorted.map((d) => d.close);
      const periods = [5, 10, 20, 60] as const;
      for (const period of periods) {
        const maValues = calcMA(closes, period);
        const maData: LineData[] = [];
        for (let i = 0; i < sorted.length; i++) {
          if (maValues[i] !== null) {
            maData.push({
              time: toTime(sorted[i].trade_date),
              value: maValues[i]!,
            });
          }
        }
        const lineSeries = chart.addSeries(LineSeries, {
          color: MA_COLORS[period],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        lineSeries.setData(maData);
      }
    }

    // Volume histogram (bottom 20%)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volData: HistogramData[] = sorted.map((d) => ({
      time: toTime(d.trade_date),
      value: d.vol ?? 0,
      color: d.close >= d.open ? CHART_COLORS.upAlpha : CHART_COLORS.downAlpha,
    }));
    volumeSeries.setData(volData);

    chart.timeScale().fitContent();

    // Responsive resize
    let ro: ResizeObserver | undefined;
    try {
      ro = new ResizeObserver(() => {
        if (containerRef.current) {
          chart.applyOptions({ width: containerRef.current.clientWidth });
        }
      });
      ro.observe(containerRef.current);
    } catch (err) {
      console.error("ResizeObserver failed:", err);
    }

    return () => {
      ro?.disconnect();
      try { chart.remove(); } catch { /* already disposed */ }
      chartRef.current = null;
    };
  }, [data, height, showMA]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground" style={{ height }}>
        暂无K线数据
      </div>
    );
  }

  return (
    <div>
      {onRangeChange && (
        <div className="flex flex-wrap gap-1 mb-3 overflow-x-auto">
          {RANGE_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={activeRange === opt.value ? "default" : "outline"}
              size="sm"
              className="text-xs h-7 px-2 whitespace-nowrap"
              onClick={() => onRangeChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
          <div className="flex gap-2 ml-auto text-xs items-center text-muted-foreground whitespace-nowrap">
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[5] }} />MA5</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[10] }} />MA10</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[20] }} />MA20</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[60] }} />MA60</span>
          </div>
        </div>
      )}
      <div ref={containerRef} />
    </div>
  );
}
