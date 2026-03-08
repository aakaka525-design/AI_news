"use client";

import { useEffect, useRef, useState } from "react";
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
export type IndicatorType = "MA" | "MACD" | "RSI" | "BOLL";

interface KlineChartProps {
  data: KlineItem[];
  height?: number;
  showMA?: boolean;
  activeRange?: TimeRange;
  onRangeChange?: (range: TimeRange) => void;
  activeIndicator?: IndicatorType;
  onIndicatorChange?: (indicator: IndicatorType) => void;
}

const RANGE_OPTIONS: { label: string; value: TimeRange }[] = [
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "6M", value: "6M" },
  { label: "1Y", value: "1Y" },
  { label: "ALL", value: "ALL" },
];

const INDICATOR_OPTIONS: { label: string; value: IndicatorType }[] = [
  { label: "MA", value: "MA" },
  { label: "MACD", value: "MACD" },
  { label: "RSI", value: "RSI" },
  { label: "BOLL", value: "BOLL" },
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

const INDICATOR_COLORS = {
  dif: "#06b6d4",      // cyan
  dea: "#f59e0b",      // amber
  rsi: "#a855f7",      // purple
  bollUpper: "#ef4444", // red
  bollMid: "#f59e0b",   // amber
  bollLower: "#22c55e", // green
  refLine: "#6b728080", // gray semi-transparent
} as const;

function toTime(dateStr: string): Time {
  const y = dateStr.slice(0, 4);
  const m = dateStr.slice(4, 6);
  const d = dateStr.slice(6, 8);
  return `${y}-${m}-${d}` as Time;
}

// ---- Indicator calculation functions ----

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

function calcEMA(data: number[], period: number): number[] {
  const ema: number[] = [];
  const k = 2 / (period + 1);
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      ema.push(data[0]);
    } else {
      ema.push(data[i] * k + ema[i - 1] * (1 - k));
    }
  }
  return ema;
}

function calcMACD(closes: number[]): {
  dif: (number | null)[];
  dea: (number | null)[];
  histogram: (number | null)[];
} {
  if (closes.length === 0) return { dif: [], dea: [], histogram: [] };

  const ema12 = calcEMA(closes, 12);
  const ema26 = calcEMA(closes, 26);

  const difRaw: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    difRaw.push(ema12[i] - ema26[i]);
  }

  const deaRaw = calcEMA(difRaw, 9);

  // Return null for the first 25 values (need at least 26 points for meaningful MACD)
  const minPeriod = 25;
  const dif: (number | null)[] = difRaw.map((v, i) => (i < minPeriod ? null : v));
  const dea: (number | null)[] = deaRaw.map((v, i) => (i < minPeriod ? null : v));
  const histogram: (number | null)[] = difRaw.map((v, i) =>
    i < minPeriod ? null : (v - deaRaw[i]) * 2
  );

  return { dif, dea, histogram };
}

function calcRSI(closes: number[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = [];
  if (closes.length === 0) return result;

  result.push(null); // first element has no change

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;

    if (i < period) {
      avgGain += gain;
      avgLoss += loss;
      result.push(null);
    } else if (i === period) {
      avgGain = (avgGain + gain) / period;
      avgLoss = (avgLoss + loss) / period;
      if (avgLoss === 0) {
        result.push(100);
      } else {
        const rs = avgGain / avgLoss;
        result.push(100 - 100 / (1 + rs));
      }
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      if (avgLoss === 0) {
        result.push(100);
      } else {
        const rs = avgGain / avgLoss;
        result.push(100 - 100 / (1 + rs));
      }
    }
  }
  return result;
}

function calcBollinger(
  closes: number[],
  period: number = 20,
  multiplier: number = 2
): {
  upper: (number | null)[];
  mid: (number | null)[];
  lower: (number | null)[];
} {
  const upper: (number | null)[] = [];
  const mid: (number | null)[] = [];
  const lower: (number | null)[] = [];

  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      upper.push(null);
      mid.push(null);
      lower.push(null);
    } else {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += closes[j];
      const ma = sum / period;

      let sqSum = 0;
      for (let j = i - period + 1; j <= i; j++) sqSum += (closes[j] - ma) ** 2;
      const std = Math.sqrt(sqSum / period);

      mid.push(ma);
      upper.push(ma + multiplier * std);
      lower.push(ma - multiplier * std);
    }
  }
  return { upper, mid, lower };
}

// ---- Legend components ----

function MALegend() {
  return (
    <div className="flex gap-2 text-xs items-center text-muted-foreground whitespace-nowrap">
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[5] }} />MA5
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[10] }} />MA10
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[20] }} />MA20
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: MA_COLORS[60] }} />MA60
      </span>
    </div>
  );
}

