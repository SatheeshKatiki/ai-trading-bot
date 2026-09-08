"use client";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, TickMarkType, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode, createSeriesMarkers } from "lightweight-charts";
import { RefreshCw, Settings2, X, ChevronDown, Maximize2 as ResetZoomIcon, Download, Tag, Bot } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useChartSettingsStore } from "@/store/useChartSettingsStore";
import { parseBackendDatetimeToEpochSeconds, getISTNowParts, istWallTimeToEpochSeconds, isMarketOpenIST, formatEpochISTParts } from "@/lib/ist-time";

const SettingGroup = ({ title, active, onToggle, children }: { title: string, active: boolean, onToggle: () => void, children: React.ReactNode }) => (
  <div className="border border-border/50 rounded-lg overflow-hidden bg-background shadow-sm mb-3 transition-all duration-200">
    <div
      className={`px-4 py-3 flex items-center justify-between cursor-pointer transition-colors ${active ? 'bg-muted/40' : 'hover:bg-muted/30'}`}
      onClick={onToggle}
    >
      <span className="font-semibold text-[11px] tracking-wider uppercase text-foreground/80">{title}</span>
      <span className={`text-muted-foreground transition-transform duration-300 ${active ? 'rotate-180 text-primary' : ''}`}>
        <ChevronDown size={14} />
      </span>
    </div>
    {active && (
      <div className="px-4 py-3 border-t border-border/50 bg-muted/10 flex flex-col gap-3 animate-in fade-in slide-in-from-top-2 duration-200">
        {children}
      </div>
    )}
  </div>
);

// Simple EMA function
function calculateEMA(data: any[], period: number) {
  const p = Math.max(1, period || 1);
  const result = [];
  const multiplier = 2 / (p + 1);
  let prevEMA = 0;

  for (let i = 0; i < data.length; i++) {
    const close = data[i].close;
    if (i === 0) {
      prevEMA = close;
      result.push({ time: data[i].time, value: prevEMA });
    } else {
      const ema = (close - prevEMA) * multiplier + prevEMA;
      result.push({ time: data[i].time, value: isNaN(ema) ? close : ema });
      prevEMA = ema;
    }
  }
  return result;
}

// Bulletproof data sanitizer that guarantees strictly ascending Unix timestamps and no duplicates
function sanitizeCandleSeries(arr: any[]) {
  if (!arr || !Array.isArray(arr) || arr.length === 0) return [];
  const valid = arr
    .map((item: any) => {
      let t = item.time;
      if (typeof t !== 'number') {
        t = parseBackendDatetimeToEpochSeconds(String(item.datetime || item.Datetime || item.date || item.time));
      }
      return {
        ...item,
        time: t,
        open: Number(item.open ?? item.Open ?? 0),
        high: Number(item.high ?? item.High ?? 0),
        low: Number(item.low ?? item.Low ?? 0),
        close: Number(item.close ?? item.Close ?? 0),
        volume: Number(item.volume ?? item.Volume ?? 0)
      };
    })
    .filter((b: any) => b.time !== null && isFinite(b.time) && !isNaN(b.close))
    .sort((a: any, b: any) => Number(a.time) - Number(b.time));

  // Deduplicate and ensure STRICTLY increasing timestamps for Lightweight Charts
  const strictlyIncreasing: any[] = [];
  let prevTime = -Infinity;
  for (const c of valid) {
    const curTime = Number(c.time);
    if (curTime > prevTime) {
      strictlyIncreasing.push(c);
      prevTime = curTime;
    }
  }
  return strictlyIncreasing;
}

// Simple SMA function
function calculateSMA(data: any[], period: number = 20) {
  const p = Math.max(1, period || 20);
  const result: any[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < p - 1) {
      result.push({ time: data[i].time, value: data[i].close }); // fallback for early periods
      continue;
    }
    let sum = 0;
    for (let j = 0; j < p; j++) {
      sum += data[i - j].close;
    }
    const val = sum / p;
    result.push({ time: data[i].time, value: isNaN(val) ? data[i].close : val });
  }
  return result;
}

// Average Volume function
function calculateAverageVolume(data: any[], period: number) {
  const p = Math.max(1, period || 1);
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < p - 1) {
      result.push({ time: data[i].time, value: data[i].volume || 0 }); // fallback
      continue;
    }
    let sum = 0;
    for (let j = 0; j < p; j++) {
      sum += (data[i - j].volume || 0);
    }
    const val = sum / p;
    result.push({ time: data[i].time, value: isNaN(val) ? 0 : val });
  }
  return result;
}

