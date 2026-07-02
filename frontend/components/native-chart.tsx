"use client";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode } from "lightweight-charts";
import { RefreshCw } from "lucide-react";

// Simple EMA function
function calculateEMA(data: any[], period: number) {
  const result = [];
  const multiplier = 2 / (period + 1);
  let prevEMA = 0;

  for (let i = 0; i < data.length; i++) {
    const close = data[i].close;
    if (i === 0) {
      prevEMA = close;
      result.push({ time: data[i].time, value: prevEMA });
    } else {
      const ema = (close - prevEMA) * multiplier + prevEMA;
      result.push({ time: data[i].time, value: ema });
      prevEMA = ema;
    }
  }
  return result;
}

// Simple SMA function
function calculateSMA(data: any[], period: number) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push({ time: data[i].time, value: data[i].close }); // fallback for early periods
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close;
    }
    result.push({ time: data[i].time, value: sum / period });
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
}

// Global cache outside component to persist across unmounts
const chartDataCache: Record<string, any> = {};

export default function NativeChart({ symbol, livePrice, timeframe = "5 Min", initialData, disableFetch }: NativeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<string>("");
  const [lastCandleOpen, setLastCandleOpen] = useState<number | null>(null);
  
  const lastCandleRef = useRef<any>(null);

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

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#9CA3AF" },
      grid: { vertLines: { color: "rgba(255, 255, 255, 0.03)" }, horzLines: { color: "rgba(255, 255, 255, 0.03)" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "rgba(255, 255, 255, 0.1)" },
      rightPriceScale: { borderColor: "rgba(255, 255, 255, 0.1)", autoScale: true },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(255, 255, 255, 0.2)", style: 3, labelBackgroundColor: "#1E293B" },
        horzLine: { color: "rgba(255, 255, 255, 0.2)", style: 3, labelBackgroundColor: "#1E293B" },
      },
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // set as an overlay by setting a blank priceScaleId
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981", downColor: "#EF4444", borderVisible: false,
      wickUpColor: "#10B981", wickDownColor: "#EF4444",
    });

    const emaSeries = chart.addSeries(LineSeries, { color: '#3B82F6', lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });
    const ema21Series = chart.addSeries(LineSeries, { color: '#F59E0B', lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    emaSeriesRef.current = emaSeries;
    smaSeriesRef.current = ema21Series;
    volumeSeriesRef.current = volumeSeries;

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
        const date = new Date((param.time as number) * 1000);
        const timeStr = date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
        // Create YYYY-MM-DD format based on local time
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const dateStr = `${year}-${month}-${day}`;
        const volumeStr = volData && volData.value ? (volData.value >= 1000000 ? (volData.value / 1000000).toFixed(2) + 'M' : (volData.value / 1000).toFixed(2) + 'K') : '---';
        
        tooltipRef.current.innerHTML = `
          <div class="font-display font-bold text-foreground mb-1.5 flex items-center gap-2">
            <span class="text-primary">${symbol.split(":")[1] || symbol}</span>
            <span class="text-muted-foreground font-mono text-xs">${dateStr} ${timeStr}</span>
          </div>
          <div class="flex gap-4 font-mono text-[11px] tracking-tight backdrop-blur-md bg-black/40 p-1.5 rounded-lg border border-white/5">
            <div class="flex flex-col"><span class="text-muted-foreground mb-0.5">O</span><span class="text-foreground font-medium">${data.open.toFixed(2)}</span></div>
            <div class="flex flex-col"><span class="text-muted-foreground mb-0.5">H</span><span class="text-success font-medium">${data.high.toFixed(2)}</span></div>
            <div class="flex flex-col"><span class="text-muted-foreground mb-0.5">L</span><span class="text-destructive font-medium">${data.low.toFixed(2)}</span></div>
            <div class="flex flex-col"><span class="text-muted-foreground mb-0.5">C</span><span class="text-foreground font-medium">${data.close.toFixed(2)}</span></div>
            <div class="flex flex-col border-l border-white/10 pl-4 ml-2"><span class="text-muted-foreground mb-0.5">Vol</span><span class="text-info font-medium">${volumeStr}</span></div>
          </div>
        `;
      }
    });

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
      }
    };
    window.addEventListener("resize", handleResize);
    const resizeTimeout = setTimeout(handleResize, 50);

    return () => {
      clearTimeout(resizeTimeout);
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chart.remove();
      }
      chartRef.current = null;
      seriesRef.current = null;
      emaSeriesRef.current = null;
      smaSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []); // Run only ONCE on mount

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
        const hostname = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
        const backendUrl = typeof window !== 'undefined' ? `http://${hostname}:8000` : 'http://127.0.0.1:8000';
        const stateRes = await fetch(`${backendUrl}/api/state`);
        if (!isMounted) return;
        if (stateRes.ok) {
          const stateData = await stateRes.json();
          if (stateData.trades && stateData.trades.length > 0) {
            const markers: any[] = [];
            const symbolTrades = stateData.trades.filter((t: any) => t.symbol === symbol);
            
            symbolTrades.forEach((trade: any) => {
               const dateStr = String(trade.entry_time || trade.time);
               if (!dateStr || dateStr === "undefined" || dateStr === "null") return;
               const safeDateStr = dateStr.includes(' ') ? dateStr.replace(' ', 'T') : dateStr;
               const date = new Date(safeDateStr);
               const time = Math.floor(date.getTime() / 1000) as Time;
               let closestTime = time;
               let minDiff = Infinity;
               for (const candle of chartData) {
                  const diff = Math.abs((candle.time as number) - (time as number));
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
            (cSeries as any).setMarkers(markers);
          }
        }
      } catch (e: any) {
        console.warn("Error fetching markers (Backend offline?):", e.message);
      }
    };

    const fetchHistory = async () => {
      if (disableFetch && initialData) {
        candleSeries.setData(initialData);
        emaSeries.setData(calculateEMA(initialData, 9));
        smaSeries.setData(calculateEMA(initialData, 21));
        if (initialData.length > 0) {
          lastCandleRef.current = initialData[initialData.length - 1];
        }
        chart.timeScale().fitContent();
        setLoading(false);
        return;
      }

      const cacheKey = `${symbol}_${timeframe}`;
      
      if (chartDataCache[cacheKey]) {
         const cached = chartDataCache[cacheKey];
         if (!isMounted) return;
         candleSeries.setData(cached);
         emaSeries.setData(calculateEMA(cached, 9));
         smaSeries.setData(calculateEMA(cached, 21));
         lastCandleRef.current = cached[cached.length - 1];
         chart.timeScale().fitContent();
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
        else startDate.setDate(endDate.getDate() - 5);

        const sDateStr = startDate.toISOString().split("T")[0];
        const eDateStr = endDate.toISOString().split("T")[0];

        const hostname = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
        const backendUrl = typeof window !== 'undefined' ? `http://${hostname}:8000` : 'http://127.0.0.1:8000';
        const res = await fetch(`${backendUrl}/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${sDateStr}&end_date=${eDateStr}&timeframe=${encodeURIComponent(timeframe)}`);
        
        if (!isMounted) return;
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
          const time = Math.floor(date.getTime() / 1000) as Time;
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
          candleSeries.setData(uniqueData);
          emaSeries.setData(calculateEMA(uniqueData, 9));
          smaSeries.setData(calculateEMA(uniqueData, 21));
          
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
          }
          lastCandleRef.current = uniqueData[uniqueData.length - 1];
          chart.timeScale().fitContent();
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
  }, [symbol, timeframe]);

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
         currentCandleTime = Math.floor(d.getTime() / 1000);
      }
      
      let updatedCandle;
      
      if (currentCandleTime > (lastCandle.time as number)) {
        updatedCandle = {
          time: currentCandleTime as Time,
          open: livePrice,
          high: livePrice,
          low: livePrice,
          close: livePrice,
          volume: 0
        };
      } else {
        // Update the existing candle
        updatedCandle = {
          ...lastCandle,
          close: livePrice,
          high: Math.max(lastCandle.high, livePrice),
          low: Math.min(lastCandle.low, livePrice),
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
  }, [livePrice, timeframe]);

  return (
    <div className="w-full h-full relative" style={{ minHeight: "450px" }}>
      {/* Chart Header Overlay */}
      <div className="absolute top-4 left-4 z-10 pointer-events-none flex flex-col items-start gap-1">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#090a0f]/80 backdrop-blur-md border border-border/20 shadow-lg">
           <span className="font-bold text-foreground text-sm tracking-tight">{symbol.split(':')[1]?.split('-')[0] || symbol}</span>
           <span className="text-muted-foreground text-xs">{timeframe}</span>
           {livePrice && livePrice > 0 && (
             <>
               <span className="text-muted-foreground/50 text-xs">|</span>
               <span className={`font-mono font-bold text-sm tracking-tighter ${lastCandleOpen !== null && livePrice >= lastCandleOpen ? 'text-emerald-400 drop-shadow-[0_0_4px_rgba(16,185,129,0.4)]' : 'text-red-400 drop-shadow-[0_0_4px_rgba(239,68,68,0.4)]'}`}>
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
                   <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground px-1.5 py-0.5 rounded bg-muted/50">Market Closed</span>
                 </>
               )}
             </>
           )}
        </div>
      </div>

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
      <div ref={tooltipRef} className="absolute top-16 left-4 z-20 pointer-events-none hidden bg-background/90 backdrop-blur-md text-muted-foreground p-3 rounded-lg border border-border/50 shadow-xl" />
      <div ref={chartContainerRef} className="w-full h-full min-h-[450px] absolute inset-0 z-0" />
    </div>
  );
}
