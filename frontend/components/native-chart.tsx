"use client";

import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, TickMarkType, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode, createSeriesMarkers } from "lightweight-charts";
import { RefreshCw, Settings2, X, ChevronDown, ChevronUp, Maximize2 as ResetZoomIcon, Download, Tag, Bot, Eye, EyeOff, Layers, BarChart3, Activity, Plus } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useChartSettingsStore } from "@/store/useChartSettingsStore";
import { parseBackendDatetimeToEpochSeconds, getISTNowParts, istWallTimeToEpochSeconds, isMarketOpenIST, formatEpochISTParts } from "@/lib/ist-time";
import TradingViewIndicatorModal, { IndicatorType } from "@/components/tradingview-indicator-modal";
import IndicatorSettings, { IndicatorSettingsData, defaultIndicatorSettings } from "@/components/indicator-settings";
import { computeSMC, computeFRVP, computeRSIWithSignal, SMCResult, FRVPResult } from "@/lib/indicators-engine";

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

  // Bars the feed reports with no volume are left at zero.
  //
  // This block previously manufactured a figure for them -- the previous bar's
  // volume scaled by candle range, falling back to a hardcoded 1,500,000 when
  // no bar in the window had any volume at all -- so the histogram would never
  // look empty. A drawn bar is a claim that something traded, and NSE index
  // series legitimately carry no volume: the honest rendering of "no volume
  // reported" is no bar, not an invented one.
  //
  // This matters beyond the chart. ExitAnalyzerAgent's Factor 4 reads volume
  // deceleration as a live exit input, so normalising zeros into plausible
  // numbers teaches the reader to trust a series that can be fabricated.
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

// Strategy signals are NOT computed here. They come from the engine that
// actually trades, via GET /api/strategy-markers -- see fetchStrategyMarkers
// below. A second implementation in this file used to draw BUY CE / BUY PE
// markers with no ADX filter and a wider EMA-touch buffer than the Python
// engine, so the chart showed entries the bot would never take (NIFTY
// 2026-09-18: chart 4, engine 0). One rule, one implementation.

const formatVolumeVal = (val: number | null | undefined): string => {
  if (val === null || val === undefined || isNaN(val)) return "---";
  if (val >= 10000000) return (val / 10000000).toFixed(2) + "Cr";
  if (val >= 1000000) return (val / 1000000).toFixed(2) + "M";
  if (val >= 1000) return (val / 1000).toFixed(1) + "K";
  return val.toLocaleString();
};

export interface SignalLevels {
  entry?: number;
  sl?: number;
  target?: number;
  title?: string;
}

export interface AppliedIndicatorsState {
  ema1: boolean;
  ema2: boolean;
  smc: boolean;
  frvp: boolean;
  rsi: boolean;
  vol: boolean;
  /** The backend strategy's own SMC overlay (GET /api/rsi-smc-overlay). */
  rsiSmc: boolean;
}

/** One overlay payload from the engine. Shapes mirror the endpoint. */
export interface RsiSmcOverlay {
  strategy_id?: string;
  view?: string;
  causal?: boolean;
  active?: boolean;
  bars?: number;
  params?: Record<string, any>;
  structure: { epoch: number; type: string; bullish: boolean; price: number | null; internal?: boolean }[];
  fvg: { epoch: number; bullish: boolean; top: number | null; bottom: number | null; mitigated_time: string | null }[];
  sweeps: { epoch: number; side: string; level: number | null; extreme: number | null }[];
  levels: { epoch: number; high: number | null; low: number | null }[];
  pd_band: { epoch: number; pdh: number | null; pdl: number | null; tol: number | null }[];
}

export const DEFAULT_APPLIED_INDICATORS: AppliedIndicatorsState = {
  ema1: true,
  ema2: true,
  smc: true,
  frvp: true,
  rsi: true,
  vol: true,
  // Off by default: a new overlay must not silently appear on charts that
  // never asked for it. The user adds it from the indicator directory.
  rsiSmc: false,
};

interface NativeChartProps {
  symbol: string;
  livePrice?: number;
  liveVolume?: number;
  timeframe?: string;
  initialData?: any[];
  disableFetch?: boolean;
  showDynamicTrend?: boolean;
  lastTick?: number;
  markers?: any[];
  showAutoSignals?: boolean;
  signalLevels?: SignalLevels | null;
  hideBottomToolbar?: boolean;
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

export default function NativeChart({ symbol, livePrice, liveVolume = 0, timeframe = "5 Min", initialData, disableFetch, lastTick = 0, markers, showAutoSignals = true, signalLevels, hideBottomToolbar = true }: NativeChartProps) {
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
  const barStartVolRef = useRef<{ time: number; vol: number }>({ time: 0, vol: 0 });
  const liveBarVolRef = useRef<number>(0);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<string>("");
  const [lastCandleOpen, setLastCandleOpen] = useState<number | null>(null);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showAutoSignalsState, setShowAutoSignalsState] = useState(showAutoSignals ?? false);

  // Listen to external chart toolbar events (moved from bottom overlay to header)
  useEffect(() => {
    const onResetZoom = () => {
      chartRef.current?.timeScale().fitContent();
    };
    const onToggleSignals = (e: any) => {
      setShowAutoSignalsState((prev) => {
        const next = e.detail?.value !== undefined ? Boolean(e.detail.value) : !prev;
        window.dispatchEvent(new CustomEvent("chart:signals-changed", { detail: { value: next } }));
        return next;
      });
    };
    const onToggleMarkers = (e: any) => {
      setShowMarkers((prev) => {
        const next = e.detail?.value !== undefined ? Boolean(e.detail.value) : !prev;
        window.dispatchEvent(new CustomEvent("chart:markers-changed", { detail: { value: next } }));
        return next;
      });
    };
    const onExportPng = () => {
      if (!chartRef.current) return;
      const canvas = chartRef.current.takeScreenshot();
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = `${symbol.replace(/[:\s]/g, "_")}_${timeframe.replace(/\s/g, "")}_chart.png`;
      link.click();
    };
    const onOpenSettings = () => {
      setShowSettings(true);
    };
    const onOpenIndicators = () => {
      setShowManaIndicatorsModal(true);
    };
    const onRsiSmcToggled = (e: any) => {
      const on = Boolean(e?.detail?.value);
      setAppliedIndicators((prev) => {
        const next = { ...prev, rsiSmc: on };
        try {
          localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
        } catch {}
        return next;
      });
      if (on) setShowRsiSmc(true);
    };

    window.addEventListener("chart:reset-zoom", onResetZoom);
    window.addEventListener("chart:toggle-signals", onToggleSignals as EventListener);
    window.addEventListener("chart:toggle-markers", onToggleMarkers as EventListener);
    window.addEventListener("chart:export-png", onExportPng);
    window.addEventListener("chart:open-settings", onOpenSettings);
    window.addEventListener("chart:open-indicators", onOpenIndicators);
    window.addEventListener("chart:rsi-smc-toggled", onRsiSmcToggled as EventListener);

    // Initial sync
    window.dispatchEvent(new CustomEvent("chart:signals-changed", { detail: { value: showAutoSignalsState } }));
    window.dispatchEvent(new CustomEvent("chart:markers-changed", { detail: { value: showMarkers } }));

    return () => {
      window.removeEventListener("chart:reset-zoom", onResetZoom);
      window.removeEventListener("chart:toggle-signals", onToggleSignals as EventListener);
      window.removeEventListener("chart:toggle-markers", onToggleMarkers as EventListener);
      window.removeEventListener("chart:export-png", onExportPng);
      window.removeEventListener("chart:open-settings", onOpenSettings);
      window.removeEventListener("chart:open-indicators", onOpenIndicators);
      window.removeEventListener("chart:rsi-smc-toggled", onRsiSmcToggled as EventListener);
    };
  }, [symbol, timeframe, showAutoSignalsState, showMarkers]);

  // Active Indicators State
  const [showEma1, setShowEma1] = useState(true);
  const [showEma2, setShowEma2] = useState(true);
  const [showSmc, setShowSmc] = useState(true);
  const [showRsiSmc, setShowRsiSmc] = useState(true);
  const [showFrvp, setShowFrvp] = useState(true);
  const [hideAllIndicators, setHideAllIndicators] = useState(false);
  const [collapseAllIndicators, setCollapseAllIndicators] = useState(false);

