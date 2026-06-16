"use client";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries } from "lightweight-charts";
import { RefreshCw } from "lucide-react";

interface NativeChartProps {
  symbol: string;
  livePrice?: number;
}

export default function NativeChart({ symbol, livePrice }: NativeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Keep track of the latest candle so we can update it with livePrice
  const lastCandleRef = useRef<any>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        autoScale: true,
      },
      crosshair: {
        mode: 0, // Normal crosshair
        vertLine: {
          color: "rgba(255, 255, 255, 0.4)",
          style: 1,
          labelBackgroundColor: "#374151",
        },
        horzLine: {
          color: "rgba(255, 255, 255, 0.4)",
          style: 1,
          labelBackgroundColor: "#374151",
        },
      },
    });

    // Create candlestick series (lightweight-charts v5 syntax)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981", // Success green
      downColor: "#EF4444", // Destructive red
      borderVisible: false,
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    // Fetch Historical Data
    const fetchHistory = async () => {
      try {
        setLoading(true);
        // We'll fetch the last 3 days of data for the 5 Min timeframe
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(endDate.getDate() - 3);

        const sDateStr = startDate.toISOString().split("T")[0];
        const eDateStr = endDate.toISOString().split("T")[0];

        // Format symbol for backend (it accepts just "NIFTY" and formats it itself, but just in case we pass the raw one)
        const res = await fetch(`http://localhost:8000/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${sDateStr}&end_date=${eDateStr}&timeframe=5 Min`);
        
        if (!res.ok) {
          throw new Error("Failed to fetch historical data");
        }
        
        const json = await res.json();
        
        if (!json.data || !Array.isArray(json.data) || json.data.length === 0) {
          // No data (e.g. weekend or broker offline)
          setLoading(false);
          return;
        }

        // Parse and sort data
        const formattedData = json.data.map((item: any) => {
          // Convert "YYYY-MM-DD HH:MM:SS" to unix timestamp in seconds
          // Assuming the timezone is IST
          const dateStr = item.datetime || item.Datetime || item.date;
          // Create date object
          const date = new Date(dateStr);
          // Get unix timestamp in seconds
          const time = Math.floor(date.getTime() / 1000) as Time;
          
          return {
            time,
            open: parseFloat(item.open || item.Open),
            high: parseFloat(item.high || item.High),
            low: parseFloat(item.low || item.Low),
            close: parseFloat(item.close || item.Close),
          };
        }).sort((a: any, b: any) => (a.time as number) - (b.time as number));

        // Deduplicate by time just in case
        const uniqueData = [];
        const seenTimes = new Set();
        for (const item of formattedData) {
          if (!seenTimes.has(item.time)) {
            seenTimes.add(item.time);
            uniqueData.push(item);
          }
        }

        if (uniqueData.length > 0) {
          candleSeries.setData(uniqueData);
          lastCandleRef.current = uniqueData[uniqueData.length - 1];
          // Fit content nicely
          chart.timeScale().fitContent();
        }
        
        setLoading(false);
      } catch (err) {
        console.error("Error loading chart:", err);
        setError("Could not load chart data");
        setLoading(false);
      }
    };

    fetchHistory();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [symbol]);

  // Handle live price updates
  useEffect(() => {
    if (livePrice && livePrice > 0 && seriesRef.current && lastCandleRef.current) {
      const lastCandle = lastCandleRef.current;
      
      // Update the close price of the last candle, and expand high/low if needed
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
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-background/50 backdrop-blur-sm">
          <div className="text-destructive font-medium">{error}</div>
        </div>
      )}

      {/* The container for the actual chart */}
      <div 
        ref={chartContainerRef} 
        className="w-full h-full min-h-[450px] absolute inset-0" 
      />
    </div>
  );
}
