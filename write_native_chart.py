import sys

chart_code = """\"use client\";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, LineSeries } from "lightweight-charts";
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

interface NativeChartProps {
  symbol: string;
  livePrice?: number;
  timeframe?: string;
}

// Global cache outside component to persist across unmounts
const chartDataCache: Record<string, any> = {};

export default function NativeChart({ symbol, livePrice, timeframe = "5 Min" }: NativeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const lastCandleRef = useRef<any>(null);

  // 1. INITIALIZE CHART ONLY ONCE
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#9CA3AF" },
      grid: { vertLines: { color: "rgba(255, 255, 255, 0.05)" }, horzLines: { color: "rgba(255, 255, 255, 0.05)" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "rgba(255, 255, 255, 0.1)" },
      rightPriceScale: { borderColor: "rgba(255, 255, 255, 0.1)", autoScale: true },
      crosshair: {
        mode: 0,
        vertLine: { color: "rgba(255, 255, 255, 0.4)", style: 1, labelBackgroundColor: "#374151" },
        horzLine: { color: "rgba(255, 255, 255, 0.4)", style: 1, labelBackgroundColor: "#374151" },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981", downColor: "#EF4444", borderVisible: false,
      wickUpColor: "#10B981", wickDownColor: "#EF4444",
    });

    const emaSeries = chart.addSeries(LineSeries, { color: '#3B82F6', lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });
    const smaSeries = chart.addSeries(LineSeries, { color: '#F59E0B', lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    emaSeriesRef.current = emaSeries;
    smaSeriesRef.current = smaSeries;

    chart.subscribeCrosshairMove((param) => {
      if (!tooltipRef.current || !chartContainerRef.current) return;
      if (param.point === undefined || !param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
        tooltipRef.current.style.display = "none";
        return;
      }
      const data = param.seriesData.get(candleSeries) as any;
      if (data) {
        tooltipRef.current.style.display = "block";
        const date = new Date((param.time as number) * 1000);
        const timeStr = date.toISOString().substr(11, 5);
        const dateStr = date.toISOString().substr(0, 10);
        tooltipRef.current.innerHTML = `
          <div class="font-bold text-primary mb-1">${symbol} &bull; ${dateStr} ${timeStr}</div>
          <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
            <div>O: <span class="text-foreground">${data.open.toFixed(2)}</span></div>
            <div>H: <span class="text-success">${data.high.toFixed(2)}</span></div>
            <div>L: <span class="text-destructive">${data.low.toFixed(2)}</span></div>
            <div>C: <span class="text-foreground">${data.close.toFixed(2)}</span></div>
          </div>
        `;
      }
    });

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
      }
    };
    window.addEventListener("resize", handleResize);
    // Initial resize to fit container
    setTimeout(handleResize, 50);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, []); // Run only ONCE on mount

  // 2. FETCH DATA WHEN SYMBOL/TIMEFRAME CHANGES
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current || !emaSeriesRef.current || !smaSeriesRef.current) return;
    
    const candleSeries = seriesRef.current;
    const emaSeries = emaSeriesRef.current;
    const smaSeries = smaSeriesRef.current;
    const chart = chartRef.current;

    const fetchMarkersAndLines = async (chartData: any[], cSeries: ISeriesApi<"Candlestick">) => {
      try {
        const backendUrl = typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000';
        const stateRes = await fetch(`${backendUrl}/api/state`);
        if (stateRes.ok) {
          const stateData = await stateRes.json();
          if (stateData.trades && stateData.trades.length > 0) {
            const markers: any[] = [];
            const symbolTrades = stateData.trades.filter((t: any) => t.symbol === symbol);
            
            symbolTrades.forEach((trade: any) => {
               const dateStr = trade.entry_time;
               if (!dateStr) return;
               const date = new Date(dateStr);
               const time = (Math.floor(date.getTime() / 1000) - (date.getTimezoneOffset() * 60)) as Time;
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
            // Lightweight charts overwrites existing markers when setMarkers is called! Perfect.
            (cSeries as any).setMarkers(markers);
          }
        }
      } catch (e) {
        console.error("Error fetching markers", e);
      }
    };

    const fetchHistory = async () => {
      const cacheKey = `${symbol}_${timeframe}`;
      
      if (chartDataCache[cacheKey]) {
         const cached = chartDataCache[cacheKey];
         candleSeries.setData(cached);
         emaSeries.setData(calculateEMA(cached, 9));
         smaSeries.setData(calculateSMA(cached, 20));
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

        const backendUrl = typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000';
        const res = await fetch(`${backendUrl}/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${sDateStr}&end_date=${eDateStr}&timeframe=${encodeURIComponent(timeframe)}`);
        
        if (!res.ok) throw new Error("Failed to fetch historical data.");
        const json = await res.json();
        
        if (!json.data || !Array.isArray(json.data) || json.data.length === 0) {
          if (!chartDataCache[cacheKey]) {
             setError(`No data available for ${timeframe}.`);
             setLoading(false);
          }
          return;
        }

        const formattedData = json.data.map((item: any) => {
          const dateStr = item.datetime || item.Datetime || item.date;
          const date = new Date(dateStr);
          const time = (Math.floor(date.getTime() / 1000) - (date.getTimezoneOffset() * 60)) as Time;
          return {
            time, open: parseFloat(item.open || item.Open), high: parseFloat(item.high || item.High),
            low: parseFloat(item.low || item.Low), close: parseFloat(item.close || item.Close),
          };
        }).sort((a: any, b: any) => (a.time as number) - (b.time as number));

        const uniqueData = [];
        const seenTimes = new Set();
        for (const item of formattedData) {
          if (!seenTimes.has(item.time)) { seenTimes.add(item.time); uniqueData.push(item); }
        }

        if (uniqueData.length > 0) {
          chartDataCache[cacheKey] = uniqueData; // Cache it!
          candleSeries.setData(uniqueData);
          emaSeries.setData(calculateEMA(uniqueData, 9));
          smaSeries.setData(calculateSMA(uniqueData, 20));
          lastCandleRef.current = uniqueData[uniqueData.length - 1];
          chart.timeScale().fitContent();
          fetchMarkersAndLines(uniqueData, candleSeries);
        }
        setLoading(false);
      } catch (err: any) {
        console.error("Error loading chart:", err);
        if (!chartDataCache[cacheKey]) {
           setError(err.message || "Could not load chart data");
           setLoading(false);
        }
      }
    };

    fetchHistory();
  }, [symbol, timeframe]);

  // 3. Handle live price updates
  useEffect(() => {
    if (livePrice && livePrice > 0 && seriesRef.current && lastCandleRef.current) {
      const lastCandle = lastCandleRef.current;
      const updatedCandle = {
        ...lastCandle,
        close: livePrice,
        high: Math.max(lastCandle.high, livePrice),
        low: Math.min(lastCandle.low, livePrice),
      };
      seriesRef.current.update(updatedCandle);
      lastCandleRef.current = updatedCandle;
    }
  }, [livePrice]);

  return (
    <div className="w-full h-full relative" style={{ minHeight: "450px" }}>
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
      <div ref={tooltipRef} className="absolute top-4 left-4 z-20 pointer-events-none hidden bg-background/90 backdrop-blur-md text-muted-foreground p-3 rounded-lg border border-border/50 shadow-xl" />
      <div ref={chartContainerRef} className="w-full h-full min-h-[450px] absolute inset-0 z-0" />
    </div>
  );
}
"""

with open("frontend/components/native-chart.tsx", "w", encoding="utf-8") as f:
    f.write(chart_code)