  // Applied Indicators State (TradingView Style - Indicator can be removed from chart via X or restored)
  const [appliedIndicators, setAppliedIndicators] = useState<AppliedIndicatorsState>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("mana_applied_indicators");
        if (saved) {
          return { ...DEFAULT_APPLIED_INDICATORS, ...JSON.parse(saved) };
        }
      } catch {}
    }
    return DEFAULT_APPLIED_INDICATORS;
  });
  const appliedIndicatorsRef = useRef(appliedIndicators);
  appliedIndicatorsRef.current = appliedIndicators;

  /** Fetch the engine's SMC overlay. Nothing about it is recomputed in the
   *  browser -- that is the entire point of the endpoint. */
  const fetchRsiSmcOverlay = useCallback(async (chartData: any[]) => {
    if (!appliedIndicatorsRef.current.rsiSmc || !chartData || !chartData.length) {
      rsiSmcRef.current = null;
      setRsiSmcStatusText("");
      requestAnimationFrame(redrawCanvasOverlays);
      return;
    }
    try {
      const firstTs = chartData[0].time as number;
      const lastTs = chartData[chartData.length - 1].time as number;
      const asDate = (epoch: number) => new Date(epoch * 1000).toISOString().split("T")[0];
      const url = `/api/rsi-smc-overlay?symbol=${encodeURIComponent(symbol)}`
        + `&start_date=${asDate(firstTs)}&end_date=${asDate(lastTs)}`
        + `&timeframe=${encodeURIComponent(timeframe)}`;
      const res = await fetch(url);
      if (!res.ok) { rsiSmcRef.current = null; setRsiSmcStatusText("unavailable"); return; }
      const json: RsiSmcOverlay = await res.json();
      rsiSmcRef.current = json;
      const bos = (json.structure || []).filter(x => (x.type || "").toUpperCase().startsWith("BOS")).length;
      const choch = (json.structure || []).length - bos;
      setRsiSmcStatusText(
        `${bos} BOS • ${choch} CHoCH • ${(json.sweeps || []).length} sweeps • ${(json.fvg || []).length} FVG`);
    } catch {
      rsiSmcRef.current = null;
      setRsiSmcStatusText("unavailable");
    }
    requestAnimationFrame(redrawCanvasOverlays);
  }, [symbol, timeframe]);

  // Switching the indicator on must draw it now, not at the next data load.
  useEffect(() => {
    void fetchRsiSmcOverlay(lastChartDataRef.current);
  }, [appliedIndicators.rsiSmc, symbol, timeframe, fetchRsiSmcOverlay]);

  const handleRemoveIndicator = (key: keyof AppliedIndicatorsState) => {
    setAppliedIndicators((prev) => {
      const next = { ...prev, [key]: false };
      try {
        localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
      } catch {}
      return next;
    });
    requestAnimationFrame(redrawCanvasOverlays);
  };

  const handleApplyIndicator = (key: keyof AppliedIndicatorsState) => {
    setAppliedIndicators((prev) => {
      const next = { ...prev, [key]: true };
      try {
        localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
      } catch {}
      return next;
    });
    requestAnimationFrame(redrawCanvasOverlays);
  };

  const handleResetAllIndicators = () => {
    setAppliedIndicators(DEFAULT_APPLIED_INDICATORS);
    setShowEma1(true);
    setShowEma2(true);
    setShowSmc(true);
    setShowFrvp(true);
    setShowRsi(true);
    setShowVolume(true);
    try {
      localStorage.setItem("mana_applied_indicators", JSON.stringify(DEFAULT_APPLIED_INDICATORS));
    } catch {}
    requestAnimationFrame(redrawCanvasOverlays);
  };

  const activeAppliedCount = useMemo(() => {
    return Object.values(appliedIndicators).filter(Boolean).length;
  }, [appliedIndicators]);

  // Persistent collapse all state from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("mana_indicators_collapsed");
      if (saved !== null) {
        setCollapseAllIndicators(saved === "true");
      }
    } catch {
      // Ignore localStorage read errors in restricted contexts
    }
  }, []);

  const handleToggleCollapseAll = () => {
    setCollapseAllIndicators((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("mana_indicators_collapsed", String(next));
      } catch {
        // Ignore localStorage write errors
      }
      return next;
    });
  };

  const hideAllIndicatorsRef = useRef(hideAllIndicators);
  hideAllIndicatorsRef.current = hideAllIndicators;
  const showFrvpRef = useRef(showFrvp);
  showFrvpRef.current = showFrvp;
  const showSmcRef = useRef(showSmc);
  showSmcRef.current = showSmc;
  const showEma1Ref = useRef(showEma1);
  showEma1Ref.current = showEma1;
  const showEma2Ref = useRef(showEma2);
  showEma2Ref.current = showEma2;
  const showRsiRef = useRef(showRsi);
  showRsiRef.current = showRsi;

  // Indicator live values & statuses for Legend
  const [liveEma1Val, setLiveEma1Val] = useState<number | null>(null);
  const [liveEma2Val, setLiveEma2Val] = useState<number | null>(null);
  const [liveRsiVal, setLiveRsiVal] = useState<number | null>(null);
  const [liveRsiSignalVal, setLiveRsiSignalVal] = useState<number | null>(null);
  const [liveVolumeVal, setLiveVolumeVal] = useState<number | null>(liveVolume || null);
  const [smcStatusText, setSmcStatusText] = useState<string>("");
  const [rsiSmcStatusText, setRsiSmcStatusText] = useState<string>("");
  const rsiSmcRef = useRef<RsiSmcOverlay | null>(null);
  /** The candles currently drawn, so the overlay can be fetched the moment
   *  the indicator is switched on instead of waiting for the next reload. */
  const lastChartDataRef = useRef<any[]>([]);
  const showRsiSmcRef = useRef(showRsiSmc);
  showRsiSmcRef.current = showRsiSmc;
  const [frvpStatusText, setFrvpStatusText] = useState<string>("");
  const lastVolumeRef = useRef<number | null>(liveVolume || null);

  const rsiSignalSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const rafOverlayIdRef = useRef<number | null>(null);
  const smcPriceLinesRef = useRef<any[]>([]);
  const frvpPriceLinesRef = useRef<any[]>([]);
  const calculatedIndicatorsRef = useRef<{ smc: SMCResult | null; frvp: FRVPResult | null }>({
    smc: null,
    frvp: null,
  });

  const [manaSettings, setManaSettings] = useState<IndicatorSettingsData>(defaultIndicatorSettings);
  const manaSettingsRef = useRef<IndicatorSettingsData>(defaultIndicatorSettings);
  manaSettingsRef.current = manaSettings;

  // Mana Institutional Indicators State
  const [activeIndicatorModal, setActiveIndicatorModal] = useState<IndicatorType | null>(null);
  const [showManaIndicatorsModal, setShowManaIndicatorsModal] = useState(false);
  const [showIndicatorsDropdown, setShowIndicatorsDropdown] = useState(false);

  const handleOpenEmaSettings = (acc: 'ema1' | 'ema2') => {
    setActiveTab('indicators');
    setActiveAccordion(acc);
    setShowSettings(true);
  };

  // Sync settings from localStorage and event dispatch
  useEffect(() => {
    if (typeof window === "undefined") return;

    const applySettingsObj = (p: any) => {
      if (!p) return;
      setManaSettings((prev) => {
        const next: IndicatorSettingsData = {
          smc: { ...prev.smc, ...(p.smc || {}) },
          frvp: { ...prev.frvp, ...(p.frvp || {}) },
          rsi: { ...prev.rsi, ...(p.rsi || {}) },
        };
        manaSettingsRef.current = next;
        return next;
      });

      if (p.smc?.enabled !== undefined) setShowSmc(Boolean(p.smc.enabled));
      if (p.frvp?.enabled !== undefined) setShowFrvp(Boolean(p.frvp.enabled));
      if (p.rsi?.enabled !== undefined) setShowRsi(Boolean(p.rsi.enabled));

      if (p.rsi?.period) setRsiLength(Number(p.rsi.period));
      if (p.rsi?.overbought) setRsiOverbought(Number(p.rsi.overbought));
      if (p.rsi?.oversold) setRsiOversold(Number(p.rsi.oversold));
      if (p.rsi?.color) setRsiColor(p.rsi.color);
    };

    try {
      const saved = localStorage.getItem("mana_indicator_settings");
      if (saved) applySettingsObj(JSON.parse(saved));
    } catch {}

    const onIndicatorSettingsChanged = (e: any) => {
      const detail = e.detail?.settings || e.detail;
      applySettingsObj(detail);
    };

    window.addEventListener("indicatorSettingsChanged", onIndicatorSettingsChanged);
    window.addEventListener("mana_indicators_updated", onIndicatorSettingsChanged);

    return () => {
      window.removeEventListener("indicatorSettingsChanged", onIndicatorSettingsChanged);
      window.removeEventListener("mana_indicators_updated", onIndicatorSettingsChanged);
    };
  }, [setShowRsi, setRsiLength, setRsiOverbought, setRsiOversold, setRsiColor]);

  const redrawCanvasOverlays = () => {
    const canvas = overlayCanvasRef.current;
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = chartContainerRef.current;

    if (!canvas || !chart || !series || !container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width <= 0 || height <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Detect exact chart pane width (excluding the right price scale)
    const firstCell = container.querySelector("table tr td:first-child") as HTMLElement | null;
    const lastCell = container.querySelector("table tr td:last-child") as HTMLElement | null;
    const priceScaleWidth = lastCell && lastCell.clientWidth > 0 ? lastCell.clientWidth : 75;
    const chartPaneWidth = firstCell && firstCell.clientWidth > 0 ? firstCell.clientWidth : (width - priceScaleWidth);

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    // Hard clip strictly to the candlestick plot area (stopping 1px before the price scale border)
    // This physically guarantees zero lines, labels, boxes, or pixels can EVER draw onto or overlap the price scale!
    ctx.beginPath();
    ctx.rect(0, 0, chartPaneWidth - 1, height);
    ctx.clip();

    if (hideAllIndicatorsRef.current) {
      ctx.restore();
      return;
    }

    const { smc, frvp } = calculatedIndicatorsRef.current;
    const mSettings = manaSettingsRef.current;
    const rightScaleMargin = chartPaneWidth;

    // RSI_SMC engine overlay. Drawn from the backend payload only.
    if (appliedIndicatorsRef.current.rsiSmc && showRsiSmcRef.current
        && !hideAllIndicatorsRef.current && rsiSmcRef.current) {
      const ov = rsiSmcRef.current;
      const ts = chart.timeScale();
      const xOf = (epoch: number) => ts.timeToCoordinate(epoch as Time);
      const yOf = (price: number) => series.priceToCoordinate(price);
      const inPane = (x: number | null) => x !== null && x >= 0 && x <= chartPaneWidth - 1;

      const BULL = "#14b8a6";
      const BEAR = "#f43f5e";
      const BAND = "#a78bfa";
      const LEVEL = "#64748b";

      // a. prior-day band (PDH/PDL +/- 0.25 ATR) -- the frozen rule
      ctx.save();
      ctx.lineWidth = 1;
      for (const key of ["pdh", "pdl"] as const) {
        ctx.beginPath();
        let started = false;
        for (const row of ov.pd_band || []) {
          const v = row[key];
          if (v === null || v === undefined) { started = false; continue; }
          const x = xOf(row.epoch), y = yOf(v);
          if (!inPane(x) || y === null) { started = false; continue; }
          if (!started) { ctx.moveTo(x as number, y); started = true; }
          else ctx.lineTo(x as number, y);
        }
        ctx.strokeStyle = BAND;
        ctx.setLineDash([4, 3]);
        ctx.stroke();
      }
      // tolerance ribbon around each level
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(167,139,250,0.10)";
      for (const key of ["pdh", "pdl"] as const) {
        ctx.beginPath();
        const top: [number, number][] = [];
        const bot: [number, number][] = [];
        for (const row of ov.pd_band || []) {
          const v = row[key], tol = row.tol;
          if (v === null || v === undefined || tol === null || tol === undefined) continue;
          const x = xOf(row.epoch), yu = yOf(v + tol), yl = yOf(v - tol);
          if (!inPane(x) || yu === null || yl === null) continue;
          top.push([x as number, yu]); bot.push([x as number, yl]);
        }
        if (top.length > 1) {
          ctx.moveTo(top[0][0], top[0][1]);
          for (const [x, y] of top) ctx.lineTo(x, y);
          for (let i = bot.length - 1; i >= 0; i--) ctx.lineTo(bot[i][0], bot[i][1]);
          ctx.closePath();
          ctx.fill();
        }
      }

      // b. rolling extreme levels the sweep rule reads
      ctx.setLineDash([2, 4]);
      ctx.strokeStyle = LEVEL;
      for (const key of ["high", "low"] as const) {
        ctx.beginPath();
        let started = false;
        for (const row of ov.levels || []) {
          const v = row[key];
          if (v === null || v === undefined) { started = false; continue; }
          const x = xOf(row.epoch), y = yOf(v);
          if (!inPane(x) || y === null) { started = false; continue; }
          if (!started) { ctx.moveTo(x as number, y); started = true; }
          else ctx.lineTo(x as number, y);
        }
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // c. unmitigated FVG boxes
      for (const g of ov.fvg || []) {
        if (g.top === null || g.bottom === null) continue;
        const x = xOf(g.epoch);
        if (!inPane(x)) continue;
        const yT = yOf(g.top), yB = yOf(g.bottom);
        if (yT === null || yB === null) continue;
        const w = Math.max(6, chartPaneWidth - (x as number));
        ctx.fillStyle = g.bullish ? "rgba(20,184,166,0.10)" : "rgba(244,63,94,0.10)";
        ctx.fillRect(x as number, Math.min(yT, yB), Math.min(w, 60), Math.abs(yT - yB));
      }

      // d. liquidity sweeps, at the extreme the wick actually reached
      for (const sw of ov.sweeps || []) {
        if (sw.extreme === null) continue;
        const x = xOf(sw.epoch), y = yOf(sw.extreme);
        if (!inPane(x) || y === null) continue;
        const bull = sw.side === "bullish";
        ctx.fillStyle = bull ? BULL : BEAR;
        ctx.beginPath();
        const px = x as number, d = 4;
        if (bull) { ctx.moveTo(px, y + d); ctx.lineTo(px - d, y + d * 2.2); ctx.lineTo(px + d, y + d * 2.2); }
        else { ctx.moveTo(px, y - d); ctx.lineTo(px - d, y - d * 2.2); ctx.lineTo(px + d, y - d * 2.2); }
        ctx.closePath();
        ctx.fill();
      }

      // e. BOS / CHoCH labels
      ctx.font = "9px ui-monospace, monospace";
      ctx.textBaseline = "middle";
      for (const ev of ov.structure || []) {
        if (ev.price === null) continue;
        const x = xOf(ev.epoch), y = yOf(ev.price);
        if (!inPane(x) || y === null) continue;
        const col = ev.bullish ? BULL : BEAR;
        ctx.strokeStyle = col;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo((x as number) - 5, y);
        ctx.lineTo((x as number) + 5, y);
        ctx.stroke();
        const label = (ev.type || "").toUpperCase().startsWith("BOS") ? "BOS" : "CHoCH";
        ctx.fillStyle = col;
        const tw = ctx.measureText(label).width;
        if ((x as number) + 7 + tw < chartPaneWidth - 2) {
          ctx.fillText(label, (x as number) + 7, ev.bullish ? y - 6 : y + 6);
        }
      }
      ctx.restore();
    }

    // 1. Draw FRVP Volume Profile (Left Side Histogram)
    if (appliedIndicatorsRef.current.frvp && showFrvpRef.current && !hideAllIndicatorsRef.current && frvp && frvp.bins && frvp.bins.length > 0 && frvp.maxBinVolume > 0) {
      const maxHistogramWidth = Math.min(180, width * 0.22);
      const startX = 65;

      const vahColor = mSettings.frvp.vah_color || "#38bdf8";
      const pocColor = mSettings.frvp.poc_color || "#eab308";

      if (mSettings.frvp.show_value_area !== false) {
        const vahY = series.priceToCoordinate(frvp.vahPrice);
        const valY = series.priceToCoordinate(frvp.valPrice);
        if (vahY !== null && valY !== null) {
          const topY = Math.min(vahY, valY);
          const boxH = Math.abs(valY - vahY);
          ctx.fillStyle = "rgba(56, 189, 248, 0.05)";
          ctx.fillRect(startX, topY, maxHistogramWidth + 20, boxH);
          ctx.strokeStyle = vahColor;
          ctx.setLineDash([3, 3]);
          ctx.strokeRect(startX, topY, maxHistogramWidth + 20, boxH);
          ctx.setLineDash([]);
        }
      }

      for (const bin of frvp.bins) {
        const yTop = series.priceToCoordinate(bin.priceHigh);
        const yBottom = series.priceToCoordinate(bin.priceLow);
        if (yTop === null || yBottom === null) continue;

        const y = Math.min(yTop, yBottom);
        const barH = Math.max(1.5, Math.abs(yBottom - yTop) - 0.5);
        const barW = (bin.totalVolume / frvp.maxBinVolume) * maxHistogramWidth;

        if (bin.isPoc && mSettings.frvp.show_poc !== false) {
          ctx.fillStyle = pocColor;
          ctx.fillRect(startX, y, barW, barH);
        } else if (bin.isInValueArea && mSettings.frvp.show_value_area !== false) {
          const buyW = bin.totalVolume > 0 ? (bin.buyVolume / bin.totalVolume) * barW : barW * 0.5;
          const sellW = barW - buyW;
          ctx.fillStyle = "rgba(16, 185, 129, 0.65)";
          ctx.fillRect(startX, y, buyW, barH);
          ctx.fillStyle = "rgba(239, 68, 68, 0.65)";
          ctx.fillRect(startX + buyW, y, sellW, barH);
        } else {
          const buyW = bin.totalVolume > 0 ? (bin.buyVolume / bin.totalVolume) * barW : barW * 0.5;
          const sellW = barW - buyW;
          ctx.fillStyle = "rgba(16, 185, 129, 0.25)";
          ctx.fillRect(startX, y, buyW, barH);
          ctx.fillStyle = "rgba(239, 68, 68, 0.25)";
          ctx.fillRect(startX + buyW, y, sellW, barH);
        }
      }

      // 1B. Clean FRVP POC line (touches the price scale border cleanly)
      if (frvp.pocPrice > 0 && mSettings.frvp.show_poc !== false) {
        const pocY = series.priceToCoordinate(frvp.pocPrice);
        if (pocY !== null) {
          ctx.strokeStyle = pocColor;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(startX, pocY);
          ctx.lineTo(rightScaleMargin, pocY);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.font = "bold 8.5px monospace";
          ctx.fillStyle = pocColor;
          ctx.textAlign = "right";
          ctx.textBaseline = "bottom";
          ctx.fillText(`POC ₹${frvp.pocPrice.toFixed(1)}`, rightScaleMargin - 4, pocY - 2);
        }
      }
    }

    // 2. Draw SMC Institutional Indicators (LuxAlgo Institutional Standard)
    if (appliedIndicatorsRef.current.smc && showSmcRef.current && !hideAllIndicatorsRef.current && smc) {

      // 2A. Vertical Daily Session Separators (09:15 IST) - Matching TradingView
      if (smc.sessionStarts && smc.sessionStarts.length > 0) {
        ctx.strokeStyle = "rgba(59, 130, 246, 0.35)";
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 3]);
        for (const sTime of smc.sessionStarts) {
          const sx = chart.timeScale().timeToCoordinate(sTime as Time);
          if (sx !== null && sx >= 65 && sx <= rightScaleMargin) {
            ctx.beginPath();
            ctx.moveTo(sx, 0);
            ctx.lineTo(sx, height);
            ctx.stroke();
          }
        }
        ctx.setLineDash([]);
      }

      // 2B. Multi-Timeframe Levels (PDH, PDL, PWL, PWH) - Exact TradingView Solid 1px Blue Lines touching scale border
      if (smc.mtfLevels && smc.mtfLevels.length > 0) {
        for (const lvl of smc.mtfLevels) {
          const isDaily = lvl.type === "PDH" || lvl.type === "PDL";
          const isWeekly = lvl.type === "PWH" || lvl.type === "PWL";
          if (isDaily && mSettings.smc.mtf_daily === false) continue;
          if (isWeekly && mSettings.smc.mtf_weekly === false) continue;

          const y = series.priceToCoordinate(lvl.price);
          if (y === null) continue;

          let startX = rightScaleMargin - 150;
          if (lvl.sessionStartTime) {
            const anchorX = chart.timeScale().timeToCoordinate(lvl.sessionStartTime as Time);
            if (anchorX !== null) startX = Math.max(65, anchorX);
          }

          const lineColor = "#3b82f6";
          ctx.strokeStyle = lineColor;
          ctx.lineWidth = 1;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(startX, y);
          ctx.lineTo(rightScaleMargin, y);
          ctx.stroke();

          // Clean terminal label above line touching right boundary (TradingView style) - never overlapping price scale
          ctx.font = "bold 9px monospace";
          ctx.fillStyle = lineColor;
          ctx.textAlign = "right";
          ctx.textBaseline = "bottom";
          ctx.fillText(lvl.type, rightScaleMargin - 4, y - 2);
        }
      }

      // 2C. Dealing Range Boxes: Premium, Equilibrium & Discount - Exact TradingView LuxAlgo Aesthetic
      if (mSettings.smc.show_premium_discount !== false && smc.dealingRange) {
        const dr = smc.dealingRange;
        const yTop = series.priceToCoordinate(dr.top);
        const yBottom = series.priceToCoordinate(dr.bottom);
        const yEq = series.priceToCoordinate(dr.equilibrium);

        if (yTop !== null && yBottom !== null && yEq !== null) {
          const boxStartX = chart.timeScale().timeToCoordinate(dr.startTime as Time);
          const startX = boxStartX !== null ? Math.max(65, Math.min(rightScaleMargin - 40, boxStartX)) : Math.max(65, rightScaleMargin - 220);
          const boxWidth = Math.max(35, rightScaleMargin - startX);
          const yMin = Math.min(yTop, yBottom);
          const yMax = Math.max(yTop, yBottom);
          const totalHeight = yMax - yMin;

          if (totalHeight > 10) {
            // Left vertical bounding line
            ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
            ctx.lineWidth = 1;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(startX, yMin);
            ctx.lineTo(startX, yMax);
            ctx.stroke();

            // 1. Premium Box (Top ~10% of dealing range)
            const premHeight = Math.max(7, totalHeight * 0.10);
            ctx.fillStyle = "rgba(244, 63, 94, 0.12)";
            ctx.fillRect(startX, yMin, boxWidth, premHeight);
            ctx.strokeStyle = "rgba(244, 63, 94, 0.30)";
            ctx.lineWidth = 1;
            ctx.strokeRect(startX, yMin, boxWidth, premHeight);

            // Premium label centered above
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#ef4444";
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText("Premium", startX + boxWidth / 2, yMin - 3);

            // 2. Equilibrium Band (50% midpoint)
            const eqHeight = Math.max(6, totalHeight * 0.05);
            const eqY = yEq - eqHeight / 2;
            ctx.fillStyle = "rgba(156, 163, 175, 0.12)";
            ctx.fillRect(startX, eqY, boxWidth, eqHeight);
            ctx.strokeStyle = "rgba(156, 163, 175, 0.35)";
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.strokeRect(startX, eqY, boxWidth, eqHeight);
            ctx.setLineDash([]);

            // Equilibrium label centered
            ctx.font = "bold 8px monospace";
            ctx.fillStyle = "#94a3b8";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("Equilibrium", startX + boxWidth / 2, yEq);

            // 3. Discount Box (Bottom ~10% of dealing range)
            const discHeight = Math.max(7, totalHeight * 0.10);
            const discY = yMax - discHeight;
            ctx.fillStyle = "rgba(20, 184, 166, 0.12)";
            ctx.fillRect(startX, discY, boxWidth, discHeight);
            ctx.strokeStyle = "rgba(20, 184, 166, 0.30)";
            ctx.lineWidth = 1;
            ctx.strokeRect(startX, discY, boxWidth, discHeight);

            // Discount label centered below
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#14b8a6";
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillText("Discount", startX + boxWidth / 2, yMax + 3);
          }
        }
      }

      // 2D. Weak High & Strong Low (and Strong High & Weak Low)
      if (mSettings.smc.show_strong_weak_high_low !== false) {
        if (smc.weakHigh) {
          const y = series.priceToCoordinate(smc.weakHigh.price);
          const x = chart.timeScale().timeToCoordinate(smc.weakHigh.time as Time);
          if (y !== null && x !== null && x >= 65 && x <= rightScaleMargin) {
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#ef4444";
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText("Weak High", x, y - 6);
          }
        }

        if (smc.strongLow) {
          const y = series.priceToCoordinate(smc.strongLow.price);
          const x = chart.timeScale().timeToCoordinate(smc.strongLow.time as Time);
          if (y !== null && x !== null && x >= 65 && x <= rightScaleMargin) {
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#10b981";
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillText("Strong Low", x, y + 6);
          }
        }

        if (smc.strongHigh) {
          const y = series.priceToCoordinate(smc.strongHigh.price);
          const x = chart.timeScale().timeToCoordinate(smc.strongHigh.time as Time);
          if (y !== null && x !== null && x >= 65 && x <= rightScaleMargin) {
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#ef4444";
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText("Strong High", x, y - 6);
          }
        }

        if (smc.weakLow) {
          const y = series.priceToCoordinate(smc.weakLow.price);
          const x = chart.timeScale().timeToCoordinate(smc.weakLow.time as Time);
          if (y !== null && x !== null && x >= 65 && x <= rightScaleMargin) {
            ctx.font = "bold 8.5px monospace";
            ctx.fillStyle = "#10b981";
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillText("Weak Low", x, y + 6);
          }
        }
      }

      // 2E. Equal Highs & Equal Lows (Dual-Pivot Pairs)
      if (mSettings.smc.show_equal_high_low !== false && smc.equalPivots && smc.equalPivots.length > 0) {
        for (const eq of smc.equalPivots) {
          const x1 = chart.timeScale().timeToCoordinate(eq.time1 as Time);
          const x2 = chart.timeScale().timeToCoordinate(eq.time2 as Time);
          const y = series.priceToCoordinate(eq.price);
          if (x1 === null || x2 === null || y === null) continue;

          const leftX = Math.min(x1, x2);
          const rightX = Math.max(x1, x2);
          if (rightX - leftX < 4) continue;

          const isEqh = eq.type === "EQH";
          const color = isEqh ? "#ef4444" : "#06b6d4";

          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.setLineDash([2, 2]);
          ctx.beginPath();
          ctx.moveTo(leftX, y);
          ctx.lineTo(rightX, y);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.font = "bold 8px monospace";
          ctx.fillStyle = color;
          ctx.textAlign = "center";
          ctx.textBaseline = isEqh ? "bottom" : "top";
          ctx.fillText(eq.type, (leftX + rightX) / 2, isEqh ? y - 3 : y + 3);
        }
      }

      // 2F. Swing Pivots (HH, LH, HL, LL)
      if (mSettings.smc.show_swing_points !== false && smc.swingPivots && smc.swingPivots.length > 0) {
        for (const pivot of smc.swingPivots) {
          if (pivot.type === "EQH" || pivot.type === "EQL") continue;

          const x = chart.timeScale().timeToCoordinate(pivot.time as Time);
          const y = series.priceToCoordinate(pivot.price);
          if (x === null || y === null || x < 65 || x > rightScaleMargin) continue;

          let color = "#94a3b8";
          if (pivot.type === "HH") color = "#10b981";
          else if (pivot.type === "LH") color = "#ef4444";
          else if (pivot.type === "HL") color = "#10b981";
          else if (pivot.type === "LL") color = "#ef4444";

          ctx.font = "bold 8px monospace";
          ctx.fillStyle = color;
          ctx.textAlign = "center";
          ctx.textBaseline = pivot.isHigh ? "bottom" : "top";
          ctx.fillText(pivot.label, x, pivot.isHigh ? y - 4 : y + 4);
        }
      }

      // 2G. Order Blocks - Exact TradingView LuxAlgo Signature Soft Blue
      if (mSettings.smc.show_order_blocks !== false) {
        const obFill = "rgba(147, 180, 255, 0.28)";
        const obStroke = "rgba(147, 180, 255, 0.45)";

        for (const ob of smc.bullishOrderBlocks) {
          const yTop = series.priceToCoordinate(ob.top);
          const yBottom = series.priceToCoordinate(ob.bottom);
          if (yTop === null || yBottom === null) continue;

          const coordX = chart.timeScale().timeToCoordinate(ob.startTime as Time);
          const boundedStartX = coordX !== null ? Math.max(65, Math.min(rightScaleMargin - 20, coordX)) : Math.max(65, rightScaleMargin - 150);
          const boxWidth = Math.max(20, rightScaleMargin - boundedStartX);
          const y = Math.min(yTop, yBottom);
          const boxHeight = Math.max(3, Math.abs(yBottom - yTop));

          ctx.fillStyle = obFill;
          ctx.fillRect(boundedStartX, y, boxWidth, boxHeight);
          ctx.strokeStyle = obStroke;
          ctx.lineWidth = 1;
          ctx.strokeRect(boundedStartX, y, boxWidth, boxHeight);
        }

        for (const ob of smc.bearishOrderBlocks) {
          const yTop = series.priceToCoordinate(ob.top);
          const yBottom = series.priceToCoordinate(ob.bottom);
          if (yTop === null || yBottom === null) continue;

          const coordX = chart.timeScale().timeToCoordinate(ob.startTime as Time);
          const boundedStartX = coordX !== null ? Math.max(65, Math.min(rightScaleMargin - 20, coordX)) : Math.max(65, rightScaleMargin - 150);
          const boxWidth = Math.max(20, rightScaleMargin - boundedStartX);
          const y = Math.min(yTop, yBottom);
          const boxHeight = Math.max(3, Math.abs(yBottom - yTop));

          ctx.fillStyle = obFill;
          ctx.fillRect(boundedStartX, y, boxWidth, boxHeight);
          ctx.strokeStyle = obStroke;
          ctx.lineWidth = 1;
          ctx.strokeRect(boundedStartX, y, boxWidth, boxHeight);
        }
      }

      // 2H. Market Structure Breaks (CHoCH & BOS) - Exact TradingView Styling
      if (mSettings.smc.show_swing_structure !== false && smc.structures && smc.structures.length > 0) {
        for (const st of smc.structures) {
          const y = series.priceToCoordinate(st.price);
          if (y === null) continue;

          const startX = chart.timeScale().timeToCoordinate(st.startTime as Time);
          const breakX = chart.timeScale().timeToCoordinate(st.breakTime as Time);
          if (startX === null || breakX === null) continue;

          const x1 = Math.max(65, Math.min(rightScaleMargin, startX));
          const x2 = Math.max(65, Math.min(rightScaleMargin, breakX));
          const xLeft = Math.min(x1, x2);
          const xRight = Math.max(x1, x2);
          if (xRight - xLeft < 6) continue;

          const isChoch = st.type === "CHoCH";
          const lineColor = isChoch ? (st.isBullish ? "#3b82f6" : "#ef4444") : (st.isBullish ? "#10b981" : "#ef4444");

          ctx.strokeStyle = lineColor;
          ctx.lineWidth = 1;
          ctx.setLineDash(isChoch ? (st.isBullish ? [] : [3, 3]) : [2, 2]);
          ctx.beginPath();
          ctx.moveTo(xLeft, y);
          ctx.lineTo(xRight, y);
          ctx.stroke();
          ctx.setLineDash([]);

          // Clean TradingView text directly above or below line
          const midX = (xLeft + xRight) / 2;
          ctx.font = "bold 8px monospace";
          ctx.fillStyle = lineColor;
          ctx.textAlign = "center";
          ctx.textBaseline = st.isBullish ? "bottom" : "top";
          ctx.fillText(st.type, midX, st.isBullish ? y - 2 : y + 2);
        }
      }
    }

    ctx.restore();
  };

  const updateFrvpPriceLines = () => {
    const series = seriesRef.current;
    if (!series) return;

    for (const pl of frvpPriceLinesRef.current) {
      try { series.removePriceLine(pl); } catch {}
    }
    frvpPriceLinesRef.current = [];
    // Note: FRVP POC line is rendered on overlayCanvasRef with strict clipping to prevent price scale overlap
  };

  const updateSmcPriceLines = () => {
    const series = seriesRef.current;
    if (!series) return;

    // Remove any previously created price lines to keep the chart clean like TradingView
    for (const pl of smcPriceLinesRef.current) {
      try { series.removePriceLine(pl); } catch {}
    }
    smcPriceLinesRef.current = [];

    // Note: In TradingView LuxAlgo SMC, order blocks, dealing ranges, MTF levels,
    // and swing points are cleanly drawn on the canvas overlay, NOT as full-screen
    // price lines cutting through candlesticks.
  };

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
      visible: appliedIndicators.vol && showVolume
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    // RSI Series
    const rsiSeries = chart.addSeries(LineSeries, {
      color: rsiColor || "#A855F7",
      lineWidth: rsiLineWidth as any,
      lineStyle: rsiLineStyle as any,
      priceScaleId: 'rsi',
      visible: appliedIndicators.rsi && showRsi && !hideAllIndicators
    });
    // RSI Signal Series (Signal EMA 20)
    const rsiSignalSeries = chart.addSeries(LineSeries, {
      color: '#F59E0B',
      lineWidth: 1,
      lineStyle: 0 as any,
      priceScaleId: 'rsi',
      visible: appliedIndicators.rsi && showRsi && !hideAllIndicators
    });
    chart.priceScale('rsi').applyOptions({
      scaleMargins: appliedIndicators.rsi && showRsi && !hideAllIndicators ? { top: 0.8, bottom: 0 } : { top: 1, bottom: 0 },
    });

    rsiObLineRef.current = rsiSeries.createPriceLine({
      price: rsiOverbought,
      color: 'rgba(239, 68, 68, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: appliedIndicators.rsi && showRsi && !hideAllIndicators,
      title: 'OB',
    });

    rsiOsLineRef.current = rsiSeries.createPriceLine({
      price: rsiOversold,
      color: 'rgba(16, 185, 129, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: appliedIndicators.rsi && showRsi && !hideAllIndicators,
      title: 'OS',
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981", downColor: "#EF4444", borderVisible: false,
      wickUpColor: "#10B981", wickDownColor: "#EF4444",
    });

    const seriesMarkers = createSeriesMarkers(candleSeries);
    seriesMarkersPluginRef.current = seriesMarkers;

    const emaSeries = chart.addSeries(LineSeries, {
      color: ema1Color,
      lineWidth: ema1LineWidth as any,
      lineStyle: ema1LineStyle as any,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      visible: appliedIndicators.ema1 && showEma1 && !hideAllIndicators,
    });
    const ema21Series = chart.addSeries(LineSeries, {
      color: ema2Color,
      lineWidth: ema2LineWidth as any,
      lineStyle: ema2LineStyle as any,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      visible: appliedIndicators.ema2 && showEma2 && !hideAllIndicators,
    });
    const vwapSeries = chart.addSeries(LineSeries, {
      color: vwapColor,
      lineWidth: vwapLineWidth as any,
      lineStyle: 2 as any,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      visible: showVwap && !hideAllIndicators,
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    emaSeriesRef.current = emaSeries;
    smaSeriesRef.current = ema21Series;
    volumeSeriesRef.current = volumeSeries;
    rsiSeriesRef.current = rsiSeries;
    rsiSignalSeriesRef.current = rsiSignalSeries;
    vwapSeriesRef.current = vwapSeries;

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      requestAnimationFrame(redrawCanvasOverlays);
    });

    chart.subscribeCrosshairMove((param) => {
      if (!tooltipRef.current || !chartContainerRef.current) return;
      if (param.point === undefined || !param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
        tooltipRef.current.style.display = "none";
        if (lastEma1Ref.current !== null) setLiveEma1Val(lastEma1Ref.current);
        if (lastEma2Ref.current !== null) setLiveEma2Val(lastEma2Ref.current);
        if (lastVolumeRef.current !== null) setLiveVolumeVal(lastVolumeRef.current);
        return;
      }
      const data = param.seriesData.get(candleSeries) as any;
      const volData = param.seriesData.get(volumeSeries) as any;
      const e1Data = param.seriesData.get(emaSeries) as any;
      const e2Data = param.seriesData.get(ema21Series) as any;
      const rData = param.seriesData.get(rsiSeries) as any;
      const rsData = param.seriesData.get(rsiSignalSeries) as any;

      if (e1Data && e1Data.value !== undefined) setLiveEma1Val(e1Data.value);
      if (e2Data && e2Data.value !== undefined) setLiveEma2Val(e2Data.value);
      if (rData && rData.value !== undefined) setLiveRsiVal(rData.value);
      if (rsData && rsData.value !== undefined) setLiveRsiSignalVal(rsData.value);
      if (volData && volData.value !== undefined) setLiveVolumeVal(volData.value);

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

    // Dynamic Resize using ResizeObserver (guarded against 0 dimensions when tab is hidden/minimized)
    const handleChartResize = (w: number, h: number) => {
      if (chartRef.current && w > 0 && h > 0) {
        chartRef.current.applyOptions({ width: w, height: h });
        requestAnimationFrame(redrawCanvasOverlays);
      }
    };

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || entries[0].target !== chartContainerRef.current) return;
      const newRect = entries[0].contentRect;
      handleChartResize(newRect.width, newRect.height);
    });
    resizeObserver.observe(chartContainerRef.current);

    const handleWindowResize = () => {
      if (chartContainerRef.current) {
        handleChartResize(chartContainerRef.current.clientWidth, chartContainerRef.current.clientHeight);
      }
    };
    window.addEventListener("resize", handleWindowResize);

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
      } else {
        if (animationFrameId === null) {
          syncCountdownPosition();
        }
        // Recalculate chart dimensions immediately upon tab regaining visibility
        handleWindowResize();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    if (!document.hidden) syncCountdownPosition();

    return () => {
      window.removeEventListener("resize", handleWindowResize);
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
      rsiSignalSeriesRef.current = null;
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

    // The engine's own entry signals for the candles on screen. One network
    // call; the engine decides, this only draws. A marker is snapped to the
    // nearest candle so it lands on a bar even if the clocks differ by seconds.
    const fetchStrategyMarkers = async (chartData: any[]): Promise<any[]> => {
      if (!chartData.length) return [];
      const firstTs = chartData[0].time as number;
      const lastTs = chartData[chartData.length - 1].time as number;
      const asDate = (epoch: number) => new Date(epoch * 1000).toISOString().split("T")[0];
      const url = `/api/strategy-markers?symbol=${encodeURIComponent(symbol)}`
        + `&start_date=${asDate(firstTs)}&end_date=${asDate(lastTs)}`
        + `&timeframe=${encodeURIComponent(timeframe)}`;
      const res = await fetch(url);
      if (!res.ok) return [];
      const json = await res.json();
      const raw: any[] = json?.markers || [];

      const times = chartData.map(c => c.time as number);
      return raw.map(m => {
        const target = Number(m.epoch);
        let snapped = times[0], best = Infinity;
        for (const t of times) {
          const diff = Math.abs(t - target);
          if (diff < best) { best = diff; snapped = t; }
        }
        const isPe = m.side === "PE";
        return {
          time: snapped as Time,
          position: isPe ? "aboveBar" : "belowBar",
          color: isPe ? "#EF4444" : "#10B981",
          shape: isPe ? "arrowDown" : "arrowUp",
          // body touch is the owner's preferred case; wick is the fallback
          text: m.touch === "wick" ? `${m.text}*` : m.text,
          size: 2,
        };
      });
    };

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

          // 2. Ask the ENGINE for its signals. Not recomputed here -- the bot's
          //    own rules (EMA cluster touch, RSI vs RSI-MA, ADX, entry window)
          //    decide, so what is drawn is what the bot would actually take.
          if (showAutoSignals && chartData.length > 20) {
            try {
              const sMarkers = await fetchStrategyMarkers(chartData);
              lastChartDataRef.current = chartData;
              void fetchRsiSmcOverlay(chartData);
              sMarkers.forEach(m => finalMarkers.push(m));
            } catch { /* markers are a view concern; never break the chart */ }
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

    const applyAllIndicatorData = (
      data: any[],
      cSeries: ISeriesApi<"Candlestick">,
      eSeries: ISeriesApi<"Line">,
      sSeries: ISeriesApi<"Line">
    ) => {
      const mSettings = manaSettingsRef.current;
      const smcLookback = mSettings.smc.swing_points_length || 50;
      const frvpBins = mSettings.frvp.num_bins || 50;
      const frvpValPct = mSettings.frvp.value_area_pct || 70;
      const rsiPer = mSettings.rsi.period || rsiLength || 14;
      const rsiSig = mSettings.rsi.ma_length || 20;

      const ema1Data = calculateEMA(data, ema1Length);
      const ema2Data = calculateEMA(data, ema2Length);
      const rsiResult = computeRSIWithSignal(data, rsiPer, rsiSig);
      const smcResult = computeSMC(data, Math.max(150, smcLookback * 3));
      const frvpResult = computeFRVP(data, frvpBins, frvpValPct);

      calculatedIndicatorsRef.current = { smc: smcResult, frvp: frvpResult };

      if (ema1Data.length > 0) setLiveEma1Val(ema1Data[ema1Data.length - 1].value);
      if (ema2Data.length > 0) setLiveEma2Val(ema2Data[ema2Data.length - 1].value);
      setLiveRsiVal(rsiResult.currentRsi);
      setLiveRsiSignalVal(rsiResult.currentSignal);
      if (data.length > 0 && data[data.length - 1].volume !== undefined) {
        const lastVol = Number(data[data.length - 1].volume) || 0;
        lastVolumeRef.current = lastVol;
        setLiveVolumeVal(lastVol);
      }

      const latestStructure = smcResult.structures[smcResult.structures.length - 1];
      const structPart = latestStructure ? ` • ${latestStructure.type}` : '';
      if (smcResult.bullishOrderBlocks.length > 0 || smcResult.bearishOrderBlocks.length > 0) {
        setSmcStatusText(`${smcResult.bullishOrderBlocks.length} Bull • ${smcResult.bearishOrderBlocks.length} Bear${structPart}`);
      } else {
        setSmcStatusText(`Active${structPart}`);
      }

      if (frvpResult.pocPrice > 0) {
        setFrvpStatusText(`POC ₹${frvpResult.pocPrice.toFixed(0)}`);
      }

      eSeries.setData(ema1Data);
      sSeries.setData(ema2Data);
      if (rsiSeriesRef.current) rsiSeriesRef.current.setData(rsiResult.rsiSeries as any);
      if (rsiSignalSeriesRef.current) rsiSignalSeriesRef.current.setData(rsiResult.signalSeries as any);

      seedIncrementalState(data, ema1Data, ema2Data);
      updateFrvpPriceLines();
      updateSmcPriceLines();
      requestAnimationFrame(redrawCanvasOverlays);
    };

    const fetchHistory = async () => {
      const cacheKey = `${symbol}_${timeframe}`;

      if (disableFetch && initialData) {
        const normalizedInitialData = sanitizeCandleSeries(initialData);
        chartDataCache[cacheKey] = normalizedInitialData;
        candleSeries.setData(normalizedInitialData);
        applyAllIndicatorData(normalizedInitialData, candleSeries, emaSeries, smaSeries);
        if (normalizedInitialData.length > 0) {
          lastCandleRef.current = normalizedInitialData[normalizedInitialData.length - 1];
          chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, normalizedInitialData.length - 150), to: normalizedInitialData.length + 15 });
        } else {
          chart.timeScale().fitContent();
        }
        setLoading(false);
        return;
      }

      if (chartDataCache[cacheKey]) {
        const cached = sanitizeCandleSeries(chartDataCache[cacheKey]);
        if (!isMounted) return;

        candleSeries.setData(cached);
        applyAllIndicatorData(cached, candleSeries, emaSeries, smaSeries);
        lastCandleRef.current = cached[cached.length - 1];
        chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, cached.length - 150), to: cached.length + 15 });
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
          applyAllIndicatorData(uniqueData, candleSeries, emaSeries, smaSeries);
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
            const lastVol = Number(uniqueData[uniqueData.length - 1].volume) || 0;
            liveBarVolRef.current = lastVol;
            lastVolumeRef.current = lastVol;
            setLiveVolumeVal(lastVol);
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
    const effHide = hideAllIndicators;

    // 1. Update visibility and styles on series immediately
    if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ visible: appliedIndicators.vol && showVolume && !effHide });
    if (rsiSeriesRef.current) rsiSeriesRef.current.applyOptions({ visible: appliedIndicators.rsi && showRsi && !effHide, color: rsiColor || "#A855F7", lineWidth: rsiLineWidth as any, lineStyle: rsiLineStyle as any });
    if (rsiSignalSeriesRef.current) rsiSignalSeriesRef.current.applyOptions({ visible: appliedIndicators.rsi && showRsi && !effHide });
    if (emaSeriesRef.current) emaSeriesRef.current.applyOptions({ visible: appliedIndicators.ema1 && showEma1 && !effHide, color: ema1Color, lineWidth: ema1LineWidth as any, lineStyle: ema1LineStyle as any, lastValueVisible: false });
    if (smaSeriesRef.current) smaSeriesRef.current.applyOptions({ visible: appliedIndicators.ema2 && showEma2 && !effHide, color: ema2Color, lineWidth: ema2LineWidth as any, lineStyle: ema2LineStyle as any, lastValueVisible: false });

    if (rsiObLineRef.current) rsiObLineRef.current.applyOptions({ price: rsiOverbought, axisLabelVisible: appliedIndicators.rsi && showRsi && !effHide });
    if (rsiOsLineRef.current) rsiOsLineRef.current.applyOptions({ price: rsiOversold, axisLabelVisible: appliedIndicators.rsi && showRsi && !effHide });
    if (vwapSeriesRef.current) vwapSeriesRef.current.applyOptions({ visible: showVwap && !effHide, color: vwapColor, lineWidth: vwapLineWidth as any, lastValueVisible: false });

    if (chartRef.current) {
      chartRef.current.priceScale('rsi').applyOptions({
        scaleMargins: appliedIndicators.rsi && showRsi && !effHide ? { top: 0.8, bottom: 0 } : { top: 1, bottom: 0 },
      });
    }

    updateFrvpPriceLines();
    updateSmcPriceLines();
    requestAnimationFrame(redrawCanvasOverlays);

    const cacheKey = `${symbol}_${timeframe}`;
    const cachedData = sanitizeCandleSeries(chartDataCache[cacheKey]);

    if (cachedData && cachedData.length > 0 && seriesRef.current) {
      // 2. Recalculate indicators
      const mSettings = manaSettingsRef.current;
      const smcLookback = mSettings.smc.swing_points_length || 50;
      const frvpBins = mSettings.frvp.num_bins || 50;
      const frvpValPct = mSettings.frvp.value_area_pct || 70;
      const rsiPer = mSettings.rsi.period || rsiLength || 14;
      const rsiSig = mSettings.rsi.ma_length || 20;

      const ema1Data = calculateEMA(cachedData, ema1Length);
      const ema2Data = calculateEMA(cachedData, ema2Length);
      const rsiResult = computeRSIWithSignal(cachedData, rsiPer, rsiSig);
      const smcResult = computeSMC(cachedData, Math.max(150, smcLookback * 3));
      const frvpResult = computeFRVP(cachedData, frvpBins, frvpValPct);
      lastChartDataRef.current = cachedData;
      calculatedIndicatorsRef.current = { smc: smcResult, frvp: frvpResult };

      if (ema1Data.length > 0) setLiveEma1Val(ema1Data[ema1Data.length - 1].value);
      if (ema2Data.length > 0) setLiveEma2Val(ema2Data[ema2Data.length - 1].value);
      setLiveRsiVal(rsiResult.currentRsi);
      setLiveRsiSignalVal(rsiResult.currentSignal);
      if (cachedData.length > 0 && cachedData[cachedData.length - 1].volume !== undefined) {
        const lastVol = Number(cachedData[cachedData.length - 1].volume) || 0;
        lastVolumeRef.current = lastVol;
        setLiveVolumeVal(lastVol);
      }

      const latestStructure = smcResult.structures[smcResult.structures.length - 1];
      const structPart = latestStructure ? ` • ${latestStructure.type}` : '';
      if (smcResult.bullishOrderBlocks.length > 0 || smcResult.bearishOrderBlocks.length > 0) {
        setSmcStatusText(`${smcResult.bullishOrderBlocks.length} Bull • ${smcResult.bearishOrderBlocks.length} Bear${structPart}`);
      } else {
        setSmcStatusText(`Active${structPart}`);
      }

      if (frvpResult.pocPrice > 0) {
        setFrvpStatusText(`POC ₹${frvpResult.pocPrice.toFixed(0)}`);
      }

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
      if (rsiSeriesRef.current) rsiSeriesRef.current.setData(rsiResult.rsiSeries as any);
      if (rsiSignalSeriesRef.current) rsiSignalSeriesRef.current.setData(rsiResult.signalSeries as any);
      seedIncrementalState(cachedData, ema1Data, ema2Data);

      updateFrvpPriceLines();
      updateSmcPriceLines();
      requestAnimationFrame(redrawCanvasOverlays);

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
    showEma1, showEma2, showSmc, showFrvp, hideAllIndicators,
    appliedIndicators,
    manaSettings,
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

  // Real-Time Incremental SMC Momentum Engine (Sub-millisecond latency)
  const updateLiveSMCState = (curCandle: any) => {
    const currentIndicators = calculatedIndicatorsRef.current;
    if (!currentIndicators.smc) return false;

    const smc = currentIndicators.smc;
    let changed = false;

    // 1. Dynamic Dealing Range Extension on live High/Low expansion
    if (curCandle.high > smc.rangeHigh) {
      smc.rangeHigh = curCandle.high;
      smc.equilibrium = (smc.rangeHigh + smc.rangeLow) / 2;
      if (smc.dealingRange) {
        smc.dealingRange.top = curCandle.high;
        smc.dealingRange.equilibrium = (smc.dealingRange.top + smc.dealingRange.bottom) / 2;
        smc.dealingRange.endTime = curCandle.time;
      }
      if (smc.weakHigh) {
        smc.weakHigh.price = curCandle.high;
        smc.weakHigh.time = curCandle.time;
      }
      changed = true;
    }

    if (curCandle.low < smc.rangeLow) {
      smc.rangeLow = curCandle.low;
      smc.equilibrium = (smc.rangeHigh + smc.rangeLow) / 2;
      if (smc.dealingRange) {
        smc.dealingRange.bottom = curCandle.low;
        smc.dealingRange.equilibrium = (smc.dealingRange.top + smc.dealingRange.bottom) / 2;
        smc.dealingRange.endTime = curCandle.time;
      }
      if (smc.weakLow) {
        smc.weakLow.price = curCandle.low;
        smc.weakLow.time = curCandle.time;
      }
      changed = true;
    }

    // 2. Real-Time Market Structure Break (CHoCH / BOS)
    if (smc.swingHighs.length > 0) {
      const nearestHigh = smc.swingHighs[smc.swingHighs.length - 1];
      const alreadyBroken = smc.structures.some((s) => s.startIndex === nearestHigh.index);
      if (!alreadyBroken && curCandle.close > nearestHigh.price) {
        const isChoch = smc.structures.length > 0 && !smc.structures[smc.structures.length - 1].isBullish;
        smc.structures.push({
          type: isChoch ? "CHoCH" : "BOS",
          isBullish: true,
          price: nearestHigh.price,
          startIndex: nearestHigh.index,
          startTime: nearestHigh.time,
          breakIndex: 999999,
          breakTime: curCandle.time,
        });
        changed = true;
      }
    }

    if (smc.swingLows.length > 0) {
      const nearestLow = smc.swingLows[smc.swingLows.length - 1];
      const alreadyBroken = smc.structures.some((s) => s.startIndex === nearestLow.index);
      if (!alreadyBroken && curCandle.close < nearestLow.price) {
        const isChoch = smc.structures.length > 0 && !smc.structures[smc.structures.length - 1].isBullish;
        smc.structures.push({
          type: isChoch ? "CHoCH" : "BOS",
          isBullish: false,
          price: nearestLow.price,
          startIndex: nearestLow.index,
          startTime: nearestLow.time,
          breakIndex: 999999,
          breakTime: curCandle.time,
        });
        changed = true;
      }
    }

    // 3. Real-Time Order Block Mitigation
    for (const ob of smc.bullishOrderBlocks) {
      if (!ob.mitigated && curCandle.low <= ob.top) {
        ob.mitigated = true;
        changed = true;
      }
    }
    for (const ob of smc.bearishOrderBlocks) {
      if (!ob.mitigated && curCandle.high >= ob.bottom) {
        ob.mitigated = true;
        changed = true;
      }
    }

    return changed;
  };

  // 3. Handle live price updates and auto-generate new candles
  useEffect(() => {
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
        } else if (timeframe.includes("30 Min")) {
          roundedMins = Math.floor(effectiveMins / 30) * 30;
        } else if (timeframe.includes("15 Min")) {
          roundedMins = Math.floor(effectiveMins / 15) * 15;
        } else {
          roundedMins = Math.floor(effectiveMins / tfVal) * tfVal;
        }

        const candleHour = Math.floor((9 * 60 + 15 + roundedMins) / 60);
        const candleMinute = (9 * 60 + 15 + roundedMins) % 60;
        currentCandleTime = istWallTimeToEpochSeconds(istNow.year, istNow.month, istNow.day, candleHour, candleMinute, 0);
      }

      // Check if this is the start of a new candle
      const isNewCandle = currentCandleTime > (lastCandle.time as number);

      let currentVol = 0;
      const tickDelta = liveVolume > 0 ? liveVolume : 1;

      let updatedCandle: any;

      if (isNewCandle) {
        // Create a new candle
        if (liveVolume && liveVolume > 0) {
          barStartVolRef.current = { time: currentCandleTime, vol: liveVolume };
          currentVol = 0;
        } else {
          currentVol = tickDelta;
        }
        liveBarVolRef.current = currentVol;

        // Dynamic live candle color
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
          time: currentCandleTime as Time,
          open: livePrice,
          high: livePrice,
          low: livePrice,
          close: livePrice,
          volume: currentVol,
          ...(liveColor ? { color: liveColor, wickColor: liveColor, borderColor: liveColor } : {})
        };
      } else {
        // Update the existing candle
        if (liveVolume && liveVolume > 0 && barStartVolRef.current.time === currentCandleTime && barStartVolRef.current.vol > 0) {
          const delta = liveVolume - barStartVolRef.current.vol;
          if (delta > 0) {
            currentVol = Math.max(lastCandle.volume || 0, delta);
          } else {
            currentVol = Math.max(lastCandle.volume || 0, liveBarVolRef.current) + tickDelta;
          }
        } else {
          currentVol = Math.max(lastCandle.volume || 0, liveBarVolRef.current) + tickDelta;
        }
        liveBarVolRef.current = currentVol;

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
          volume: currentVol,
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
          color: updatedCandle.close >= updatedCandle.open ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)'
        });
      }
      lastVolumeRef.current = updatedCandle.volume || 0;
      setLiveVolumeVal(updatedCandle.volume || 0);

      // Update indicators incrementally instead of recomputing over the
      // entire candle history on every single tick (previously O(n) per
      // tick via calculateEMA(cached, ...) on the whole array).
      const cacheKey = `${symbol}_${timeframe}`;
      const cached = chartDataCache[cacheKey] || [];
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
          // the last fully-closed bar's EMA
          const liveEma1 = lastEma1Ref.current !== null
            ? (updatedCandle.close - lastEma1Ref.current) * mult1 + lastEma1Ref.current
            : updatedCandle.close;
          emaSeriesRef.current.update({ time: updatedCandle.time, value: liveEma1 });
          setLiveEma1Val(liveEma1);

          // EMA2 (EMA 20): exponential moving average matching strategy
          const mult2 = 2 / (ema2Length + 1);
          if (cached[lastIdx].time !== updatedCandle.time) {
            lastEma2Ref.current = lastEma2Ref.current !== null
              ? (cached[lastIdx].close - lastEma2Ref.current) * mult2 + lastEma2Ref.current
              : cached[lastIdx].close;
          }
          const liveEma2 = lastEma2Ref.current !== null
            ? (updatedCandle.close - lastEma2Ref.current) * mult2 + lastEma2Ref.current
            : updatedCandle.close;
          smaSeriesRef.current.update({ time: updatedCandle.time, value: liveEma2 });
          setLiveEma2Val(liveEma2);
        }
      }

      // 4. Real-time Live SMC Momentum Detection
      const smcChanged = updateLiveSMCState(updatedCandle);
      if (smcChanged) {
        updateSmcPriceLines();
      }

      // 5. 60FPS Throttled Overlay Redraw (Better than TradingView latency)
      if (rafOverlayIdRef.current === null) {
        rafOverlayIdRef.current = requestAnimationFrame(() => {
          redrawCanvasOverlays();
          rafOverlayIdRef.current = null;
        });
      }
    }
  }, [livePrice, liveVolume, timeframe, lastTick, ema1Length, ema2Length]);

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

      {/* Mana Institutional Indicators Legend (Interactive - Click to Open Settings, Toggle Visibility, or Remove via X) */}
      <div className="absolute top-8 left-4 z-20 pointer-events-auto flex flex-col gap-1 select-none max-w-[340px]">
        {/* Master Toolbar Header: Indicators Count, Add fx, Restore, Hide All, Expand/Collapse */}
        <div className="flex items-center justify-between px-2 py-0.5 rounded bg-background/70 backdrop-blur-md border border-border/40 text-[10px] text-muted-foreground w-fit gap-1.5 shadow-sm transition-all">
          <div
            onClick={handleToggleCollapseAll}
            className="flex items-center gap-1.5 cursor-pointer hover:text-foreground transition-colors group"
            title={collapseAllIndicators ? "Click to Expand All Indicators" : "Click to Collapse All Indicators"}
          >
            <span className="font-semibold uppercase tracking-wider text-[9px] text-foreground/80 group-hover:text-primary transition-colors">Indicators</span>
            <span className="text-[9px] px-1 py-0.2 rounded bg-muted/60 text-muted-foreground font-mono font-medium">{activeAppliedCount}</span>
            {collapseAllIndicators && (
              <div className="flex items-center gap-1 ml-0.5 animate-in fade-in duration-200">
                {appliedIndicators.ema1 && showEma1 && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ema1Color }} title={`EMA ${ema1Length}`} />}
                {appliedIndicators.ema2 && showEma2 && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ema2Color }} title={`EMA ${ema2Length}`} />}
                {appliedIndicators.smc && showSmc && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" title="SMC Pro" />}
                {appliedIndicators.frvp && showFrvp && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="FRVP" />}
                {appliedIndicators.rsi && showRsi && <span className="w-1.5 h-1.5 rounded-full bg-purple-400" title="MDE Pro" />}
                {appliedIndicators.vol && showVolume && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" title="Volume" />}
              </div>
            )}
          </div>

          <div className="h-3 w-px bg-border/40" />

          {/* Quick Add Indicators Button */}
          <button
            type="button"
            onClick={() => setShowManaIndicatorsModal(true)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded transition-all text-[9.5px] font-medium hover:text-primary hover:bg-muted/40 text-muted-foreground"
            title="Open Indicators Directory (fx) to Add Indicators"
          >
            <Plus size={11} />
            <span>Add</span>
          </button>

          {/* If any indicator was removed, provide a quick one-click Restore button */}
          {activeAppliedCount < 6 && (
            <button
              type="button"
              onClick={handleResetAllIndicators}
              className="flex items-center gap-0.5 px-1.5 py-0.5 rounded transition-all text-[9.5px] font-medium text-primary hover:bg-primary/10"
              title="Restore / Re-apply All 6 Indicators"
            >
              <RefreshCw size={9} />
              <span>Restore</span>
            </button>
          )}

          <div className="h-3 w-px bg-border/40" />

          {/* Hide All / Show All on Chart */}
          <button
            type="button"
            onClick={() => setHideAllIndicators(!hideAllIndicators)}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-all text-[9.5px] font-medium ${
              hideAllIndicators
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/40 shadow-sm"
                : "hover:text-foreground hover:bg-muted/40 text-muted-foreground"
            }`}
            title={hideAllIndicators ? "Show All Indicators" : "Hide All Indicators (Disturbance-Free Raw Price Action)"}
          >
            {hideAllIndicators ? (
              <>
                <EyeOff size={11} className="text-amber-400" />
                <span>Hidden</span>
              </>
            ) : (
              <>
                <Eye size={11} />
                <span>Hide All</span>
              </>
            )}
          </button>

          {/* Expand All / Collapse All Toggle Button */}
          <button
            type="button"
            onClick={handleToggleCollapseAll}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-all text-[9.5px] font-medium ${
              collapseAllIndicators
                ? "bg-primary/20 text-primary border border-primary/40 shadow-xs hover:bg-primary/30"
                : "hover:text-foreground hover:bg-muted/40 text-muted-foreground"
            }`}
            title={collapseAllIndicators ? "Expand All Indicators" : "Collapse All Indicators"}
          >
            {collapseAllIndicators ? (
              <>
                <ChevronDown size={11} className="text-primary" />
                <span>Expand All</span>
              </>
            ) : (
              <>
                <ChevronUp size={11} />
                <span>Collapse All</span>
              </>
            )}
          </button>
        </div>

        {/* Indicator Badges (Collapsed when collapseAllIndicators is true) */}
        {!collapseAllIndicators && (
          <div className="flex flex-col gap-1 animate-in fade-in slide-in-from-top-1 duration-150">
            {/* 1. EMA 9 */}
            {appliedIndicators.ema1 && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showEma1 || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to configure EMA 1"
              >
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => handleOpenEmaSettings('ema1')}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ema1Color }}></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    EMA {ema1Length}
                    {liveEma1Val !== null && showEma1 && !hideAllIndicators && (
                      <span className="text-[9.5px] font-mono text-muted-foreground font-normal ml-0.5">
                        ₹{liveEma1Val.toFixed(2)}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowEma1(!showEma1);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showEma1 ? "Hide EMA" : "Show EMA"}
                  >
                    {showEma1 && !hideAllIndicators ? <Eye size={11} style={{ color: ema1Color }} /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenEmaSettings('ema1');
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure EMA 1"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('ema1');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove EMA 1"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* 2. EMA 20 */}
            {appliedIndicators.ema2 && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showEma2 || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to configure EMA 2"
              >
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => handleOpenEmaSettings('ema2')}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ema2Color }}></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    EMA {ema2Length}
                    {liveEma2Val !== null && showEma2 && !hideAllIndicators && (
                      <span className="text-[9.5px] font-mono text-muted-foreground font-normal ml-0.5">
                        ₹{liveEma2Val.toFixed(2)}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowEma2(!showEma2);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showEma2 ? "Hide EMA" : "Show EMA"}
                  >
                    {showEma2 && !hideAllIndicators ? <Eye size={11} style={{ color: ema2Color }} /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenEmaSettings('ema2');
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure EMA 2"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('ema2');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove EMA 2"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* 3. SMC Pro Indicator */}
            {appliedIndicators.smc && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showSmc || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to open SMC Pro Settings"
              >
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => setActiveIndicatorModal("smc")}>
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    SMC Pro <span className="text-[9px] text-emerald-400 font-mono">[Structure]</span>
                    {showSmc && !hideAllIndicators && smcStatusText && (
                      <span className="text-[9px] text-emerald-400/80 font-mono ml-0.5">{smcStatusText}</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowSmc(!showSmc);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showSmc ? "Hide Indicator" : "Show Indicator"}
                  >
                    {showSmc && !hideAllIndicators ? <Eye size={11} className="text-emerald-400" /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveIndicatorModal("smc");
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure Parameters"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('smc');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove SMC Pro"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}


            {/* 3b. RSI_SMC engine overlay */}
            {appliedIndicators.rsiSmc && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showRsiSmc || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="RSI_SMC_OPTIONS_BUYER_V1 — served by the engine. Analytical view. Strategy is inactive."
              >
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400"></span>
                  <span className="text-foreground/90 font-semibold flex items-center gap-1 text-[10.5px]">
                    RSI SMC
                    <span className="text-[9px] text-violet-400 font-mono">[RSI_SMC_OPTIONS_BUYER_V1]</span>
                    <span className="text-[8.5px] text-amber-400/90 font-mono border border-amber-400/40 rounded px-1">ANALYTICAL</span>
                    {showRsiSmc && !hideAllIndicators && rsiSmcStatusText && (
                      <span className="text-[9px] text-violet-400/80 font-mono ml-0.5">{rsiSmcStatusText}</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setShowRsiSmc(!showRsiSmc); }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showRsiSmc ? "Hide Indicator" : "Show Indicator"}
                  >
                    {showRsiSmc ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleRemoveIndicator('rsiSmc'); }}
                    className="p-0.5 hover:text-red-400 text-muted-foreground rounded"
                    title="Remove Indicator"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              </div>
            )}
            {/* 4. FRVP Indicator */}
            {appliedIndicators.frvp && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showFrvp || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to open FRVP Settings"
              >
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => setActiveIndicatorModal("frvp")}>
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    FRVP <span className="text-[9px] text-amber-400 font-mono">[Range]</span>
                    {showFrvp && !hideAllIndicators && frvpStatusText && (
                      <span className="text-[9px] text-amber-400/80 font-mono ml-0.5">{frvpStatusText}</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowFrvp(!showFrvp);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showFrvp ? "Hide Indicator" : "Show Indicator"}
                  >
                    {showFrvp && !hideAllIndicators ? <Eye size={11} className="text-amber-400" /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveIndicatorModal("frvp");
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure Parameters"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('frvp');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove FRVP"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* 5. MDE Pro Indicator */}
            {appliedIndicators.rsi && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showRsi || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to open MDE Pro Settings"
              >
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => setActiveIndicatorModal("rsi")}>
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    MDE Pro <span className="text-[9px] text-purple-400 font-mono">[{rsiLength}, 20]</span>
                    {showRsi && !hideAllIndicators && liveRsiVal !== null && (
                      <span className="text-[9px] text-purple-400 font-mono ml-0.5">
                        {liveRsiVal.toFixed(1)}
                        {liveRsiSignalVal !== null && <span className="text-amber-400 ml-1">({liveRsiSignalVal.toFixed(1)})</span>}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowRsi(!showRsi);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showRsi ? "Hide Indicator" : "Show Indicator"}
                  >
                    {showRsi && !hideAllIndicators ? <Eye size={11} className="text-purple-400" /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveIndicatorModal("rsi");
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure Parameters"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('rsi');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove MDE Pro"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* 6. Volume Indicator */}
            {appliedIndicators.vol && (
              <div
                className={`group flex items-center justify-between gap-2 px-2 py-0.5 rounded bg-background/70 hover:bg-background/95 backdrop-blur-md border border-border/40 text-[11px] font-medium shadow-sm transition-all hover:border-primary/50 w-fit ${
                  !showVolume || hideAllIndicators ? "opacity-50" : ""
                }`}
                title="Click to configure Volume"
              >
                <div
                  className="flex items-center gap-1.5 cursor-pointer"
                  onClick={() => {
                    setActiveTab('indicators');
                    setActiveAccordion('vol');
                    setShowSettings(true);
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  <span className="text-foreground/90 font-semibold group-hover:text-primary transition-colors flex items-center gap-1 text-[10.5px]">
                    Volume <span className="text-[9px] text-cyan-400 font-mono">[Vol]</span>
                    {liveVolumeVal !== null && showVolume && !hideAllIndicators && (
                      <span className="text-[9.5px] font-mono text-cyan-400/90 font-normal ml-0.5">
                        {formatVolumeVal(liveVolumeVal)}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity ml-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowVolume(!showVolume);
                    }}
                    className="p-0.5 hover:text-foreground text-muted-foreground rounded"
                    title={showVolume ? "Hide Volume" : "Show Volume"}
                  >
                    {showVolume && !hideAllIndicators ? <Eye size={11} className="text-cyan-400" /> : <EyeOff size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveTab('indicators');
                      setActiveAccordion('vol');
                      setShowSettings(true);
                    }}
                    className="p-0.5 hover:text-primary text-muted-foreground rounded"
                    title="Configure Volume"
                  >
                    <Settings2 size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveIndicator('vol');
                    }}
                    className="p-0.5 hover:text-destructive hover:bg-destructive/10 text-muted-foreground rounded transition-colors"
                    title="Remove Volume"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* Zero state: when user removed all indicators via X button */}
            {activeAppliedCount === 0 && (
              <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-background/70 backdrop-blur-md border border-border/40 text-[10.5px] text-muted-foreground shadow-sm">
                <span>No indicators applied</span>
                <button
                  type="button"
                  onClick={() => setShowManaIndicatorsModal(true)}
                  className="text-primary hover:underline font-semibold flex items-center gap-0.5"
                >
                  <Plus size={11} /> Add
                </button>
              </div>
            )}
          </div>
        )}
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

      {/* Chart Toolbar: Reset Zoom / fx Indicators / Toggle Markers / Export / Settings (Hidden by default to avoid bottom overlap) */}
      {!hideBottomToolbar && (
        <div className="absolute bottom-1 right-2 z-20 flex items-center gap-1.5">
          {/* Mana Indicators fx Button */}
          <div className="relative pointer-events-auto">
            <button
              onClick={() => setShowManaIndicatorsModal(true)}
              className="p-1.5 sm:px-2.5 sm:py-1 rounded-full transition-all shadow-lg border backdrop-blur-md flex items-center justify-center hover:scale-105 active:scale-95 text-xs font-bold gap-1 bg-background/90 hover:bg-background text-muted-foreground hover:text-foreground border-border/40"
              title="Mana Indicators (fx)"
            >
              <span className="font-serif italic font-black text-xs text-primary">fx</span>
              <span className="hidden sm:inline text-[11px] font-semibold">Indicators</span>
            </button>
          </div>

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
      )}

      {/* TradingView Indicator Settings Modal (Opened on indicator click) */}
      <TradingViewIndicatorModal
        isOpen={activeIndicatorModal !== null}
        indicator={activeIndicatorModal}
        onClose={() => setActiveIndicatorModal(null)}
        onSave={(ind, updatedSettings) => {
          setManaSettings(updatedSettings);
          manaSettingsRef.current = updatedSettings;
        }}
      />

      {/* Mana Indicators Directory Modal */}
      {showManaIndicatorsModal && (
        <IndicatorSettings
          isModal={true}
          onClose={() => setShowManaIndicatorsModal(false)}
        />
      )}

      <div ref={chartContainerRef} className="w-full h-full min-h-[450px] absolute inset-0 z-0" />
      <canvas
        ref={overlayCanvasRef}
        className="w-full h-full min-h-[450px] absolute inset-0 z-10 pointer-events-none"
      />
    </div>
  );
}
