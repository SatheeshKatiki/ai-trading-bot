"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  init, dispose, Chart, KLineData,
  LineType, PolygonType, ActionType, CandleType,
  TooltipShowRule, TooltipShowType,
  YAxisType, YAxisPosition
} from "klinecharts";
import {
  RefreshCw, MousePointer2, TrendingUp, MoveHorizontal, MoveVertical,
  Crosshair, Square, ArrowRight, Minus, GitBranch, Circle, Trash2,
} from "lucide-react";
import { useTheme } from "@/components/theme-provider";

// Crash-guard: patch formatToParts for bad klinecharts timestamps
if (typeof Intl !== "undefined" && Intl.DateTimeFormat?.prototype) {
  const orig = Intl.DateTimeFormat.prototype.formatToParts;
  Intl.DateTimeFormat.prototype.formatToParts = function (date?: Date | number) {
    try {
      if (typeof date === "number" && (!isFinite(date) || date < -8640000000000000 || date > 8640000000000000))
        return orig.call(this, 0);
      return orig.call(this, date);
    } catch {
      return orig.call(this, 0);
    }
  };
}

// Market hours helper (IST)
function isMarketOpen() {
  const now = new Date();
  const opts = { timeZone: "Asia/Kolkata", hour12: false, hour: "numeric", minute: "numeric", weekday: "short" } as const;
  const parts = new Intl.DateTimeFormat("en-US", opts).formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  if (weekday === "Sat" || weekday === "Sun") return false;
  const h = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const m = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
  const t = h * 60 + m;
  return t >= 9 * 60 + 15 && t <= 15 * 60 + 30;
}

interface AdvancedChartProps {
  symbol: string;
  livePrice?: number;
  timeframe: string;
}

const DRAWING_TOOLS = [
  { id: "", icon: MousePointer2, label: "Cursor", group: "cursor" },
  { id: "trendLine", icon: TrendingUp, label: "Trend Line", group: "lines" },
  { id: "rayLine", icon: ArrowRight, label: "Ray", group: "lines" },
  { id: "horizontalLine", icon: Minus, label: "Horizontal Line", group: "lines" },
  { id: "verticalLine", icon: MoveVertical, label: "Vertical Line", group: "lines" },
  { id: "priceChannelLine", icon: MoveHorizontal, label: "Parallel Channel", group: "lines" },
  { id: "fibonacciLine", icon: GitBranch, label: "Fibonacci Retracement", group: "fib" },
  { id: "rect", icon: Square, label: "Rectangle", group: "shapes" },
  { id: "circle", icon: Circle, label: "Circle", group: "shapes" },
];

const dataCache: Record<string, KLineData[]> = {};

function fmtDate(d: Date) { return d.toISOString().split("T")[0]; }

function setupIndicators(chart: Chart) {
  try { chart.removeIndicator("candle_pane", "EMA"); } catch { }
  try { chart.removeIndicator("vol_pane", "VOL"); } catch { }

  // EMA 9 (blue) + EMA 21 (orange) - minimal safe styles
  chart.createIndicator({
    name: "EMA",
    calcParams: [9, 21],
    styles: {
      lines: [
        { style: LineType.Solid, smooth: false, size: 1.5, color: "#2196F3", dashedValue: [4, 4] },
        { style: LineType.Solid, smooth: false, size: 1.5, color: "#FF9800", dashedValue: [4, 4] },
      ],
    },
  }, true, { id: "candle_pane" });

  // Volume in separate sub-pane using default colours (safe)
  chart.createIndicator({ name: "VOL" }, false, { id: "vol_pane", height: 80 });
}