// RSI Calculation
function calculateRSI(data: any[], period: number = 14) {
  const p = Math.max(1, period || 14);
  const result: any[] = [];
  if (data.length < p) return result;

  let gains = 0, losses = 0;
  for (let i = 1; i <= p; i++) {
    const diff = data[i].close - data[i - 1].close;
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  let avgGain = gains / p;
  let avgLoss = losses / p;

  // First RSI
  let rs = avgGain / (avgLoss === 0 ? 1 : avgLoss);
  let rsi = 100 - (100 / (1 + rs));
  result.push({ time: data[period].time, value: isNaN(rsi) ? 50 : rsi });

  for (let i = p + 1; i < data.length; i++) {
    const diff = data[i].close - data[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;

    avgGain = ((avgGain * (p - 1)) + gain) / p;
    avgLoss = ((avgLoss * (p - 1)) + loss) / p;

    rs = avgGain / (avgLoss === 0 ? 1 : avgLoss);
    rsi = 100 - (100 / (1 + rs));
    result.push({ time: data[i].time, value: isNaN(rsi) ? 50 : rsi });
  }
  return result;
}

// Volume-Weighted Average Price, resetting at each new IST trading day so
// intraday sessions don't carry cumulative volume/price over from the
// previous day. Returns the same running (cumPv, cumVol) state it ended on
// so live ticks can extend it incrementally instead of recomputing from
// the first candle of the day on every tick.
function calculateVWAP(data: any[]): { series: any[]; lastDayKey: string | null; cumPv: number; cumVol: number } {
  const series: any[] = [];
  let cumPv = 0, cumVol = 0, lastDayKey: string | null = null;

  for (const bar of data) {
    const p = formatEpochISTParts(bar.time as number);
    const dayKey = `${p.year}-${p.month}-${p.day}`;
    if (dayKey !== lastDayKey) {
      cumPv = 0;
      cumVol = 0;
      lastDayKey = dayKey;
    }
    const typicalPrice = (bar.high + bar.low + bar.close) / 3;
    const vol = bar.volume || 0;
    cumPv += typicalPrice * vol;
    cumVol += vol;
    const value = cumVol > 0 ? cumPv / cumVol : typicalPrice;
    series.push({ time: bar.time, value: isNaN(value) ? typicalPrice : value });
  }
  return { series, lastDayKey, cumPv, cumVol };
}

// Helper to check if Indian market is open
function isMarketOpen() {
  return isMarketOpenIST();
}

// Algorithmic Strategy Signal Generator matching EMA 9 / EMA 20 Momentum & RSI-MA Strategy Rules
function computeAutoSignalMarkers(candles: any[]): { markers: any[]; activeSignal: any } {
  if (!candles || candles.length < 25) return { markers: [], activeSignal: null };

  const markers: any[] = [];
  const ema9 = calculateEMA(candles, 9);
  const ema20 = calculateEMA(candles, 20);
  const rsi14 = calculateRSI(candles, 14);
  const rsiMa = calculateEMA(rsi14.map(r => ({ time: r.time, close: r.value })), 20);

  // Build lookup maps for fast indexed access
  const rsiMap = new Map<number, number>();
  rsi14.forEach(r => rsiMap.set(r.time as number, r.value));
  const rsiMaMap = new Map<number, number>();
  rsiMa.forEach(r => rsiMaMap.set(r.time as number, r.value));

  let position: 'NONE' | 'CALL' | 'PUT' = 'NONE';
  let entryPrice = 0;
  let highestPrice = 0;
  let lowestPrice = Infinity;
  let activeSignal: any = null;

  for (let i = 21; i < candles.length; i++) {
    const prev9 = ema9[i - 1]?.value;
    const prev20 = ema20[i - 1]?.value;
    const curr9 = ema9[i]?.value;
    const curr20 = ema20[i]?.value;
    const c = candles[i];
    const time = c.time as number;

    if (!c || c.close <= 0 || prev9 === undefined || prev20 === undefined || curr9 === undefined || curr20 === undefined) continue;

    const currRsi = rsiMap.get(time) ?? 50;
    const currRsiMa = rsiMaMap.get(time) ?? 50;

    // Time-of-day filter (09:25 to 15:00 IST)
    const p = formatEpochISTParts(time);
    const hhmm = `${p.hour}:${p.minute}`;
    const isTimeOk = hhmm >= "09:25" && hhmm <= "15:00";

    // EMA Touch & No-Chasing Guard (candle must be anchored near EMA cluster)
    const buffer = c.close * 0.0008; // ~19 pts buffer on NIFTY 24000
    const maxEma = Math.max(curr9, curr20);
    const minEma = Math.min(curr9, curr20);
    const touchCE = c.low <= (maxEma + buffer);
    const touchPE = c.high >= (minEma - buffer);

    // Exact Clean Edge Crossover Rules matching Python Engine
    const isBullishCross = (prev9 <= prev20 && curr9 > curr20) && (currRsi > currRsiMa) && touchCE && isTimeOk;
    const isBearishCross = (prev9 >= prev20 && curr9 < curr20) && (currRsi < currRsiMa) && touchPE && isTimeOk;

    if (position === 'NONE') {
      if (isBullishCross) {
        position = 'CALL';
        entryPrice = c.close;
        highestPrice = Math.max(c.high || c.close, c.close);
        markers.push({
          time: c.time,
          position: 'belowBar',
          color: '#10B981',
          shape: 'arrowUp',
          text: 'BUY CE',
          size: 2
        });
        activeSignal = { type: 'BUY CE', entry: entryPrice, time: c.time };
      } else if (isBearishCross) {
        position = 'PUT';
        entryPrice = c.close;
        lowestPrice = Math.min(c.low || c.close, c.close);
        markers.push({
          time: c.time,
          position: 'aboveBar',
          color: '#EF4444',
          shape: 'arrowDown',
          text: 'BUY PE',
          size: 2
        });
        activeSignal = { type: 'BUY PE', entry: entryPrice, time: c.time };
      }
    } else if (position === 'CALL') {
      highestPrice = Math.max(highestPrice, c.high || c.close);
      const peakGain = highestPrice - entryPrice;
      const giveback = peakGain > 0 ? (highestPrice - c.close) / peakGain : 0;

      // AI Exit Analyzer: Peak Giveback (>= 20% from +30pt peak) or SL or Opposite Crossover
      const isPeakLockExit = peakGain >= 30 && giveback >= 0.20;
      const isHardSlExit = (entryPrice - c.close) / entryPrice >= 0.006;
      const isReversalExit = prev9 >= prev20 && curr9 < curr20;

      if (isPeakLockExit || isHardSlExit || isReversalExit) {
        markers.push({
          time: c.time,
          position: 'aboveBar',
          color: '#F59E0B',
          shape: 'arrowDown',
          text: 'EXIT',
          size: 2
        });
        position = 'NONE';
        activeSignal = null;

        // If strong fresh bearish crossover, transition immediately to BUY PE
        if (isBearishCross) {
          position = 'PUT';
          entryPrice = c.close;
          lowestPrice = Math.min(c.low || c.close, c.close);
          markers.push({
            time: c.time,
            position: 'aboveBar',
            color: '#EF4444',
            shape: 'arrowDown',
            text: 'BUY PE',
            size: 2
          });
          activeSignal = { type: 'BUY PE', entry: entryPrice, time: c.time };
        }
      }
    } else if (position === 'PUT') {
      lowestPrice = Math.min(lowestPrice, c.low || c.close);
      const peakGain = entryPrice - lowestPrice;
      const giveback = peakGain > 0 ? (c.close - lowestPrice) / peakGain : 0;

      // AI Exit Analyzer: Peak Giveback (>= 20% from +30pt peak) or SL or Opposite Crossover
      const isPeakLockExit = peakGain >= 30 && giveback >= 0.20;
      const isHardSlExit = (c.close - entryPrice) / entryPrice >= 0.006;
      const isReversalExit = prev9 <= prev20 && curr9 > curr20;

      if (isPeakLockExit || isHardSlExit || isReversalExit) {
        markers.push({
          time: c.time,
          position: 'belowBar',
          color: '#F59E0B',
          shape: 'arrowUp',
          text: 'EXIT',
          size: 2
        });
        position = 'NONE';
        activeSignal = null;

        // If strong fresh bullish crossover, transition immediately to BUY CE
        if (isBullishCross) {
          position = 'CALL';
          entryPrice = c.close;
          highestPrice = Math.max(c.high || c.close, c.close);
          markers.push({
            time: c.time,
            position: 'belowBar',
            color: '#10B981',
            shape: 'arrowUp',
            text: 'BUY CE',
            size: 2
          });
          activeSignal = { type: 'BUY CE', entry: entryPrice, time: c.time };
        }
      }
    }
  }

  return { markers, activeSignal: position !== 'NONE' ? activeSignal : null };
}

export interface SignalLevels {
  entry?: number;
  sl?: number;
  target?: number;
  title?: string;
}

interface NativeChartProps {
  symbol: string;
  livePrice?: number;
  timeframe?: string;
  initialData?: any[];
  disableFetch?: boolean;
  showDynamicTrend?: boolean;
  lastTick?: number;
  markers?: any[];
  showAutoSignals?: boolean;
  signalLevels?: SignalLevels | null;
}

const Toggle = ({ checked, onChange, label }: { checked: boolean, onChange: (c: boolean) => void, label: string }) => (
  <div className="flex items-center justify-between py-2 cursor-pointer group" onClick={() => onChange(!checked)}>
    <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">{label}</span>
    <div className={`w-9 h-5 rounded-full relative transition-colors duration-200 ease-in-out shadow-inner ${checked ? 'bg-primary' : 'bg-muted-foreground/30'}`}>
      <span className={`absolute left-0.5 top-0.5 bg-background w-4 h-4 rounded-full shadow-sm transition-transform duration-200 ease-in-out ${checked ? 'translate-x-4' : 'translate-x-0'}`} />
    </div>
  </div>
);

const ColorSwatch = ({ color, onChange, label }: { color: string, onChange: (c: string) => void, label: string }) => (
  <div className="flex items-center justify-between py-2 group">
    <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors">{label}</span>
    <div className="relative w-6 h-6 rounded overflow-hidden border border-border/50 shadow-sm cursor-pointer hover:ring-2 hover:ring-primary/50 transition-all">
      <input type="color" value={color} onChange={(e) => onChange(e.target.value)} className="absolute -top-2 -left-2 w-10 h-10 cursor-pointer" />
    </div>
  </div>
);

// Global cache outside component to persist across unmounts
const chartDataCache: Record<string, any> = {};

export default function NativeChart({ symbol, livePrice, timeframe = "5 Min", initialData, disableFetch, lastTick = 0, markers, showAutoSignals = true, signalLevels }: NativeChartProps) {
  const { theme } = useTheme();

  const {
    ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
    ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
    showVolume, showRsi, rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
    showSmartTrend, bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor,
    showVwap, vwapColor, vwapLineWidth,

    setEma1Length, setEma1Color, setEma1LineWidth, setEma1LineStyle,
    setEma2Length, setEma2Color, setEma2LineWidth, setEma2LineStyle,
    setShowVolume, setShowRsi, setRsiLength, setRsiColor, setRsiLineWidth, setRsiLineStyle, setRsiOverbought, setRsiOversold,
    setShowSmartTrend, setBullishSurgeColor, setBearishSurgeColor, setBullishNormalColor, setBearishNormalColor, setChopColor,
    setShowVwap, setVwapColor
  } = useChartSettingsStore();

  const [showSettings, setShowSettings] = useState(false);
  const [activeTab, setActiveTab] = useState<'indicators' | 'smartTrend'>('indicators');
  const [activeAccordion, setActiveAccordion] = useState<string | null>('ema1');
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiObLineRef = useRef<any>(null);
  const rsiOsLineRef = useRef<any>(null);
  const vwapSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const entryPriceLineRef = useRef<any>(null);
  const slPriceLineRef = useRef<any>(null);
  const targetPriceLineRef = useRef<any>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<HTMLDivElement>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<string>("");
  const [lastCandleOpen, setLastCandleOpen] = useState<number | null>(null);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showAutoSignalsState, setShowAutoSignalsState] = useState(showAutoSignals ?? false);

  useEffect(() => {
    setShowAutoSignalsState(showAutoSignals ?? false);
  }, [showAutoSignals]);

  const lastCandleRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const seriesMarkersPluginRef = useRef<any>(null);
  const initialSettingsRef = useRef<any>(null);

  // Incremental indicator state -- seeded from a full recompute whenever
  // the underlying candle array changes (fetch/cache/settings), then
  // advanced in O(1) per live tick instead of re-scanning the whole
  // dataset on every single price update (previously recomputed EMA over
  // the entire candle history on every tick, and used hardcoded 9/21
  // periods there regardless of the user's configured EMA lengths).
  const lastEma1Ref = useRef<number | null>(null);
  const lastEma2Ref = useRef<number | null>(null);
  const vwapStateRef = useRef<{ dayKey: string | null; cumPv: number; cumVol: number }>({ dayKey: null, cumPv: 0, cumVol: 0 });

  // Re-seeds the incremental live-tick indicator state (EMA1/EMA2 last
  // value, VWAP running sums) from a fresh full-array computation. Called
  // whenever the underlying candle array changes (fetch/cache/settings);
  // live ticks then extend these in O(1) instead of re-scanning the whole
  // array on every single price update.
  const seedIncrementalState = (data: any[], ema1Data: any[], ema2Data: any[]) => {
    lastEma1Ref.current = ema1Data.length > 0 ? ema1Data[ema1Data.length - 1].value : null;
    lastEma2Ref.current = ema2Data.length > 0 ? ema2Data[ema2Data.length - 1].value : null;
    const vwap = calculateVWAP(data);
    vwapStateRef.current = { dayKey: vwap.lastDayKey, cumPv: vwap.cumPv, cumVol: vwap.cumVol };
    if (vwapSeriesRef.current) vwapSeriesRef.current.setData(vwap.series);
  };

  const handleOpenSettings = () => {
    initialSettingsRef.current = {
      ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
      ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
      showVolume, showRsi, rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
      showSmartTrend, bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor,
      showVwap, vwapColor
    };
    setShowSettings(true);
  };

  const handleCancelSettings = () => {
    if (initialSettingsRef.current) {
      const s = initialSettingsRef.current;
      setEma1Length(s.ema1Length); setEma1Color(s.ema1Color); setEma1LineWidth(s.ema1LineWidth); setEma1LineStyle(s.ema1LineStyle);
      setEma2Length(s.ema2Length); setEma2Color(s.ema2Color); setEma2LineWidth(s.ema2LineWidth); setEma2LineStyle(s.ema2LineStyle);
      setShowVolume(s.showVolume);
      setShowRsi(s.showRsi); setRsiLength(s.rsiLength); setRsiColor(s.rsiColor); setRsiLineWidth(s.rsiLineWidth); setRsiLineStyle(s.rsiLineStyle); setRsiOverbought(s.rsiOverbought); setRsiOversold(s.rsiOversold);
      setShowSmartTrend(s.showSmartTrend);
      setBullishSurgeColor(s.bullishSurgeColor); setBearishSurgeColor(s.bearishSurgeColor);
      setBullishNormalColor(s.bullishNormalColor); setBearishNormalColor(s.bearishNormalColor);
      setChopColor(s.chopColor);
      setShowVwap(s.showVwap); setVwapColor(s.vwapColor);
    }
    setShowSettings(false);
  };

  // 1. INITIALIZE CHART ONLY ONCE
  useEffect(() => {
    let minutes = 5;
    if (timeframe.toLowerCase().includes("hour")) {
      const tfMatch = timeframe.match(/(\d+)/);
      minutes = tfMatch ? parseInt(tfMatch[1], 10) * 60 : 60;
    } else if (timeframe.toLowerCase().includes("min")) {
      const tfMatch = timeframe.match(/(\d+)/);
      minutes = tfMatch ? parseInt(tfMatch[1], 10) : 5;
    } else {
      setCountdown("");
      return;
    }

    const intervalId = setInterval(() => {
      const now = new Date();
      const currentMinutes = now.getMinutes();
      const currentSeconds = now.getSeconds();

      let minutesToNext = minutes - (currentMinutes % minutes) - 1;
      let secondsToNext = 60 - currentSeconds;

      if (secondsToNext === 60) {
        minutesToNext += 1;
        secondsToNext = 0;
      }

      const mm = String(minutesToNext).padStart(2, '0');
      const ss = String(secondsToNext).padStart(2, '0');

      setCountdown(`${mm}:${ss}`);
    }, 1000);

    return () => clearInterval(intervalId);
  }, [timeframe]);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const isDark = theme !== "light"; // default to dark if undefined

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: isDark ? "#9CA3AF" : "#6B7280" },
      grid: { vertLines: { color: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.05)" }, horzLines: { color: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.05)" } },
      // Root-cause fix (chart timestamp audit): lightweight-charts has no
      // built-in per-chart timezone setting -- by default it formats the
      // epochs it's given using JS Date's *UTC* getters, which (since every
      // `time` value here is a true, timezone-independent Unix epoch) would
      // display UTC wall-clock time, i.e. IST minus 5:30, to any viewer.
      // Explicit localization/tickMarkFormatter force every axis label and
      // crosshair time to real IST (Asia/Kolkata) regardless of the
      // viewer's own browser/system timezone.
      localization: {
        timeFormatter: (time: Time) => {
          const p = formatEpochISTParts(time as number);
          return `${p.day} ${p.month} ${p.year}  ${p.hour}:${p.minute}`;
        },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)",
        rightOffset: 15,
        barSpacing: 8,
        minBarSpacing: 0.2,
        fixLeftEdge: false,
        fixRightEdge: false,
        tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) => {
          const p = formatEpochISTParts(time as number);
          switch (tickMarkType) {
            case TickMarkType.Year: return p.year;
            case TickMarkType.Month: return `${p.month} '${p.year.slice(-2)}`;
            case TickMarkType.DayOfMonth: return `${p.day} ${p.month}`;
            default: return `${p.hour}:${p.minute}`;
          }
        },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true
      },
      handleScale: {
        axisPressedMouseMove: { time: true, price: true },
        mouseWheel: true,
        pinch: true
      },
      rightPriceScale: { borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)", autoScale: true },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: isDark ? "rgba(255, 255, 255, 0.2)" : "rgba(0, 0, 0, 0.2)", style: 3, labelBackgroundColor: isDark ? "#1E293B" : "#475569" },
        horzLine: { color: isDark ? "rgba(255, 255, 255, 0.2)" : "rgba(0, 0, 0, 0.2)", style: 3, labelBackgroundColor: isDark ? "#1E293B" : "#475569" },
      },
    });

    // Volume Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      visible: showVolume
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    // RSI Series
    const rsiSeries = chart.addSeries(LineSeries, {
      color: rsiColor,
      lineWidth: rsiLineWidth as any,
      lineStyle: rsiLineStyle as any,
      priceScaleId: 'rsi',
      visible: showRsi
    });
    chart.priceScale('rsi').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    rsiObLineRef.current = rsiSeries.createPriceLine({
      price: rsiOverbought,
      color: 'rgba(239, 68, 68, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'OB',
    });

    rsiOsLineRef.current = rsiSeries.createPriceLine({
      price: rsiOversold,
      color: 'rgba(16, 185, 129, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'OS',
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981", downColor: "#EF4444", borderVisible: false,
      wickUpColor: "#10B981", wickDownColor: "#EF4444",
    });

    const seriesMarkers = createSeriesMarkers(candleSeries);
    seriesMarkersPluginRef.current = seriesMarkers;

    const emaSeries = chart.addSeries(LineSeries, { color: ema1Color, lineWidth: ema1LineWidth as any, lineStyle: ema1LineStyle as any, crosshairMarkerVisible: false, priceLineVisible: false });
    const ema21Series = chart.addSeries(LineSeries, { color: ema2Color, lineWidth: ema2LineWidth as any, lineStyle: ema2LineStyle as any, crosshairMarkerVisible: false, priceLineVisible: false });
    const vwapSeries = chart.addSeries(LineSeries, {
      color: vwapColor, lineWidth: vwapLineWidth as any, lineStyle: 2 as any,
      crosshairMarkerVisible: false, priceLineVisible: false, visible: showVwap,
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    emaSeriesRef.current = emaSeries;
    smaSeriesRef.current = ema21Series;
    volumeSeriesRef.current = volumeSeries;
    rsiSeriesRef.current = rsiSeries;
    vwapSeriesRef.current = vwapSeries;

    chart.subscribeCrosshairMove((param) => {
      if (!tooltipRef.current || !chartContainerRef.current) return;
      if (param.point === undefined || !param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
        tooltipRef.current.style.display = "none";
        return;
      }
      const data = param.seriesData.get(candleSeries) as any;
      const volData = param.seriesData.get(volumeSeries) as any;

      if (data) {
        tooltipRef.current.style.display = "block";
        const volumeStr = volData && volData.value ? (volData.value >= 1000000 ? (volData.value / 1000000).toFixed(2) + 'M' : (volData.value / 1000).toFixed(2) + 'K') : '---';

        tooltipRef.current.innerHTML = `
          <div class="flex items-center gap-3">
            <span class="text-muted-foreground">O<span class="text-foreground ml-1 font-bold">${data.open.toFixed(2)}</span></span>
            <span class="text-muted-foreground">H<span class="text-success ml-1 font-bold">${data.high.toFixed(2)}</span></span>
            <span class="text-muted-foreground">L<span class="text-destructive ml-1 font-bold">${data.low.toFixed(2)}</span></span>
            <span class="text-muted-foreground">C<span class="text-foreground ml-1 font-bold">${data.close.toFixed(2)}</span></span>
            ${volData && volData.value ? `<span class="ml-2 flex items-center gap-1 px-1.5 py-0.5 rounded backdrop-blur-md bg-blue-500/10 border border-blue-500/20"><span class="text-[9px] uppercase tracking-wider text-blue-400">Vol</span><span class="text-blue-500 font-bold">${volumeStr}</span></span>` : ''}
          </div>
        `;
      }
    });

    // Dynamic Resize using ResizeObserver
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || entries[0].target !== chartContainerRef.current) return;
      const newRect = entries[0].contentRect;
      if (chartRef.current) {
        chart.applyOptions({ width: newRect.width, height: newRect.height });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    // Sync countdown position to price line dynamically.
    // Performance fix: this previously ran an uninterruptible RAF loop for
    // the entire component lifetime, burning a CPU/GPU frame 60x/sec even
    // while the browser tab was in the background or no countdown badge
    // was even showing. Now it stops scheduling frames whenever the tab is
    // hidden (Page Visibility API) and resumes exactly where it left off
    // when it becomes visible again -- the on-screen behavior while
    // visible is unchanged.
    let animationFrameId: number | null = null;
    const syncCountdownPosition = () => {
      if (countdownRef.current && seriesRef.current && lastCandleRef.current) {
        const y = seriesRef.current.priceToCoordinate(lastCandleRef.current.close);
        if (y !== null) {
          countdownRef.current.style.top = `${y + 12}px`;
        }
      }
      animationFrameId = requestAnimationFrame(syncCountdownPosition);
    };
    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (animationFrameId !== null) cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
      } else if (animationFrameId === null) {
        syncCountdownPosition();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    if (!document.hidden) syncCountdownPosition();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (animationFrameId !== null) cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      seriesMarkersPluginRef.current = null;
      emaSeriesRef.current = null;
      smaSeriesRef.current = null;
      volumeSeriesRef.current = null;
      rsiSeriesRef.current = null;
      vwapSeriesRef.current = null;
    };
  }, []); // Run only ONCE on mount

  // Update chart theme dynamically when theme changes
  useEffect(() => {
    if (!chartRef.current) return;
    const isDark = theme !== "light";
    chartRef.current.applyOptions({
      layout: { textColor: isDark ? "#9CA3AF" : "#6B7280" },
      grid: { vertLines: { color: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.05)" }, horzLines: { color: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.05)" } },
      timeScale: { borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)" },
      rightPriceScale: { borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)" },
      crosshair: {
        vertLine: { color: isDark ? "rgba(255, 255, 255, 0.2)" : "rgba(0, 0, 0, 0.2)", labelBackgroundColor: isDark ? "#1E293B" : "#475569" },
        horzLine: { color: isDark ? "rgba(255, 255, 255, 0.2)" : "rgba(0, 0, 0, 0.2)", labelBackgroundColor: isDark ? "#1E293B" : "#475569" },
      },
    });
  }, [theme]);

  // 2. FETCH DATA WHEN SYMBOL/TIMEFRAME CHANGES
  useEffect(() => {
    let isMounted = true;
    if (!chartRef.current || !seriesRef.current || !emaSeriesRef.current || !smaSeriesRef.current) return;

    const candleSeries = seriesRef.current;
    const emaSeries = emaSeriesRef.current;
    const smaSeries = smaSeriesRef.current;
    const chart = chartRef.current;

    const fetchMarkersAndLines = async (chartData: any[], cSeries: ISeriesApi<"Candlestick">) => {
      try {
        let finalMarkers: any[] = [];

        if (markers && markers.length > 0) {
          finalMarkers = [...markers];
        } else {
          // 1. Fetch real executed trade markers from backend state
          try {
            const stateRes = await fetch(`/api/state`);
            if (stateRes.ok) {
              const stateData = await stateRes.json();
              if (stateData.trades && stateData.trades.length > 0) {
                const symClean = symbol.split(':')[1] || symbol;
                const symbolTrades = stateData.trades.filter((t: any) => {
                  if (!t.symbol) return false;
                  const tSym = t.symbol.toUpperCase();
                  return tSym.includes(symClean.toUpperCase()) || (symClean.toUpperCase().includes('NIFTY') && tSym.includes('NIFTY'));
                });

                symbolTrades.forEach((trade: any) => {
                  const dateStr = String(trade.entry_time || trade.time);
                  if (!dateStr || dateStr === "undefined" || dateStr === "null") return;
                  const adjustedTime = parseBackendDatetimeToEpochSeconds(dateStr);
                  if (adjustedTime === null) return;

                  let closestTime = adjustedTime as Time;
                  let minDiff = Infinity;
                  for (const candle of chartData) {
                    const diff = Math.abs((candle.time as number) - (adjustedTime as number));
                    if (diff < minDiff) { minDiff = diff; closestTime = candle.time; }
                  }

                  const isPut = trade.type?.includes('PUT') || trade.symbol?.toUpperCase().includes('PE');
                  const isExit = trade.side === 'SELL' || trade.type?.includes('SELL');

                  if (isExit) {
                    finalMarkers.push({
                      time: closestTime,
                      position: 'aboveBar',
                      color: '#F59E0B',
                      shape: 'arrowDown',
                      text: 'EXIT',
                      size: 2
                    });
                  } else if (isPut) {
                    finalMarkers.push({
                      time: closestTime,
                      position: 'aboveBar',
                      color: '#EF4444',
                      shape: 'arrowDown',
                      text: 'BUY PE',
                      size: 2
                    });
                  } else {
                    finalMarkers.push({
                      time: closestTime,
                      position: 'belowBar',
                      color: '#10B981',
                      shape: 'arrowUp',
                      text: 'BUY CE',
                      size: 2
                    });
                  }

                  // Also add exit marker if exit_time exists
                  if (trade.exit_time) {
                    const exitEpoch = parseBackendDatetimeToEpochSeconds(String(trade.exit_time));
                    if (exitEpoch !== null) {
                      let closestExitTime = exitEpoch as Time;
                      let minExitDiff = Infinity;
                      for (const candle of chartData) {
                        const diff = Math.abs((candle.time as number) - (exitEpoch as number));
                        if (diff < minExitDiff) { minExitDiff = diff; closestExitTime = candle.time; }
                      }
                      finalMarkers.push({
                        time: closestExitTime,
                        position: 'aboveBar',
                        color: '#F59E0B',
                        shape: 'arrowDown',
                        text: 'EXIT',
                        size: 2
                      });
                    }
                  }
                });
              }
            }
          } catch { }

          // 2. Compute algorithmic strategy signals across candles if showAutoSignals is enabled
          if (showAutoSignals && chartData.length > 20) {
            const autoSig = computeAutoSignalMarkers(chartData);
            if (finalMarkers.length === 0) {
              finalMarkers = [...autoSig.markers];
            } else {
              // Merge auto signals with executed trades
              autoSig.markers.forEach(am => finalMarkers.push(am));
            }
          }
        }

        // Prioritize and collapse to 1 clean marker per candle timestamp
        const markerMap = new Map<number, any>();

        finalMarkers.forEach(m => {
          const t = m.time as number;
          const existing = markerMap.get(t);
          if (!existing) {
            markerMap.set(t, m);
          } else {
            // New Entry (BUY CE / BUY PE) takes priority over EXIT on the same reversal candle
            if ((m.text === 'BUY CE' || m.text === 'BUY PE') && existing.text === 'EXIT') {
              markerMap.set(t, m);
            }
          }
        });

        const uniqueMarkers = Array.from(markerMap.values()).sort((a, b) => (a.time as number) - (b.time as number));

        if (!isMounted) return;
        markersRef.current = uniqueMarkers;
        if (showMarkers && seriesMarkersPluginRef.current) {
          seriesMarkersPluginRef.current.setMarkers(uniqueMarkers);
        }
      } catch (e: any) {
        console.warn("Error fetching markers:", e.message);
      }
    };

    const fetchHistory = async () => {
      if (disableFetch && initialData) {
        // Root-cause fix: callers (e.g. the backtest page) pass through
        // whatever the backend sent verbatim, which for `/api/backtest` is
        // a raw "yyyy-mm-dd HH:MM:SS" string (`str(row['datetime'])`
        // server-side), not the Unix-epoch-seconds every other `time` value
        // in this component is. Passing that string straight to
        // `setData()` crashes lightweight-charts' business-day parser. Every
        // other data path here funnels through `parseBackendDatetimeToEpochSeconds`
        // first -- do the same here instead of trusting the caller's shape.
        const normalizedInitialData = sanitizeCandleSeries(initialData);

        const ema1Data = calculateEMA(normalizedInitialData, ema1Length);
        const ema2Data = calculateSMA(normalizedInitialData, ema2Length);
        candleSeries.setData(normalizedInitialData);
        emaSeries.setData(ema1Data);
        smaSeries.setData(ema2Data);
        seedIncrementalState(normalizedInitialData, ema1Data, ema2Data);
        if (normalizedInitialData.length > 0) {
          lastCandleRef.current = normalizedInitialData[normalizedInitialData.length - 1];
          chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, normalizedInitialData.length - 150), to: normalizedInitialData.length });
        } else {
          chart.timeScale().fitContent();
        }
        setLoading(false);
        return;
      }

      const cacheKey = `${symbol}_${timeframe}`;

      if (chartDataCache[cacheKey]) {
        const cached = sanitizeCandleSeries(chartDataCache[cacheKey]);
        if (!isMounted) return;

        const ema1Data = calculateEMA(cached, ema1Length);
        const ema2Data = calculateSMA(cached, ema2Length);

        candleSeries.setData(cached);
        emaSeries.setData(ema1Data);
        smaSeries.setData(ema2Data);
        seedIncrementalState(cached, ema1Data, ema2Data);
        lastCandleRef.current = cached[cached.length - 1];
        chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, cached.length - 150), to: cached.length });
        setLoading(false); // Instant load!
        fetchMarkersAndLines(cached, candleSeries);
      } else {
        setLoading(true);
      }

      try {
        setError(null);
        const endDate = new Date();
        const startDate = new Date();
        if (timeframe.includes("Month")) startDate.setFullYear(endDate.getFullYear() - 10);
        else if (timeframe.includes("Week")) startDate.setFullYear(endDate.getFullYear() - 5);
        else if (timeframe.includes("Day")) startDate.setFullYear(endDate.getFullYear() - 1);
        else if (timeframe.includes("Hour") || timeframe.includes("30 Min") || timeframe.includes("15 Min")) startDate.setDate(endDate.getDate() - 30);
        else startDate.setDate(endDate.getDate() - 60);

        const sDateStr = startDate.toISOString().split("T")[0];
        const eDateStr = endDate.toISOString().split("T")[0];

        // Use Next.js Proxy
        const url = `/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${sDateStr}&end_date=${eDateStr}&timeframe=${encodeURIComponent(timeframe)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch historical data.");
        const json = await res.json();
        if (!isMounted) return;

        if (!json.data || !Array.isArray(json.data) || json.data.length === 0) {
          if (!chartDataCache[cacheKey]) {
            setError(`No data available for ${timeframe}.`);
            setLoading(false);
          }
          return;
        }

        const uniqueData = sanitizeCandleSeries(json.data);

        if (uniqueData.length > 0) {
          const prevLen = (chartDataCache[cacheKey] || []).length;
          chartDataCache[cacheKey] = uniqueData; // Cache it!
          if (!isMounted) return;
          // Apply dynamic colors if enabled
          let dataToSet = uniqueData;
          const ema1Data = calculateEMA(uniqueData, ema1Length);
          const ema2Data = calculateSMA(uniqueData, ema2Length);
          const rsiData = calculateRSI(uniqueData, rsiLength);
          const avgVol20 = calculateAverageVolume(uniqueData, 20);

          if (showSmartTrend) {
            dataToSet = uniqueData.map((d: any, index: number) => {
              const ema1 = ema1Data[index]?.value;
              const ema2 = ema2Data[index]?.value;
              const avgVol = avgVol20[index]?.value;
              if (!ema1 || !ema2) return d;

              const isChop = Math.abs(ema1 - ema2) / ema2 < 0.0005; // 0.05% difference threshold for chop
              const isHighVolume = d.volume && avgVol && d.volume > avgVol * 2.0; // 2x average volume

              let customColor;
              if (isChop) {
                customColor = chopColor;
              } else if (isHighVolume && d.close > ema1) {
                customColor = bullishSurgeColor;
              } else if (isHighVolume && d.close < ema1) {
                customColor = bearishSurgeColor;
              } else if (d.close >= ema1) {
                customColor = d.close >= d.open ? bullishNormalColor : "#059669";
              } else {
                customColor = d.close < d.open ? bearishNormalColor : "#991B1B";
              }
              return { ...d, color: customColor, wickColor: customColor, borderColor: customColor };
            });
          }

          candleSeries.setData(dataToSet);
          emaSeries.setData(ema1Data);
          smaSeries.setData(ema2Data);
          if (rsiSeriesRef.current) rsiSeriesRef.current.setData(rsiData);
          seedIncrementalState(uniqueData, ema1Data, ema2Data);

          if (volumeSeriesRef.current) {
            const volumeData = uniqueData.map((d: any) => ({
              time: d.time,
              value: d.volume,
              color: d.close >= d.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)'
            }));
            volumeSeriesRef.current.setData(volumeData);
          }

          if (uniqueData.length > 0) {
            setLastCandleOpen(uniqueData[uniqueData.length - 1].open);
            lastCandleRef.current = uniqueData[uniqueData.length - 1];
            if (prevLen === 0 || uniqueData.length > prevLen) {
              chart.priceScale('right').applyOptions({ autoScale: true });
              chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, uniqueData.length - 150), to: uniqueData.length });
            }
          } else {
            chart.timeScale().fitContent();
          }
          fetchMarkersAndLines(uniqueData, candleSeries);
        }
        if (isMounted) setLoading(false);
      } catch (err: any) {
        console.warn("Chart data fetch failed (Backend offline?):", err.message);
        if (isMounted && !chartDataCache[cacheKey]) {
          setError(err.message || "Could not load chart data");
          setLoading(false);
        }
      }
    };

    fetchHistory();

    // Auto-poll history every 15s during live trading so new closed candles are automatically appended
    const pollInterval = !disableFetch ? setInterval(() => {
      if (typeof document !== 'undefined' && !document.hidden && chartRef.current) {
        fetchHistory();
      }
    }, 15000) : null;

    return () => {
      isMounted = false;
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [symbol, timeframe, showAutoSignals]);
  // We removed showSmartTrend here because we have a dedicated hook now

  // 2a. Synchronize Active Signal Price Lines (Entry, SL, Target)
  useEffect(() => {
    if (!seriesRef.current) return;
    const candleSeries = seriesRef.current;

    // Clear old price lines
    if (entryPriceLineRef.current) {
      try { candleSeries.removePriceLine(entryPriceLineRef.current); } catch { }
      entryPriceLineRef.current = null;
    }
    if (slPriceLineRef.current) {
      try { candleSeries.removePriceLine(slPriceLineRef.current); } catch { }
      slPriceLineRef.current = null;
    }
    if (targetPriceLineRef.current) {
      try { candleSeries.removePriceLine(targetPriceLineRef.current); } catch { }
      targetPriceLineRef.current = null;
    }

    if (!showAutoSignals || !signalLevels) return;

    if (signalLevels.entry && signalLevels.entry > 0) {
      try {
        entryPriceLineRef.current = candleSeries.createPriceLine({
          price: signalLevels.entry,
          color: '#10B981',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `BUY ENTRY ₹${signalLevels.entry.toFixed(1)}`,
        });
      } catch { }
    }

    if (signalLevels.sl && signalLevels.sl > 0) {
      try {
        slPriceLineRef.current = candleSeries.createPriceLine({
          price: signalLevels.sl,
          color: '#EF4444',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `STOP LOSS ₹${signalLevels.sl.toFixed(1)}`,
        });
      } catch { }
    }

    if (signalLevels.target && signalLevels.target > 0) {
      try {
        targetPriceLineRef.current = candleSeries.createPriceLine({
          price: signalLevels.target,
          color: '#8B5CF6',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `TARGET ₹${signalLevels.target.toFixed(1)}`,
        });
      } catch { }
    }
  }, [signalLevels, showAutoSignals]);

  // 2b. Handle Chart Settings Changes Dynamically (No refetch)
  useEffect(() => {
    const cacheKey = `${symbol}_${timeframe}`;
    const cachedData = sanitizeCandleSeries(chartDataCache[cacheKey]);

    if (cachedData && cachedData.length > 0 && seriesRef.current) {
      // 1. Update visibility and styles
      if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ visible: showVolume });
      if (rsiSeriesRef.current) rsiSeriesRef.current.applyOptions({ visible: showRsi, color: rsiColor, lineWidth: rsiLineWidth as any, lineStyle: rsiLineStyle as any });
      if (emaSeriesRef.current) emaSeriesRef.current.applyOptions({ color: ema1Color, lineWidth: ema1LineWidth as any, lineStyle: ema1LineStyle as any });
      if (smaSeriesRef.current) smaSeriesRef.current.applyOptions({ color: ema2Color, lineWidth: ema2LineWidth as any, lineStyle: ema2LineStyle as any });

      if (rsiObLineRef.current) rsiObLineRef.current.applyOptions({ price: rsiOverbought });
      if (rsiOsLineRef.current) rsiOsLineRef.current.applyOptions({ price: rsiOversold });
      if (vwapSeriesRef.current) vwapSeriesRef.current.applyOptions({ visible: showVwap, color: vwapColor, lineWidth: vwapLineWidth as any });

      // 2. Recalculate indicators
      const ema1Data = calculateEMA(cachedData, ema1Length);
      const ema2Data = calculateSMA(cachedData, ema2Length);
      const rsiData = calculateRSI(cachedData, rsiLength);

      // 3. Re-apply Smart Trend colors
      let dataToSet = cachedData;
      if (showSmartTrend) {
        const avgVol20 = calculateAverageVolume(cachedData, 20);
        dataToSet = cachedData.map((d: any, index: number) => {
          const ema1 = ema1Data[index]?.value;
          const ema2 = ema2Data[index]?.value;
          const avgVol = avgVol20[index]?.value;
          if (!ema1 || !ema2) return d;

          const isChop = Math.abs(ema1 - ema2) / ema2 < 0.0005;
          const isHighVolume = d.volume && avgVol && d.volume > avgVol * 2.0;

          let customColor;
          if (isChop) {
            customColor = chopColor;
          } else if (isHighVolume && d.close > ema1) {
            customColor = bullishSurgeColor;
          } else if (isHighVolume && d.close < ema1) {
            customColor = bearishSurgeColor;
          } else if (d.close >= ema1) {
            customColor = d.close >= d.open ? bullishNormalColor : "#059669";
          } else {
            customColor = d.close < d.open ? bearishNormalColor : "#991B1B";
          }
          return { ...d, color: customColor, wickColor: customColor, borderColor: customColor };
        });
      } else {
        // Reset colors if disabled
        dataToSet = cachedData.map((d: any) => ({ ...d, color: undefined, wickColor: undefined, borderColor: undefined }));
      }

      // 4. Update Series Data
      seriesRef.current.setData(dataToSet);
      if (emaSeriesRef.current) emaSeriesRef.current.setData(ema1Data);
      if (smaSeriesRef.current) smaSeriesRef.current.setData(ema2Data);
      if (rsiSeriesRef.current) rsiSeriesRef.current.setData(rsiData);
      seedIncrementalState(cachedData, ema1Data, ema2Data);

      // Update the last candle ref so live ticks don't revert colors immediately
      lastCandleRef.current = dataToSet[dataToSet.length - 1];
    }
  }, [
    ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
    ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
    rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
    showVolume, showRsi, showSmartTrend,
    bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor,
    showVwap, vwapColor, vwapLineWidth,
    symbol, timeframe
  ]);

  // 2c. Handle Marker Toggle without refetching
  useEffect(() => {
    if (seriesMarkersPluginRef.current) {
      if (!showAutoSignalsState || !showMarkers) {
        try {
          seriesMarkersPluginRef.current.setMarkers([]);
        } catch { }
      } else {
        try {
          seriesMarkersPluginRef.current.setMarkers(markersRef.current || []);
        } catch { }
      }
    }
  }, [showAutoSignalsState, showMarkers]);

  // 2d. Render External Strategy Markers (BUY CE / BUY PE / EXIT arrows)
  useEffect(() => {
    if (seriesMarkersPluginRef.current && markers && Array.isArray(markers)) {
      try {
        const formatted = markers.map((m: any) => {
          let timeVal = m.time;
          if (typeof timeVal === 'string') {
            const parsed = parseBackendDatetimeToEpochSeconds(timeVal);
            if (parsed !== null) timeVal = parsed as Time;
          }
          const isPut = m.type?.includes('PUT') || m.symbol?.toUpperCase().includes('PE') || m.text?.includes('PE');
          const isExit = m.type === 'EXIT' || m.type === 'SELL' || m.side === 'SELL' || m.text?.includes('EXIT');

          let label = 'BUY CE';
          let color = '#10B981';
          let shape = 'arrowUp';
          let position = 'belowBar';

          if (isExit) {
            label = 'EXIT';
            color = '#F59E0B';
            shape = 'arrowDown';
            position = 'aboveBar';
          } else if (isPut) {
            label = 'BUY PE';
            color = '#EF4444';
            shape = 'arrowDown';
            position = 'aboveBar';
          }

          return {
            time: timeVal,
            position: m.position || position,
            color: m.color || color,
            shape: m.shape || shape,
            text: m.text || label,
            size: 2
          };
        }).sort((a: any, b: any) => (a.time as number) - (b.time as number));

        seriesMarkersPluginRef.current.setMarkers(formatted);
      } catch (err) {
        console.warn("Failed to set markers on seriesMarkersPlugin:", err);
      }
    }
  }, [markers]);

  // 3. Handle live price updates and auto-generate new candles
  useEffect(() => {
    if (!isMarketOpen()) return;

    if (livePrice && livePrice > 0 && seriesRef.current && lastCandleRef.current) {
      const lastCandle = lastCandleRef.current;

      // Root-cause fix (chart timestamp audit): this used to read
      // `new Date().getHours()/getMinutes()`, i.e. the VIEWER's own
      // browser/system local time -- correct only by accident for a viewer
      // whose machine happens to be set to IST. Candle-interval alignment
      // must always be computed against real IST/NSE market time.
      const istNow = getISTNowParts();

      // Calculate exact candle start time aligned to Indian Market Open (09:15)
      const tfVal = parseInt(timeframe.split(' ')[0] || "5");
      let currentCandleTime: number;

      if (timeframe.includes("Day")) {
        currentCandleTime = istWallTimeToEpochSeconds(istNow.year, istNow.month, istNow.day, 0, 0, 0);
      } else {
        const minutesSinceMidnight = istNow.hour * 60 + istNow.minute;
        const minutesSinceOpen = minutesSinceMidnight - (9 * 60 + 15);
        // Cap to 370 mins (15:25 PM IST) so post-market ticks do not generate candles after 3:30 PM
        const effectiveMins = Math.min(370, Math.max(0, minutesSinceOpen));

        let roundedMins = 0;
        if (timeframe.includes("Hour")) {
          roundedMins = Math.floor(effectiveMins / 60) * 60;
        } else {
          roundedMins = Math.floor(effectiveMins / tfVal) * tfVal;
        }

        const totalMinsFromMidnight = 9 * 60 + 15 + roundedMins;
        const candleHour = Math.floor(totalMinsFromMidnight / 60);
        const candleMinute = totalMinsFromMidnight % 60;
        currentCandleTime = istWallTimeToEpochSeconds(istNow.year, istNow.month, istNow.day, candleHour, candleMinute, 0);
      }

      let updatedCandle;

      if (currentCandleTime > (lastCandle.time as number)) {
        // Dynamic live candle color
        let liveColor = undefined;
        if (showSmartTrend && chartDataCache[`${symbol}_${timeframe}`]) {
          const cache = chartDataCache[`${symbol}_${timeframe}`];
          if (cache.length > 0) {
            const ema1 = calculateEMA(cache, ema1Length).pop()?.value;
            const ema2 = calculateSMA(cache, ema2Length).pop()?.value;
            // Note: Volume surge for live candle is hard to calculate accurately before it closes, 
            // so we rely mostly on trend and chop logic for the live ticking candle.
            if (ema1 && ema2) {
              const isChop = Math.abs(ema1 - ema2) / ema2 < 0.0005;
              if (isChop) {
                liveColor = chopColor;
              } else if (livePrice >= ema1) {
                liveColor = livePrice >= lastCandle.open ? bullishNormalColor : "#059669";
              } else {
                liveColor = livePrice < lastCandle.open ? bearishNormalColor : "#991B1B";
              }
            }
          }
        }

        updatedCandle = {
          time: currentCandleTime as Time,
          open: livePrice,
          high: livePrice,
          low: livePrice,
          close: livePrice,
          volume: 0,
          ...(liveColor ? { color: liveColor, wickColor: liveColor, borderColor: liveColor } : {})
        };
      } else {
        // Update the existing candle
        let liveColor = undefined;
        if (showSmartTrend && chartDataCache[`${symbol}_${timeframe}`]) {
          const cache = chartDataCache[`${symbol}_${timeframe}`];
          if (cache.length > 0) {
            const ema1 = calculateEMA(cache, ema1Length).pop()?.value;
            const ema2 = calculateSMA(cache, ema2Length).pop()?.value;
            if (ema1 && ema2) {
              const isChop = Math.abs(ema1 - ema2) / ema2 < 0.0005;
              if (isChop) {
                liveColor = chopColor;
              } else if (livePrice >= ema1) {
                liveColor = livePrice >= lastCandle.open ? bullishNormalColor : "#059669";
              } else {
                liveColor = livePrice < lastCandle.open ? bearishNormalColor : "#991B1B";
              }
            }
          }
        }

        updatedCandle = {
          ...lastCandle,
          close: livePrice,
          high: Math.max(lastCandle.high, livePrice),
          low: Math.min(lastCandle.low, livePrice),
          ...(liveColor ? { color: liveColor, wickColor: liveColor, borderColor: liveColor } : {})
        };
      }

      // CRITICAL FIX: Save the updated candle so wicks don't disappear on next tick!
      lastCandleRef.current = updatedCandle;
      setLastCandleOpen(updatedCandle.open);

      seriesRef.current.update(updatedCandle);
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.update({
          time: updatedCandle.time,
          value: updatedCandle.volume || 0,
          color: updatedCandle.close >= updatedCandle.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)'
        });
      }

      // Update indicators incrementally instead of recomputing over the
      // entire candle history on every single tick (previously O(n) per
      // tick via calculateEMA(cached, ...) on the whole array). Also fixes
      // a pre-existing bug: this path hardcoded periods 9/21 regardless of
      // the user's configured ema1Length/ema2Length, and used the EMA
      // formula for series 2 even though the historical/settings paths
      // compute it as a simple moving average (calculateSMA) -- both
      // series would silently jump to a different formula/period the
      // instant a live tick arrived.
      const cacheKey = `${symbol}_${timeframe}`;
      const cached = chartDataCache[cacheKey];
      if (cached && emaSeriesRef.current && smaSeriesRef.current) {
        const lastIdx = cached.length - 1;
        if (lastIdx >= 0) {
          const mult1 = 2 / (ema1Length + 1);
          if (cached[lastIdx].time === updatedCandle.time) {
            cached[lastIdx] = updatedCandle;
          } else {
            // The bar that was forming until now has definitively closed --
            // advance the EMA1 anchor by one real step using its final
            // close before appending the new (still-forming) bar.
            lastEma1Ref.current = lastEma1Ref.current !== null
              ? (cached[lastIdx].close - lastEma1Ref.current) * mult1 + lastEma1Ref.current
              : cached[lastIdx].close;
            cached.push(updatedCandle);
          }

          // EMA1: live value for the still-forming last bar, anchored on
          // the last fully-closed bar's EMA -- repeated ticks within the
          // same forming bar recompute from that same fixed anchor rather
          // than compounding, exactly matching what a full recompute would
          // give for the bar in progress.
          const liveEma1 = lastEma1Ref.current !== null
            ? (updatedCandle.close - lastEma1Ref.current) * mult1 + lastEma1Ref.current
            : updatedCandle.close;
          emaSeriesRef.current.update({ time: updatedCandle.time, value: liveEma1 });

          // EMA "2" is actually a simple moving average (calculateSMA) --
          // a plain windowed average over the last ema2Length closes is
          // O(period), not the O(n) full-array EMA this used to run.
          const windowStart = Math.max(0, cached.length - ema2Length);
          const window = cached.slice(windowStart);
          const smaValue = window.reduce((sum: number, b: any) => sum + b.close, 0) / window.length;
          smaSeriesRef.current.update({ time: updatedCandle.time, value: smaValue });

          // VWAP is volume-weighted, and live ticks here never carry real
          // volume (always 0, same as the volume series' own live update
          // above) -- so it correctly holds its last historical value
          // until the next fetch rather than needing an update here.
        }
      }
    }
  }, [livePrice, timeframe, lastTick, ema1Length, ema2Length]);

  return (
    <div className="w-full h-full relative" style={{ minHeight: "450px" }}>
      {/* Chart Header Overlay */}
      <div className="absolute top-2 left-4 z-20 pointer-events-none flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground text-sm tracking-tight">{symbol.split(':')[1]?.split('-')[0] || symbol}</span>
          <span className="text-muted-foreground text-xs">{timeframe}</span>
          {livePrice && livePrice > 0 && (
            <>
              <span className="text-muted-foreground/50 text-xs">|</span>
              <span className={`font-mono font-bold text-sm tracking-tighter ${lastCandleOpen !== null && livePrice >= lastCandleOpen ? 'text-emerald-400' : 'text-red-400'}`}>
                ₹{livePrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {countdown && isMarketOpen() && (
                <>
                  <span className="text-muted-foreground/50 text-xs">|</span>
                  <span className="text-orange-400 font-mono text-xs font-semibold animate-pulse shadow-orange-500/20">{countdown}</span>
                </>
              )}
              {!isMarketOpen() && (
                <>
                  <span className="text-muted-foreground/50 text-xs">|</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">Market Closed</span>
                </>
              )}
            </>
          )}
        </div>
        <div ref={tooltipRef} className="hidden text-[11px] font-mono tracking-tight px-3" />
      </div>

      {/* Settings Panel Overlay */}
      {showSettings && (
        <div className="absolute bottom-14 right-3 z-50 w-[360px] bg-background/95 backdrop-blur-xl border border-border shadow-2xl rounded-xl pointer-events-auto flex flex-col transform origin-bottom-right animate-in fade-in zoom-in-95 duration-200 overflow-hidden">
          {/* Header */}
          <div className="flex justify-between items-center px-5 py-3.5 border-b border-border/50 bg-muted/20">
            <h3 className="font-semibold text-foreground flex items-center gap-2 text-sm"><Settings2 size={16} className="text-primary" /> Chart Settings</h3>
            <button onClick={handleCancelSettings} className="text-muted-foreground hover:text-foreground p-1 rounded hover:bg-muted/50 transition-colors"><X size={16} /></button>
          </div>

          {/* Tabs */}
          <div className="flex px-5 pt-3 gap-6 border-b border-border/50 bg-muted/10">
            <button
              onClick={() => setActiveTab('indicators')}
              className={`pb-2.5 text-sm font-medium transition-colors border-b-2 ${activeTab === 'indicators' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            >
              Indicators
            </button>
            <button
              onClick={() => setActiveTab('smartTrend')}
              className={`pb-2.5 text-sm font-medium transition-colors border-b-2 ${activeTab === 'smartTrend' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            >
              Smart Trend
            </button>
          </div>

          {/* Content */}
          <div className="p-5 max-h-[420px] overflow-y-auto custom-scrollbar">
            {activeTab === 'indicators' && (
              <div className="flex flex-col gap-0 animate-in fade-in duration-300">
                <SettingGroup title="EMA 1" active={activeAccordion === 'ema1'} onToggle={() => setActiveAccordion(activeAccordion === 'ema1' ? null : 'ema1')}>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Length</label>
                      <input type="number" value={ema1Length} onChange={(e) => setEma1Length(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Width</label>
                      <select value={ema1LineWidth} onChange={(e) => setEma1LineWidth(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={1}>1px</option><option value={2}>2px</option><option value={3}>3px</option><option value={4}>4px</option>
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 items-end mt-1">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Style</label>
                      <select value={ema1LineStyle} onChange={(e) => setEma1LineStyle(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={0}>Solid</option><option value={1}>Dotted</option><option value={2}>Dashed</option>
                      </select>
                    </div>
                    <div className="pb-1"><ColorSwatch label="Color" color={ema1Color} onChange={setEma1Color} /></div>
                  </div>
                </SettingGroup>

                <SettingGroup title="EMA 2" active={activeAccordion === 'ema2'} onToggle={() => setActiveAccordion(activeAccordion === 'ema2' ? null : 'ema2')}>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Length</label>
                      <input type="number" value={ema2Length} onChange={(e) => setEma2Length(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Width</label>
                      <select value={ema2LineWidth} onChange={(e) => setEma2LineWidth(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={1}>1px</option><option value={2}>2px</option><option value={3}>3px</option><option value={4}>4px</option>
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 items-end mt-1">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Style</label>
                      <select value={ema2LineStyle} onChange={(e) => setEma2LineStyle(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={0}>Solid</option><option value={1}>Dotted</option><option value={2}>Dashed</option>
                      </select>
                    </div>
                    <div className="pb-1"><ColorSwatch label="Color" color={ema2Color} onChange={setEma2Color} /></div>
                  </div>
                </SettingGroup>

                <SettingGroup title="Relative Strength Index (RSI)" active={activeAccordion === 'rsi'} onToggle={() => setActiveAccordion(activeAccordion === 'rsi' ? null : 'rsi')}>
                  <Toggle checked={showRsi} onChange={setShowRsi} label="Show RSI" />
                  <div className="w-full h-px bg-border/40 my-1"></div>
                  <div className="grid grid-cols-2 gap-4 mt-2">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Length</label>
                      <input type="number" value={rsiLength} onChange={(e) => setRsiLength(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Width</label>
                      <select value={rsiLineWidth} onChange={(e) => setRsiLineWidth(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={1}>1px</option><option value={2}>2px</option><option value={3}>3px</option><option value={4}>4px</option>
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 items-end mt-1">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Style</label>
                      <select value={rsiLineStyle} onChange={(e) => setRsiLineStyle(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm cursor-pointer">
                        <option value={0}>Solid</option><option value={1}>Dotted</option><option value={2}>Dashed</option>
                      </select>
                    </div>
                    <div className="pb-1"><ColorSwatch label="Line Color" color={rsiColor} onChange={setRsiColor} /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-1">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Overbought</label>
                      <input type="number" value={rsiOverbought} onChange={(e) => setRsiOverbought(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Oversold</label>
                      <input type="number" value={rsiOversold} onChange={(e) => setRsiOversold(Number(e.target.value))} className="bg-background px-3 py-1.5 rounded-md text-sm outline-none border border-border focus:border-primary/50 transition-colors shadow-sm" />
                    </div>
                  </div>
                </SettingGroup>

                <SettingGroup title="Volume" active={activeAccordion === 'vol'} onToggle={() => setActiveAccordion(activeAccordion === 'vol' ? null : 'vol')}>
                  <Toggle checked={showVolume} onChange={setShowVolume} label="Show Volume" />
                </SettingGroup>

                <SettingGroup title="VWAP" active={activeAccordion === 'vwap'} onToggle={() => setActiveAccordion(activeAccordion === 'vwap' ? null : 'vwap')}>
                  <Toggle checked={showVwap} onChange={setShowVwap} label="Show VWAP" />
                  {showVwap && (
                    <>
                      <div className="w-full h-px bg-border/40 my-1"></div>
                      <ColorSwatch label="Line Color" color={vwapColor} onChange={setVwapColor} />
                    </>
                  )}
                </SettingGroup>
              </div>
            )}

            {activeTab === 'smartTrend' && (
              <div className="flex flex-col gap-5 animate-in fade-in duration-300">
                <Toggle checked={showSmartTrend} onChange={setShowSmartTrend} label="Enable Smart Trend Colors" />

                {showSmartTrend && (
                  <div className="bg-muted/30 rounded-lg p-4 border border-border/50 shadow-inner">
                    <div className="flex flex-col gap-1">
                      <ColorSwatch label="Bullish Surge (Strong Up)" color={bullishSurgeColor} onChange={setBullishSurgeColor} />
                      <ColorSwatch label="Bearish Surge (Strong Down)" color={bearishSurgeColor} onChange={setBearishSurgeColor} />
                      <div className="my-1.5 w-full h-px bg-border/40"></div>
                      <ColorSwatch label="Normal Up" color={bullishNormalColor} onChange={setBullishNormalColor} />
                      <ColorSwatch label="Normal Down" color={bearishNormalColor} onChange={setBearishNormalColor} />
                      <div className="my-1.5 w-full h-px bg-border/40"></div>
                      <ColorSwatch label="Chop Phase (Sideways)" color={chopColor} onChange={setChopColor} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-5 py-4 border-t border-border/50 bg-muted/10 flex justify-end gap-3">
            <button
              onClick={handleCancelSettings}
              className="px-5 py-2 bg-muted text-muted-foreground text-sm font-medium rounded-lg hover:bg-muted-foreground/10 transition-all active:scale-95 border border-border"
            >
              Cancel
            </button>
            <button
              onClick={() => setShowSettings(false)}
              className="px-5 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-all shadow-md active:scale-95"
            >
              Save Settings
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-background/50 backdrop-blur-sm">
          <RefreshCw className="w-6 h-6 animate-spin text-primary mb-2" />
          <span className="text-sm font-medium">Loading {symbol} Market Data...</span>
        </div>
      )}
      {error && !loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="text-destructive font-semibold flex flex-col items-center">
            <span className="text-2xl mb-2">⚠️</span>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Floating Countdown on Price Scale */}
      {countdown && isMarketOpen() && (
        <div ref={countdownRef} className="absolute right-0 w-[55px] z-20 pointer-events-none flex justify-center" style={{ top: 0 }}>
          <div className="flex items-center justify-center gap-1 bg-background/90 backdrop-blur-md px-1.5 py-0.5 border border-border/20 shadow-md">
            <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse"></span>
            <span className="text-orange-400 font-mono text-[10px] font-bold">{countdown}</span>
          </div>
        </div>
      )}

      {/* Chart Toolbar: Reset Zoom / Toggle Markers / Export / Settings */}
      <div className="absolute bottom-1 right-2 z-20 flex items-center gap-1.5">
        <button
          onClick={() => chartRef.current?.timeScale().fitContent()}
          className="p-2 rounded-full bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground transition-all shadow-lg border border-border/40 backdrop-blur-md pointer-events-auto flex items-center justify-center hover:scale-110 active:scale-95"
          title="Reset Zoom"
        >
          <ResetZoomIcon size={16} />
        </button>
        <button
          onClick={() => setShowAutoSignalsState(!showAutoSignalsState)}
          className={`p-2 rounded-full transition-all shadow-lg border backdrop-blur-md pointer-events-auto flex items-center justify-center hover:scale-110 active:scale-95 ${showAutoSignalsState ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 shadow-emerald-500/10' : 'bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground border-border/40'}`}
          title={showAutoSignalsState ? "Signals ON (Click to turn OFF for Clean Normal Chart)" : "Signals OFF (Click to turn ON Auto BUY/SELL/SL Signals)"}
        >
          <Bot size={16} className={showAutoSignalsState ? "animate-pulse" : ""} />
        </button>
        <button
          onClick={() => setShowMarkers(!showMarkers)}
          className={`p-2 rounded-full transition-all shadow-lg border backdrop-blur-md pointer-events-auto flex items-center justify-center hover:scale-110 active:scale-95 ${showMarkers ? 'bg-primary/20 text-primary border-primary/30' : 'bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground border-border/40'}`}
          title={showMarkers ? "Hide Trade Markers" : "Show Trade Markers"}
        >
          <Tag size={16} />
        </button>
        <button
          onClick={() => {
            if (!chartRef.current) return;
            const canvas = chartRef.current.takeScreenshot();
            const link = document.createElement('a');
            link.href = canvas.toDataURL('image/png');
            link.download = `${symbol.replace(/[:\s]/g, '_')}_${timeframe.replace(/\s/g, '')}_chart.png`;
            link.click();
          }}
          className="p-2 rounded-full bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground transition-all shadow-lg border border-border/40 backdrop-blur-md pointer-events-auto flex items-center justify-center hover:scale-110 active:scale-95"
          title="Export Chart as PNG"
        >
          <Download size={16} />
        </button>
        <button
          onClick={() => showSettings ? handleCancelSettings() : handleOpenSettings()}
          className="p-2 rounded-full bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground transition-all shadow-lg border border-border/40 backdrop-blur-md pointer-events-auto flex items-center justify-center hover:scale-110 active:scale-95"
          title="Chart Settings"
        >
          <Settings2 size={16} />
        </button>
      </div>

      <div ref={chartContainerRef} className="w-full h-full min-h-[450px] absolute inset-0 z-0" />
    </div>
  );
}