function MACDLegend() {
  return (
    <div className="flex gap-2 text-xs items-center text-muted-foreground whitespace-nowrap">
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.dif }} />DIF
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.dea }} />DEA
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-2 h-2" style={{ background: CHART_COLORS.up, opacity: 0.6 }} />MACD
      </span>
    </div>
  );
}

function RSILegend() {
  return (
    <div className="flex gap-2 text-xs items-center text-muted-foreground whitespace-nowrap">
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.rsi }} />RSI14
      </span>
      <span className="text-muted-foreground/60">超买70 / 超卖30</span>
    </div>
  );
}

function BOLLLegend() {
  return (
    <div className="flex gap-2 text-xs items-center text-muted-foreground whitespace-nowrap">
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.bollUpper }} />上轨
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.bollMid }} />中轨
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-0.5" style={{ background: INDICATOR_COLORS.bollLower }} />下轨
      </span>
    </div>
  );
}

const LEGEND_MAP: Record<IndicatorType, React.FC> = {
  MA: MALegend,
  MACD: MACDLegend,
  RSI: RSILegend,
  BOLL: BOLLLegend,
};

export function KlineChart({
  data,
  height = 400,
  showMA = true,
  activeRange,
  onRangeChange,
  activeIndicator: controlledIndicator,
  onIndicatorChange,
}: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Support both controlled and uncontrolled indicator state
  const [internalIndicator, setInternalIndicator] = useState<IndicatorType>("MA");
  const currentIndicator = controlledIndicator ?? internalIndicator;
  const handleIndicatorChange = (ind: IndicatorType) => {
    if (onIndicatorChange) {
      onIndicatorChange(ind);
    } else {
      setInternalIndicator(ind);
    }
  };

  // Calculate the total chart height based on active indicator
  // MACD and RSI need extra space for sub-charts
  const needsSubChart = currentIndicator === "MACD" || currentIndicator === "RSI";
  const totalHeight = needsSubChart ? height + 150 : height;

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    let chart: IChartApi;
    try {
      chart = createChart(containerRef.current, {
        height: totalHeight,
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

    // Sort ascending by date for the chart
    const sorted = [...data].sort((a, b) =>
      a.trade_date.localeCompare(b.trade_date)
    );
    const closes = sorted.map((d) => d.close);
    const times = sorted.map((d) => toTime(d.trade_date));

    // ---- Main candlestick series ----
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      borderUpColor: CHART_COLORS.up,
      borderDownColor: CHART_COLORS.down,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
    });

    const candleData: CandlestickData[] = sorted.map((d) => ({
      time: toTime(d.trade_date),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    candleSeries.setData(candleData);

    // Adjust main price scale margins based on indicator
    // When MACD/RSI sub-chart is shown, give main chart less bottom margin
    if (needsSubChart) {
      chart.priceScale("right").applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.42 },
      });
    }

    // ---- MA overlay (when indicator is MA) ----
    if (currentIndicator === "MA" && showMA) {
      const periods = [5, 10, 20, 60] as const;
      for (const period of periods) {
        const maValues = calcMA(closes, period);
        const maData: LineData[] = [];
        for (let i = 0; i < sorted.length; i++) {
          if (maValues[i] !== null) {
            maData.push({ time: times[i], value: maValues[i]! });
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

    // ---- Bollinger Bands overlay (on main chart) ----
    if (currentIndicator === "BOLL") {
      const boll = calcBollinger(closes, 20, 2);

      const bollUpperData: LineData[] = [];
      const bollMidData: LineData[] = [];
      const bollLowerData: LineData[] = [];

      for (let i = 0; i < sorted.length; i++) {
        if (boll.upper[i] !== null) {
          bollUpperData.push({ time: times[i], value: boll.upper[i]! });
        }
        if (boll.mid[i] !== null) {
          bollMidData.push({ time: times[i], value: boll.mid[i]! });
        }
        if (boll.lower[i] !== null) {
          bollLowerData.push({ time: times[i], value: boll.lower[i]! });
        }
      }

      const upperSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.bollUpper,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      upperSeries.setData(bollUpperData);

      const midSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.bollMid,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      midSeries.setData(bollMidData);

      const lowerSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.bollLower,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      lowerSeries.setData(bollLowerData);
    }

    // ---- Volume histogram ----
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    if (needsSubChart) {
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.62, bottom: 0.32 },
      });
    } else {
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
    }

    const volData: HistogramData[] = sorted.map((d) => ({
      time: toTime(d.trade_date),
      value: d.vol ?? 0,
      color:
        d.close >= d.open ? CHART_COLORS.upAlpha : CHART_COLORS.downAlpha,
    }));
    volumeSeries.setData(volData);

    // ---- MACD sub-chart ----
    if (currentIndicator === "MACD") {
      const macd = calcMACD(closes);

      // MACD histogram
      const macdHistData: HistogramData[] = [];
      for (let i = 0; i < sorted.length; i++) {
        if (macd.histogram[i] !== null) {
          macdHistData.push({
            time: times[i],
            value: macd.histogram[i]!,
            color:
              macd.histogram[i]! >= 0 ? CHART_COLORS.up : CHART_COLORS.down,
          });
        }
      }
      const macdHistSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: "macd",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      chart.priceScale("macd").applyOptions({
        scaleMargins: { top: 0.78, bottom: 0.02 },
        autoScale: true,
      });
      macdHistSeries.setData(macdHistData);

      // DIF line
      const difData: LineData[] = [];
      for (let i = 0; i < sorted.length; i++) {
        if (macd.dif[i] !== null) {
          difData.push({ time: times[i], value: macd.dif[i]! });
        }
      }
      const difSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.dif,
        lineWidth: 1,
        priceScaleId: "macd",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      difSeries.setData(difData);

      // DEA line
      const deaData: LineData[] = [];
      for (let i = 0; i < sorted.length; i++) {
        if (macd.dea[i] !== null) {
          deaData.push({ time: times[i], value: macd.dea[i]! });
        }
      }
      const deaSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.dea,
        lineWidth: 1,
        priceScaleId: "macd",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      deaSeries.setData(deaData);
    }

    // ---- RSI sub-chart ----
    if (currentIndicator === "RSI") {
      const rsiValues = calcRSI(closes, 14);

      // RSI line
      const rsiData: LineData[] = [];
      for (let i = 0; i < sorted.length; i++) {
        if (rsiValues[i] !== null) {
          rsiData.push({ time: times[i], value: rsiValues[i]! });
        }
      }
      const rsiSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.rsi,
        lineWidth: 1,
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      chart.priceScale("rsi").applyOptions({
        scaleMargins: { top: 0.78, bottom: 0.02 },
        autoScale: true,
      });
      rsiSeries.setData(rsiData);

      // Overbought line (70)
      const overboughtData: LineData[] = [];
      const oversoldData: LineData[] = [];
      // Use the range where RSI has valid values
      for (let i = 0; i < sorted.length; i++) {
        if (rsiValues[i] !== null) {
          overboughtData.push({ time: times[i], value: 70 });
          oversoldData.push({ time: times[i], value: 30 });
        }
      }

      const overboughtSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.refLine,
        lineWidth: 1,
        lineStyle: 2, // dashed
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      overboughtSeries.setData(overboughtData);

      const oversoldSeries = chart.addSeries(LineSeries, {
        color: INDICATOR_COLORS.refLine,
        lineWidth: 1,
        lineStyle: 2, // dashed
        priceScaleId: "rsi",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      oversoldSeries.setData(oversoldData);
    }

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
      try {
        chart.remove();
      } catch {
        /* already disposed */
      }
      chartRef.current = null;
    };
  }, [data, height, showMA, currentIndicator, totalHeight, needsSubChart]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-muted-foreground"
        style={{ height }}
      >
        暂无K线数据
      </div>
    );
  }

  const LegendComponent = LEGEND_MAP[currentIndicator];

  return (
    <div>
      {/* Controls bar */}
      {onRangeChange && (
        <div className="flex flex-wrap gap-1 mb-3 overflow-x-auto items-center">
          {/* Time range buttons */}
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

          {/* Separator */}
          <div className="w-px h-5 bg-border mx-1 hidden sm:block" />

          {/* Indicator toggle buttons */}
          {INDICATOR_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={currentIndicator === opt.value ? "default" : "outline"}
              size="sm"
              className="text-xs h-7 px-2 whitespace-nowrap"
              onClick={() => handleIndicatorChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}

          {/* Legend */}
          <div className="ml-auto">
            <LegendComponent />
          </div>
        </div>
      )}

      {/* Chart without onRangeChange: just show indicator buttons */}
      {!onRangeChange && (
        <div className="flex flex-wrap gap-1 mb-3 overflow-x-auto items-center">
          {INDICATOR_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={currentIndicator === opt.value ? "default" : "outline"}
              size="sm"
              className="text-xs h-7 px-2 whitespace-nowrap"
              onClick={() => handleIndicatorChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
          <div className="ml-auto">
            <LegendComponent />
          </div>
        </div>
      )}

      <div ref={containerRef} />
    </div>
  );
}