function buildStyles(isDark: boolean) {
  const bg = isDark ? "#0d1117" : "#ffffff";
  const grid = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";
  const axisCol = isDark ? "#8b949e" : "#57606a";
  const border = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const cross = isDark ? "rgba(139,148,158,0.5)" : "rgba(87,96,106,0.5)";
  const label = isDark ? "#161b22" : "#f6f8fa";
  const labCol = isDark ? "#e6edf3" : "#24292f";
  return {
    grid: {
      show: true,
      horizontal: { style: LineType.Dashed, size: 1, color: grid, dashedValue: [4, 4] },
      vertical:   { style: LineType.Dashed, size: 1, color: grid, dashedValue: [4, 4] },
    },
    candle: {
      type: CandleType.CandleSolid,
      bar: {
        upColor: "#26a69a", downColor: "#ef5350", noChangeColor: "#888",
        upBorderColor: "#26a69a", downBorderColor: "#ef5350", noChangeBorderColor: "#888",
        upWickColor: "#26a69a", downWickColor: "#ef5350", noChangeWickColor: "#888",
      },
      priceMark: {
        show: true,
        high: { show: true, color: axisCol, textOffset: 5, textSize: 10, textFamily: "Inter,monospace", textWeight: "normal" },
        low: { show: true, color: axisCol, textOffset: 5, textSize: 10, textFamily: "Inter,monospace", textWeight: "normal" },
        last: {
          show: true, upColor: "#26a69a", downColor: "#ef5350", noChangeColor: "#888",
          line: { show: true, style: LineType.Dashed, dashedValue: [4, 4], size: 1 },
          text: { show: true, size: 11, paddingTop: 3, paddingBottom: 3, paddingLeft: 6, paddingRight: 6, borderRadius: 3, borderSize: 0, textFamily: "Inter,monospace", textWeight: "700" },
        },
      },
      tooltip: {
        showRule: TooltipShowRule.FollowCross,
        showType: TooltipShowType.Standard,
        labels: ["Time:", "O:", "H:", "L:", "C:", "Vol:"],
        values: null, defaultValue: "n/a",
        text: { size: 11, family: "Inter,monospace", weight: "normal", color: axisCol, marginLeft: 4, marginTop: 4, marginRight: 4, marginBottom: 4 },
      },
    },
    indicator: {
      tooltip: {
        showRule: TooltipShowRule.FollowCross, showType: TooltipShowType.Standard,
        text: { size: 11, family: "Inter,monospace", color: axisCol, marginLeft: 4, marginTop: 4, marginRight: 4, marginBottom: 4 },
      },
    },
    xAxis: {
      show: true, height: 28,
      axisLine: { show: true, color: border, size: 1 },
      tickLine: { show: true, color: border, size: 5, length: 5 },
      tickText: { show: true, color: axisCol, family: "Inter,monospace", weight: "normal", size: 11 },
    },
    yAxis: {
      show: true, width: 72, type: YAxisType.Normal, position: YAxisPosition.Right,
      axisLine: { show: true, color: border, size: 1 },
      tickLine: { show: true, color: border, size: 5, length: 5 },
      tickText: { show: true, color: axisCol, family: "Inter,monospace", weight: "normal", size: 11 },
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 4], size: 1, color: cross },
        text: { show: true, size: 11, paddingLeft: 6, paddingRight: 6, paddingTop: 3, paddingBottom: 3, color: labCol, borderSize: 1, borderRadius: 3, family: "Inter,monospace", weight: "600", backgroundColor: label, borderColor: border },
      },
      vertical: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 4], size: 1, color: cross },
        text: { show: true, size: 11, paddingLeft: 6, paddingRight: 6, paddingTop: 3, paddingBottom: 3, color: labCol, borderSize: 1, borderRadius: 3, family: "Inter,monospace", weight: "600", backgroundColor: label, borderColor: border },
      },
    },
    overlay: {
      point: { color: "#26a69a", borderColor: "#26a69a", borderSize: 1, radius: 5, activeColor: "#26a69a", activeBorderColor: "#fff", activeBorderSize: 2, activeRadius: 6 },
      line: { style: LineType.Solid, smooth: false, color: "#26a69a", size: 1.5, dashedValue: [4, 4] },
      rect: { style: PolygonType.Fill, color: "rgba(38,166,154,0.1)", borderColor: "#26a69a", borderSize: 1, borderRadius: 0, borderStyle: LineType.Solid, dashedValue: [4, 4] },
    },
    separator: {
      size: 1, color: border, fill: true,
      activeBackgroundColor: isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.03)",
    },
  };
}

