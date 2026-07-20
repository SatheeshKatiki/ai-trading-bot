"use client";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode, createSeriesMarkers } from "lightweight-charts";
import { RefreshCw, Eye, EyeOff } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useChartSettingsStore } from "@/store/useChartSettingsStore";
import { Settings2, X, ChevronDown } from "lucide-react";

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

// Helper to check if Indian market is open
function isMarketOpen() {
  const now = new Date();
  const options = { timeZone: 'Asia/Kolkata', hour12: false, hour: 'numeric', minute: 'numeric', weekday: 'short' } as const;
  const formatter = new Intl.DateTimeFormat('en-US', options);
  const parts = formatter.formatToParts(now);

  const hourStr = parts.find(p => p.type === 'hour')?.value || '0';
  const minStr = parts.find(p => p.type === 'minute')?.value || '0';
  const weekday = parts.find(p => p.type === 'weekday')?.value || '';

  if (weekday === 'Sat' || weekday === 'Sun') return false;

  const hour = parseInt(hourStr, 10);
  const minute = parseInt(minStr, 10);

  const currentMins = hour * 60 + minute;
  return currentMins >= 555 && currentMins < 930; // 09:15 AM to 03:30 PM IST
}

interface NativeChartProps {
  symbol: string;
  livePrice?: number;
  timeframe?: string;
  initialData?: any[];
  disableFetch?: boolean;
  showDynamicTrend?: boolean;
  lastTick?: number;
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

export default function NativeChart({ symbol, livePrice, timeframe = "5 Min", initialData, disableFetch, lastTick = 0 }: NativeChartProps) {
  const { theme } = useTheme();
  
  const {
    ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
    ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
    showVolume, showRsi, rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
    showSmartTrend, bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor,
    
    setEma1Length, setEma1Color, setEma1LineWidth, setEma1LineStyle,
    setEma2Length, setEma2Color, setEma2LineWidth, setEma2LineStyle,
    setShowVolume, setShowRsi, setRsiLength, setRsiColor, setRsiLineWidth, setRsiLineStyle, setRsiOverbought, setRsiOversold,
    setShowSmartTrend, setBullishSurgeColor, setBearishSurgeColor, setBullishNormalColor, setBearishNormalColor, setChopColor
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
  const tooltipRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<HTMLDivElement>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<string>("");
  const [lastCandleOpen, setLastCandleOpen] = useState<number | null>(null);
  const [showMarkers, setShowMarkers] = useState(true);

  const lastCandleRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const seriesMarkersPluginRef = useRef<any>(null);
  const initialSettingsRef = useRef<any>(null);

  const handleOpenSettings = () => {
    initialSettingsRef.current = {
      ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
      ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
      showVolume, showRsi, rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
      showSmartTrend, bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor
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
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)" },
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

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    emaSeriesRef.current = emaSeries;
    smaSeriesRef.current = ema21Series;
    volumeSeriesRef.current = volumeSeries;
    rsiSeriesRef.current = rsiSeries;

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
        const offset = new Date().getTimezoneOffset() * 60;
        const trueUnixTime = (param.time as number) + offset;
        const date = new Date(trueUnixTime * 1000);
        const timeStr = date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
        // Create YYYY-MM-DD format based on local time
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const dateStr = `${year}-${month}-${day}`;
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

    // Sync countdown position to price line dynamically
    let animationFrameId: number;
    const syncCountdownPosition = () => {
      if (countdownRef.current && seriesRef.current && lastCandleRef.current) {
        const y = seriesRef.current.priceToCoordinate(lastCandleRef.current.close);
        if (y !== null) {
          countdownRef.current.style.top = `${y + 12}px`;
        }
      }
      animationFrameId = requestAnimationFrame(syncCountdownPosition);
    };
    syncCountdownPosition();

    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      seriesMarkersPluginRef.current = null;
      emaSeriesRef.current = null;
      smaSeriesRef.current = null;
      volumeSeriesRef.current = null;
      rsiSeriesRef.current = null;
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
        // Use Next.js proxy
        const stateRes = await fetch(`/api/state`);
        if (!isMounted) return;
        if (stateRes.ok) {
          const stateData = await stateRes.json();
          if (stateData.trades && stateData.trades.length > 0) {
            const markers: any[] = [];
            const symClean = symbol.split(':')[1] || symbol;
            const symbolTrades = stateData.trades.filter((t: any) => t.symbol && t.symbol.toUpperCase().includes(symClean.toUpperCase()));

            symbolTrades.forEach((trade: any) => {
              const dateStr = String(trade.entry_time || trade.time);
              if (!dateStr || dateStr === "undefined" || dateStr === "null") return;
              const safeDateStr = dateStr.includes(' ') ? dateStr.replace(' ', 'T') : dateStr;
              const d = new Date(safeDateStr);
              // Calculate adjusted time for marker
              const offset = d.getTimezoneOffset() * 60;
              const trueTime = Math.floor(d.getTime() / 1000);
              const adjustedTime = trueTime - offset;

              let closestTime = adjustedTime as Time;
              let minDiff = Infinity;
              for (const candle of chartData) {
                const diff = Math.abs((candle.time as number) - (adjustedTime as number));
                if (diff < minDiff) { minDiff = diff; closestTime = candle.time; }
              }
              if (trade.type === 'CALL BUY' || trade.type === 'BUY') {
                markers.push({ time: closestTime, position: 'belowBar', color: '#10B981', shape: 'arrowUp', text: 'Buy' });
              } else if (trade.type === 'PUT BUY' || trade.type === 'SELL') {
                markers.push({ time: closestTime, position: 'aboveBar', color: '#EF4444', shape: 'arrowDown', text: 'Sell' });
              }
            });
            markers.sort((a, b) => (a.time as number) - (b.time as number));
            if (!isMounted) return;
            markersRef.current = markers;
            if (showMarkers && seriesMarkersPluginRef.current) {
              seriesMarkersPluginRef.current.setMarkers(markers);
            }
          }
        }
      } catch (e: any) {
        console.warn("Error fetching markers (Backend offline?):", e.message);
      }
    };

    const fetchHistory = async () => {
      if (disableFetch && initialData) {
        candleSeries.setData(initialData);
        emaSeries.setData(calculateEMA(initialData, ema1Length));
        smaSeries.setData(calculateSMA(initialData, ema2Length));
        if (initialData.length > 0) {
          lastCandleRef.current = initialData[initialData.length - 1];
          chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, initialData.length - 150), to: initialData.length });
        } else {
          chart.timeScale().fitContent();
        }
        setLoading(false);
        return;
      }

      const cacheKey = `${symbol}_${timeframe}`;

      if (chartDataCache[cacheKey]) {
        const cached = chartDataCache[cacheKey];
        if (!isMounted) return;
        
        let dataToSet = cached;
        const ema1Data = calculateEMA(cached, ema1Length);
        const ema2Data = calculateSMA(cached, ema2Length);
        
        if (showSmartTrend) {
           // We will let the dedicated settings useEffect handle the deep coloring, 
           // but for instant load we just set base data and let the other hook color it
        }

        candleSeries.setData(cached);
        emaSeries.setData(ema1Data);
        smaSeries.setData(ema2Data);
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

        const formattedData = json.data.map((item: any) => {
          const dateStr = String(item.datetime || item.Datetime || item.date);
          const safeDateStr = dateStr.includes(' ') ? dateStr.replace(' ', 'T') : dateStr;
          const date = new Date(safeDateStr);
          // Apply timezone offset adjustment
          const offset = date.getTimezoneOffset() * 60;
          const time = (Math.floor(date.getTime() / 1000) - offset) as Time;
          return {
            time, open: parseFloat(item.open || item.Open), high: parseFloat(item.high || item.High),
            low: parseFloat(item.low || item.Low), close: parseFloat(item.close || item.Close),
            volume: parseFloat(item.volume || item.Volume || 0)
          };
        }).sort((a: any, b: any) => (a.time as number) - (b.time as number));

        const uniqueData = [];
        const seenTimes = new Set();
        for (const item of formattedData) {
          if (!seenTimes.has(item.time)) { seenTimes.add(item.time); uniqueData.push(item); }
        }

        if (uniqueData.length > 0) {
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
                // Squeeze / Chop Phase
                customColor = chopColor;
              } else if (isHighVolume && d.close > ema1) {
                // Bullish Institutional Surge
                customColor = bullishSurgeColor;
              } else if (isHighVolume && d.close < ema1) {
                // Bearish Institutional Surge
                customColor = bearishSurgeColor;
              } else if (d.close >= ema1) {
                // Normal Bullish Trend
                customColor = d.close >= d.open ? bullishNormalColor : "#059669";
              } else {
                // Normal Bearish Trend
                customColor = d.close < d.open ? bearishNormalColor : "#991B1B";
              }
              return { ...d, color: customColor, wickColor: customColor, borderColor: customColor };
            });
          }

          candleSeries.setData(dataToSet);
          emaSeries.setData(ema1Data);
          smaSeries.setData(ema2Data);
          if (rsiSeriesRef.current) rsiSeriesRef.current.setData(rsiData);

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
            chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, uniqueData.length - 150), to: uniqueData.length });
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

    return () => {
      isMounted = false;
    };
  }, [symbol, timeframe]); // We removed showSmartTrend here because we have a dedicated hook now

  // 2b. Handle Chart Settings Changes Dynamically (No refetch)
  useEffect(() => {
    const cacheKey = `${symbol}_${timeframe}`;
    const cachedData = chartDataCache[cacheKey];

    if (cachedData && cachedData.length > 0 && seriesRef.current) {
      // 1. Update visibility and styles
      if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ visible: showVolume });
      if (rsiSeriesRef.current) rsiSeriesRef.current.applyOptions({ visible: showRsi, color: rsiColor, lineWidth: rsiLineWidth as any, lineStyle: rsiLineStyle as any });
      if (emaSeriesRef.current) emaSeriesRef.current.applyOptions({ color: ema1Color, lineWidth: ema1LineWidth as any, lineStyle: ema1LineStyle as any });
      if (smaSeriesRef.current) smaSeriesRef.current.applyOptions({ color: ema2Color, lineWidth: ema2LineWidth as any, lineStyle: ema2LineStyle as any });

      if (rsiObLineRef.current) rsiObLineRef.current.applyOptions({ price: rsiOverbought });
      if (rsiOsLineRef.current) rsiOsLineRef.current.applyOptions({ price: rsiOversold });

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
      
      // Update the last candle ref so live ticks don't revert colors immediately
      lastCandleRef.current = dataToSet[dataToSet.length - 1];
    }
  }, [
    ema1Length, ema1Color, ema1LineWidth, ema1LineStyle,
    ema2Length, ema2Color, ema2LineWidth, ema2LineStyle,
    rsiLength, rsiColor, rsiLineWidth, rsiLineStyle, rsiOverbought, rsiOversold,
    showVolume, showRsi, showSmartTrend,
    bullishSurgeColor, bearishSurgeColor, bullishNormalColor, bearishNormalColor, chopColor,
    symbol, timeframe
  ]);

  // 2c. Handle Marker Toggle without refetching
  useEffect(() => {
    if (seriesMarkersPluginRef.current) {
      seriesMarkersPluginRef.current.setMarkers(showMarkers ? markersRef.current : []);
    }
  }, [showMarkers]);

  // 3. Handle live price updates and auto-generate new candles
  useEffect(() => {
    // Stop updating the chart if market is closed (prevents fake candles in paper mode after hours)
    if (!isMarketOpen()) return;

    if (livePrice && livePrice > 0 && seriesRef.current && lastCandleRef.current) {
      const lastCandle = lastCandleRef.current;

      const now = new Date();

      // Calculate exact candle start time aligned to Indian Market Open (09:15)
      const tfVal = parseInt(timeframe.split(' ')[0] || "5");
      let currentCandleTime: number;

      if (timeframe.includes("Day")) {
        const d = new Date(now);
        d.setHours(0, 0, 0, 0);
        currentCandleTime = Math.floor(d.getTime() / 1000);
      } else {
        const minutesSinceMidnight = now.getHours() * 60 + now.getMinutes();
        const minutesSinceOpen = minutesSinceMidnight - (9 * 60 + 15);
        const effectiveMins = Math.max(0, minutesSinceOpen);

        let roundedMins = 0;
        if (timeframe.includes("Hour")) {
          roundedMins = Math.floor(effectiveMins / 60) * 60;
        } else {
          roundedMins = Math.floor(effectiveMins / tfVal) * tfVal;
        }

        const d = new Date(now);
        d.setHours(9, 15 + roundedMins, 0, 0);
        // Adjust live candle time for lightweight charts timezone
        const offset = d.getTimezoneOffset() * 60;
        currentCandleTime = Math.floor(d.getTime() / 1000) - offset;
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

      // Update EMAs dynamically
      const cacheKey = `${symbol}_${timeframe}`;
      const cached = chartDataCache[cacheKey];
      if (cached && emaSeriesRef.current && smaSeriesRef.current) {
        const lastIdx = cached.length - 1;
        if (lastIdx >= 0) {
          if (cached[lastIdx].time === updatedCandle.time) {
            cached[lastIdx] = updatedCandle;
          } else {
            cached.push(updatedCandle);
          }
          const ema9 = calculateEMA(cached, 9);
          const ema21 = calculateEMA(cached, 21);
          emaSeriesRef.current.update(ema9[ema9.length - 1]);
          smaSeriesRef.current.update(ema21[ema21.length - 1]);
        }
      }

    }
  }, [livePrice, timeframe, lastTick]);

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

      {/* Settings Gear Icon at Bottom Right */}
      <div className="absolute bottom-1 right-2 z-20">
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
