"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
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

interface KlineChartProps {
  data: KlineItem[];
  height?: number;
}

function toTime(dateStr: string): Time {
  // YYYYMMDD → YYYY-MM-DD
  const y = dateStr.slice(0, 4);
  const m = dateStr.slice(4, 6);
  const d = dateStr.slice(6, 8);
  return `${y}-${m}-${d}` as Time;
}

export function KlineChart({ data, height = 400 }: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: "transparent" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#e5e7eb20" },
        horzLines: { color: "#e5e7eb20" },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: "#e5e7eb40" },
      timeScale: { borderColor: "#e5e7eb40" },
    });
    chartRef.current = chart;

    // A股配色：红涨绿跌
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderUpColor: "#ef4444",
      borderDownColor: "#22c55e",
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
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
      color: d.close >= d.open ? "#ef444480" : "#22c55e80",
    }));
    volumeSeries.setData(volData);

    chart.timeScale().fitContent();

    // Responsive
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground" style={{ height }}>
        暂无K线数据
      </div>
    );
  }

  return <div ref={containerRef} />;
}