export default function AdvancedChart({ symbol, livePrice, timeframe }: AdvancedChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const lastBarRef = useRef<KLineData | null>(null);
  const { theme } = useTheme();
  const isDark = theme !== "light";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState("");
  const [ohlcv, setOhlcv] = useState<{ o: number; h: number; l: number; c: number; v: number } | null>(null);

  const bg = isDark ? "#0d1117" : "#ffffff";
  const border = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisCol = isDark ? "#8b949e" : "#57606a";

  // Init chart once
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = init(containerRef.current, {
      locale: "en-US",
      timezone: "Asia/Kolkata",
      styles: buildStyles(isDark),
    });
    if (!chart) return;
    chartRef.current = chart;

    chart.setCustomApi({
      formatDate: (_dtf: Intl.DateTimeFormat, ts: number, fmt: string) => {
        try {
          if (!isFinite(ts) || ts < 0) return "";
          const d = new Date(ts);
          const dd = d.getDate().toString().padStart(2, "0");
          const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()];
          const yyyy = d.getFullYear();
          const hh = d.getHours().toString().padStart(2, "0");
          const mm = d.getMinutes().toString().padStart(2, "0");
          if (fmt === "YYYY-MM-DD" || fmt === "MM-DD") return `${dd} ${mon} ${yyyy}`;
          if (fmt === "HH:mm") return `${hh}:${mm}`;
          return `${dd} ${mon} ${yyyy}`;
        } catch { return ""; }
      },
    });

    chart.subscribeAction(ActionType.OnCrosshairChange, (data: any) => {
      if (data?.kLineData) {
        const k = data.kLineData as KLineData;
        setOhlcv({ o: k.open, h: k.high, l: k.low, c: k.close, v: k.volume ?? 0 });
      } else {
        setOhlcv(null);
      }
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current!);

    return () => {
      ro.disconnect();
      if (containerRef.current) dispose(containerRef.current);
      chartRef.current = null;
    };
  }, []);

  // Re-style on theme change
  useEffect(() => { chartRef.current?.setStyles(buildStyles(isDark)); }, [theme]);

  // Fetch data on symbol/timeframe change
  useEffect(() => {
    let alive = true;
    const chart = chartRef.current;
    if (!chart) return;
    const key = `adv_${symbol}_${timeframe}`;

    const load = async () => {
      if (dataCache[key]) {
        chart.applyNewData(dataCache[key]);
        setupIndicators(chart);
        lastBarRef.current = dataCache[key][dataCache[key].length - 1] ?? null;
        setLoading(false); setError(null);
        return;
      }
      setLoading(true); setError(null);
      try {
        const end = new Date(), start = new Date();
        if (timeframe.includes("Month")) start.setFullYear(end.getFullYear() - 10);
        else if (timeframe.includes("Week")) start.setFullYear(end.getFullYear() - 5);
        else if (timeframe.includes("Day")) start.setFullYear(end.getFullYear() - 2);
        else if (timeframe.includes("Hour")) start.setDate(end.getDate() - 60);
        else start.setDate(end.getDate() - 10);

        const host = window.location.hostname === "localhost" ? "127.0.0.1" : window.location.hostname;
        const url = `http://${host}:8000/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${fmtDate(start)}&end_date=${fmtDate(end)}&timeframe=${encodeURIComponent(timeframe)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch data");
        const json = await res.json();
        if (!alive) return;
        if (!Array.isArray(json?.data) || json.data.length === 0)
          throw new Error(`No data for ${symbol} (${timeframe})`);

        const bars: KLineData[] = json.data
          .map((d: any) => {
            const raw = String(d.datetime ?? d.Datetime ?? d.date ?? "");
            const safe = raw.includes(" ") ? raw.replace(" ", "T") : raw;
            return { timestamp: new Date(safe).getTime(), open: parseFloat(d.open ?? d.Open ?? 0), high: parseFloat(d.high ?? d.High ?? 0), low: parseFloat(d.low ?? d.Low ?? 0), close: parseFloat(d.close ?? d.Close ?? 0), volume: parseFloat(d.volume ?? d.Volume ?? 0) };
          })
          .filter((b: KLineData) => isFinite(b.timestamp) && b.timestamp > 0)
          .sort((a: KLineData, b: KLineData) => a.timestamp - b.timestamp);

        if (bars.length === 0) throw new Error("No valid bars after filtering");
        dataCache[key] = bars;
        chart.applyNewData(bars);
        setupIndicators(chart);
        lastBarRef.current = bars[bars.length - 1] ?? null;
        setLoading(false);
      } catch (e: any) {
        if (!alive) return;
        setError(e.message ?? "Unknown error");
        setLoading(false);
      }
    };
    load();
    return () => { alive = false; };
  }, [symbol, timeframe]);

  // Live price tick
  useEffect(() => {
    if (!livePrice || livePrice <= 0 || !chartRef.current || !lastBarRef.current || !isMarketOpen()) return;
    const tfVal = parseInt(timeframe.split(" ")[0] ?? "5", 10);
    const now = new Date();
    const mins = now.getHours() * 60 + now.getMinutes();
    const sinceOpen = mins - (9 * 60 + 15);
    const slot = timeframe.includes("Hour")
      ? Math.floor(sinceOpen / (tfVal * 60)) * (tfVal * 60)
      : Math.floor(sinceOpen / tfVal) * tfVal;
    const slotStart = new Date(now);
    slotStart.setHours(9, 15 + slot, 0, 0);
    const ts = slotStart.getTime();
    const last = lastBarRef.current;
    const bar = ts > last.timestamp
      ? { timestamp: ts, open: livePrice, high: livePrice, low: livePrice, close: livePrice, volume: 0 }
      : { ...last, close: livePrice, high: Math.max(last.high, livePrice), low: Math.min(last.low, livePrice) };
    lastBarRef.current = bar;
    chartRef.current.updateData(bar);
  }, [livePrice, timeframe]);

  // Drawing tool handler
  const selectTool = useCallback((id: string) => {
    const chart = chartRef.current;
    if (!chart) return;
    setActiveTool(id);
    if (!id) { chart.removeOverlay({}); } else { chart.createOverlay(id); }
  }, []);

  const fmtPx = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtVol = (v: number) => v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : v.toFixed(0);
  const isUp = ohlcv ? ohlcv.c >= ohlcv.o : true;
  const pxCol = isUp ? "#26a69a" : "#ef5350";

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", background: bg, overflow: "hidden", minHeight: 450 }}>
      {/* LEFT TOOLBAR */}
      <div style={{ width: 44, borderRight: `1px solid ${border}`, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 2, background: isDark ? "#0d1117" : "#fafafa", flexShrink: 0, zIndex: 10 }}>
        {DRAWING_TOOLS.map((t, i) => {
          const Icon = t.icon;
          const active = activeTool === t.id;
          const showSep = i > 0 && DRAWING_TOOLS[i - 1].group !== t.group;
          return (
            <React.Fragment key={t.id}>
              {showSep && <div style={{ width: 28, height: 1, background: border, margin: "2px 0" }} />}
              <button
                title={t.label}
                onClick={() => selectTool(t.id)}
                style={{
                  width: 34, height: 34, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center",
                  background: active ? "rgba(38,166,154,0.15)" : "transparent",
                  border: `1px solid ${active ? "rgba(38,166,154,0.4)" : "transparent"}`,
                  color: active ? "#26a69a" : axisCol, cursor: "pointer", transition: "all 0.15s",
                }}
              >
                <Icon size={15} strokeWidth={active ? 2.5 : 1.75} />
              </button>
            </React.Fragment>
          );
        })}
        <div style={{ flex: 1 }} />
        <button
          title="Clear drawings"
          onClick={() => { chartRef.current?.removeOverlay({}); setActiveTool(""); }}
          style={{ width: 34, height: 34, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", background: "transparent", border: "1px solid transparent", color: axisCol, cursor: "pointer", marginBottom: 8 }}
        >
          <Trash2 size={14} strokeWidth={1.75} />
        </button>
      </div>

      {/* CHART AREA */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        {/* TOP INFO BAR */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, zIndex: 20,
          display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8,
          padding: "5px 12px",
          background: isDark ? "rgba(13,17,23,0.9)" : "rgba(255,255,255,0.9)",
          backdropFilter: "blur(8px)", borderBottom: `1px solid ${border}`,
          pointerEvents: "none",
        }}>
          <span style={{ fontWeight: 700, fontSize: 13, color: isDark ? "#e6edf3" : "#24292f", letterSpacing: "-0.01em" }}>
            {symbol.split(":")[1]?.split("-")[0] ?? symbol}
          </span>
          <span style={{ fontSize: 11, color: axisCol, fontWeight: 500 }}>{timeframe}</span>

          {livePrice && livePrice > 0 && <>
            <span style={{ color: border }}>•</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: pxCol, fontFamily: "monospace", letterSpacing: "-0.02em" }}>
              ₹{fmtPx(livePrice)}
            </span>
            {!isMarketOpen() && (
              <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.08em", color: axisCol, background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4, textTransform: "uppercase" }}>
                Market Closed
              </span>
            )}
          </>}

          {ohlcv && (
            <span style={{ display: "flex", gap: 10, fontSize: 11, fontFamily: "monospace", color: axisCol }}>
              {([["O", ohlcv.o, ohlcv.c >= ohlcv.o ? "#26a69a" : "#ef5350"], ["H", ohlcv.h, "#26a69a"], ["L", ohlcv.l, "#ef5350"], ["C", ohlcv.c, ohlcv.c >= ohlcv.o ? "#26a69a" : "#ef5350"]] as [string, number, string][]).map(([l, v, c]) => (
                <span key={l}>{l} <span style={{ color: c }}>{fmtPx(v)}</span></span>
              ))}
              <span>V <span style={{ color: "#8b949e" }}>{fmtVol(ohlcv.v)}</span></span>
            </span>
          )}
        </div>

        {/* CHART CANVAS */}
        <div ref={containerRef} style={{ position: "absolute", inset: 0, top: 36 }} />

        {/* Loading */}
        {loading && (
          <div style={{ position: "absolute", inset: 0, top: 36, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: isDark ? "rgba(13,17,23,0.85)" : "rgba(255,255,255,0.85)", backdropFilter: "blur(4px)", zIndex: 30 }}>
            <RefreshCw size={22} style={{ animation: "spin 1s linear infinite", color: "#26a69a", marginBottom: 8 }} />
            <span style={{ fontSize: 13, color: axisCol }}>Loading {symbol.split(":")[1] ?? symbol}…</span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div style={{ position: "absolute", inset: 0, top: 36, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: isDark ? "rgba(13,17,23,0.85)" : "rgba(255,255,255,0.85)", backdropFilter: "blur(4px)", zIndex: 30, gap: 8 }}>
            <span style={{ fontSize: 22 }}>⚠️</span>
            <span style={{ fontSize: 13, color: "#ef5350", fontWeight: 600 }}>{error}</span>
          </div>
        )}
      </div>
      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
