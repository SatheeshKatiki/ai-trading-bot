"use client";

import React, { memo } from 'react';
import { AdvancedRealTimeChart } from "react-ts-tradingview-widgets";
import { useTheme } from "@/components/theme-provider";

interface UltraChartProps {
  symbol: string;
  timeframe: string;
  isFullScreen?: boolean;
}

const UltraChart = ({ symbol, timeframe, isFullScreen = false }: UltraChartProps) => {
  const { theme } = useTheme();
  const isDark = theme !== "light";

  // Map our timeframe string to TradingView intervals
  const mapTimeframe = (tf: string) => {
    if (tf.includes("Min")) return tf.split(" ")[0]; // "1", "5", "15", "30"
    if (tf.includes("Hour")) {
      const h = parseInt(tf.split(" ")[0]);
      return (h * 60).toString(); // "60", "240"
    }
    if (tf.includes("Day")) return "D";
    if (tf.includes("Week")) return "W";
    if (tf.includes("Month")) return "M";
    return "5"; // Default 5 Min
  };

  // Convert our generic symbol string into TV format
  const mapSymbol = (sym: string) => {
    let clean = sym;
    if (clean.includes(':')) clean = clean.split(':')[1];
    if (clean.includes('-')) clean = clean.split('-')[0];
    
    clean = clean.toUpperCase();
    if (clean === "NIFTY") return "OANDA:IN50INR";
    if (clean === "BANKNIFTY") return "BSE:SENSEX"; // Bank Nifty CFDs are rare, falling back to Sensex
    if (clean === "FINNIFTY") return "BSE:SENSEX";
    if (clean === "SENSEX") return "BSE:SENSEX";
    
    return `BSE:${clean}`;
  };

  return (
    <div className="w-full relative" style={{ height: isFullScreen ? "calc(100vh - 100px)" : "600px" }}>
      <AdvancedRealTimeChart
        theme={isDark ? "dark" : "light"}
        symbol={mapSymbol(symbol)}
        interval={mapTimeframe(timeframe) as any}
        timezone="Asia/Kolkata"
        style="1" // 1 = Candles
        locale="en"
        enable_publishing={false}
        hide_top_toolbar={false}
        hide_legend={false}
        save_image={false}
        container_id={`tv_chart_${mapSymbol(symbol).replace(/[^a-zA-Z0-9]/g, '')}`}
        autosize={true}
        studies={["Volume@tv-basicstudies"]}
      />
    </div>
  );
};

export default memo(UltraChart);
