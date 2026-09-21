"use client";

import React, { useState, useEffect } from "react";
import { Maximize2, Bot, Tag, Download, Settings2 } from "lucide-react";

interface ChartHeaderToolbarProps {
  className?: string;
  showIndicators?: boolean;
}

export default function ChartHeaderToolbar({
  className = "",
  showIndicators = true,
}: ChartHeaderToolbarProps) {
  const [signalsActive, setSignalsActive] = useState(true);
  const [markersActive, setMarkersActive] = useState(true);

  useEffect(() => {
    const onSignals = (e: any) => {
      if (e.detail?.value !== undefined) setSignalsActive(Boolean(e.detail.value));
    };
    const onMarkers = (e: any) => {
      if (e.detail?.value !== undefined) setMarkersActive(Boolean(e.detail.value));
    };
    window.addEventListener("chart:signals-changed", onSignals as EventListener);
    window.addEventListener("chart:markers-changed", onMarkers as EventListener);
    return () => {
      window.removeEventListener("chart:signals-changed", onSignals as EventListener);
      window.removeEventListener("chart:markers-changed", onMarkers as EventListener);
    };
  }, []);

  const handleOpenIndicators = () => {
    window.dispatchEvent(new CustomEvent("chart:open-indicators"));
  };

  const handleResetZoom = () => {
    window.dispatchEvent(new CustomEvent("chart:reset-zoom"));
  };

  const handleToggleSignals = () => {
    window.dispatchEvent(new CustomEvent("chart:toggle-signals"));
  };

  const handleToggleMarkers = () => {
    window.dispatchEvent(new CustomEvent("chart:toggle-markers"));
  };

  const handleExportPng = () => {
    window.dispatchEvent(new CustomEvent("chart:export-png"));
  };

  const handleOpenSettings = () => {
    window.dispatchEvent(new CustomEvent("chart:open-settings"));
  };

  return (
    <div
      className={`inline-flex items-center bg-muted/40 backdrop-blur-md px-2 py-1 rounded-full border border-border/60 gap-1.5 shadow-sm transition-all ${className}`}
    >
      {showIndicators && (
        <>
          <button
            type="button"
            onClick={handleOpenIndicators}
            className="px-2.5 py-1 rounded-full transition-all flex items-center gap-1.5 text-xs font-semibold bg-background/60 hover:bg-background text-muted-foreground hover:text-foreground border border-border/50 hover:border-border active:scale-95 cursor-pointer shadow-xs"
            title="Technical Indicators (fx)"
          >
            <span className="font-serif italic font-black text-xs text-rose-500">fx</span>
            <span className="text-[11px] font-semibold text-foreground/90">Indicators</span>
          </button>
          <div className="h-4 w-px bg-border/60 mx-0.5" />
        </>
      )}

      {/* Reset Zoom */}
      <button
        type="button"
        onClick={handleResetZoom}
        className="p-1.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-transparent hover:border-border/40 transition-all active:scale-95 flex items-center justify-center cursor-pointer"
        title="Reset Zoom (Fit Candlesticks to View)"
      >
        <Maximize2 size={15} />
      </button>

      {/* AI Strategy Signals Toggle */}
      <button
        type="button"
        onClick={handleToggleSignals}
        className={`p-1.5 rounded-full transition-all active:scale-95 flex items-center justify-center border cursor-pointer ${
          signalsActive
            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-sm"
            : "text-muted-foreground hover:text-foreground hover:bg-muted/60 border-transparent"
        }`}
        title={
          signalsActive
            ? "AI Strategy Signals Active (Click to Hide)"
            : "AI Strategy Signals Hidden (Click to Show)"
        }
      >
        <Bot size={15} className={signalsActive ? "animate-pulse" : ""} />
      </button>

      {/* Executed Trade Markers Toggle */}
      <button
        type="button"
        onClick={handleToggleMarkers}
        className={`p-1.5 rounded-full transition-all active:scale-95 flex items-center justify-center border cursor-pointer ${
          markersActive
            ? "bg-rose-500/20 text-rose-400 border-rose-500/50 shadow-sm"
            : "text-muted-foreground hover:text-foreground hover:bg-muted/60 border-transparent"
        }`}
        title={
          markersActive
            ? "Trade Markers Active (Click to Hide)"
            : "Trade Markers Hidden (Click to Show)"
        }
      >
        <Tag size={15} />
      </button>

      {/* Export PNG */}
      <button
        type="button"
        onClick={handleExportPng}
        className="p-1.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-transparent hover:border-border/40 transition-all active:scale-95 flex items-center justify-center cursor-pointer"
        title="Export Chart Snapshot (PNG)"
      >
        <Download size={15} />
      </button>

      {/* Chart Settings */}
      <button
        type="button"
        onClick={handleOpenSettings}
        className="p-1.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-transparent hover:border-border/40 transition-all active:scale-95 flex items-center justify-center cursor-pointer"
        title="Chart Settings & Parameters"
      >
        <Settings2 size={15} />
      </button>
    </div>
  );
}
