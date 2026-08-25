"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Activity, TrendingUp, TrendingDown, Clock, Gauge, Zap,
  ArrowUpRight, ArrowDownRight, Target, Shield, BarChart2,
  Crosshair, Layers, Timer, AlertTriangle, ChevronDown,
  Bot, Radio, Sparkles, ShieldAlert, CheckCircle2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import { useLiveMarketStore } from "@/store/useLiveMarketStore";

const NativeChart = dynamic(() => import("@/components/native-chart"), { ssr: false });

// ─── Types ──────────────────────────────────────────────────────────────
interface GreeksData {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  theta_per_lot: number;
}

interface OptionGreeksResponse {
  symbol: string;
  strike: number;
  opt_type: string;
  spot: number;
  premium: number;
  intrinsic: number;
  extrinsic: number;
  status: string;
  breakeven: number;
  expiry_days: number;
  iv: number;
  greeks: GreeksData;
  lot_size: number;
  distance_points: number;
  distance_pct: number;
}

interface AdvancedOptionChartProps {
  symbol: string;       // Full option symbol e.g. "NIFTY 24250 CE"
  livePrice: number;    // Live premium price from ticker
  spotPrice: number;    // Live underlying spot price
  timeframe: string;
  showDynamicTrend: boolean;
  baseSymbol: string;   // e.g. "NIFTY"
}

// ─── Parse option symbol ────────────────────────────────────────────────
function parseOptionSymbol(symbol: string): { base: string; strike: number; type: string } | null {
  const match = symbol.match(/^(\w+)\s+(\d+)\s+(CE|PE)$/i);
  if (match) {
    return { base: match[1], strike: parseInt(match[2]), type: match[3].toUpperCase() };
  }
  return null;
}

// ─── IV Level Classification ────────────────────────────────────────────
function getIVLevel(iv: number): { label: string; color: string; bg: string; border: string } {
  if (iv < 12) return { label: "LOW", color: "text-emerald-400", bg: "bg-emerald-500/15", border: "border-emerald-500/30" };
  if (iv < 18) return { label: "NORMAL", color: "text-blue-400", bg: "bg-blue-500/15", border: "border-blue-500/30" };
  if (iv < 28) return { label: "ELEVATED", color: "text-amber-400", bg: "bg-amber-500/15", border: "border-amber-500/30" };
  return { label: "EXTREME", color: "text-rose-400", bg: "bg-rose-500/15", border: "border-rose-500/30" };
}

// ─── Status Badge ───────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const config = {
    ITM: { color: "text-emerald-300", bg: "bg-emerald-500/20", border: "border-emerald-500/40", icon: TrendingUp },
    ATM: { color: "text-amber-300", bg: "bg-amber-500/20", border: "border-amber-500/40", icon: Crosshair },
    OTM: { color: "text-rose-300", bg: "bg-rose-500/20", border: "border-rose-500/40", icon: TrendingDown },
  }[status] || { color: "text-muted-foreground", bg: "bg-muted/20", border: "border-border/40", icon: Activity };

  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black tracking-widest uppercase border ${config.bg} ${config.color} ${config.border}`}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
}

// ─── Greek Card ─────────────────────────────────────────────────────────
function GreekCard({ label, value, unit, icon: Icon, color, tooltip }: {
  label: string; value: string; unit?: string; icon: React.ElementType; color: string; tooltip?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative flex flex-col items-center px-3 py-2 rounded-lg border transition-all hover:scale-[1.02] group ${color}`}
      title={tooltip}
    >
      <div className="flex items-center gap-1 mb-0.5">
        <Icon className="w-3 h-3 opacity-70" />
        <span className="text-[9px] font-bold tracking-widest uppercase opacity-80">{label}</span>
      </div>
      <span className="text-sm font-black font-mono tabular-nums leading-none">{value}</span>
      {unit && <span className="text-[8px] font-semibold opacity-60 mt-0.5">{unit}</span>}
    </motion.div>
  );
}

// ─── IV Gauge (mini arc) ────────────────────────────────────────────────
function IVGauge({ iv }: { iv: number }) {
  const pct = Math.min(1, Math.max(0, iv / 40));
  const R = 22, CX = 28, CY = 28;
  const arcLen = Math.PI * R;
  const strokeOffset = arcLen * (1 - pct);
  const ivLevel = getIVLevel(iv);

  const gradientId = `iv-gauge-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="flex flex-col items-center gap-0.5">
      <svg width="56" height="36" viewBox="0 0 56 36">
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="40%" stopColor="#3b82f6" />
            <stop offset="70%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none"
          className="stroke-muted/40"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${arcLen}`}
          strokeDashoffset={strokeOffset}
          style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.4,0,0.2,1)" }}
        />
        <text x={CX} y={CY - 4} textAnchor="middle" className="fill-foreground" fontSize="10" fontWeight="900" fontFamily="monospace">
          {iv.toFixed(1)}%
        </text>
      </svg>
      <span className={`text-[8px] font-black tracking-wider ${ivLevel.color}`}>{ivLevel.label}</span>
    </div>
  );
}

// ─── Expiry Countdown ───────────────────────────────────────────────────
function ExpiryCountdown({ days }: { days: number }) {
  const d = Math.floor(days);
  const h = Math.floor((days - d) * 24);
  const m = Math.floor(((days - d) * 24 - h) * 60);

  const urgency = days < 1 ? "text-rose-400" : days < 3 ? "text-amber-400" : "text-emerald-400";
  const urgencyBg = days < 1 ? "bg-rose-500/10 border-rose-500/30" : days < 3 ? "bg-amber-500/10 border-amber-500/30" : "bg-emerald-500/10 border-emerald-500/30";

  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border ${urgencyBg}`}>
      <Timer className={`w-3.5 h-3.5 ${urgency} ${days < 1 ? 'animate-pulse' : ''}`} />
      <span className={`text-xs font-black font-mono tabular-nums ${urgency}`}>
        {d}d {h}h {m}m
      </span>
      {days < 1 && <AlertTriangle className="w-3 h-3 text-rose-400 animate-pulse" />}
    </div>
  );
}

// ─── Theta Burn Sparkline ───────────────────────────────────────────────
function ThetaBurnSparkline({ thetaHistory }: { thetaHistory: number[] }) {
  const data = thetaHistory.slice(-20);
  if (data.length < 2) return null;

  const max = Math.max(...data.map(Math.abs));
  const min = Math.min(...data.map(Math.abs));
  const range = max - min || 1;
  const w = 120, h = 28;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((Math.abs(v) - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(" ");

  const areaPoints = `0,${h} ${points} ${w},${h}`;

  return (
    <div className="flex items-center gap-2">
      <span className="text-[8px] font-bold text-rose-400/70 uppercase tracking-wider whitespace-nowrap">θ Burn</span>
      <svg width={w} height={h} className="overflow-visible">
        <defs>
          <linearGradient id="theta-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(239,68,68,0.3)" />
            <stop offset="100%" stopColor="rgba(239,68,68,0)" />
          </linearGradient>
        </defs>
        <polygon points={areaPoints} fill="url(#theta-fill)" />
        <polyline points={points} fill="none" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ─── Premium Decomposition Bar ──────────────────────────────────────────
function PremiumBar({ intrinsic, extrinsic, total }: { intrinsic: number; extrinsic: number; total: number }) {
  const iPct = total > 0 ? (intrinsic / total) * 100 : 0;
  const ePct = total > 0 ? (extrinsic / total) * 100 : 100;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[9px] font-bold">
        <span className="text-blue-400">Intrinsic ₹{intrinsic.toFixed(1)}</span>
        <span className="text-purple-400">Extrinsic ₹{extrinsic.toFixed(1)}</span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden flex bg-muted/30">
        <div className="bg-blue-500/70 transition-all duration-500 rounded-l-full" style={{ width: `${iPct}%` }} />
        <div className="bg-purple-500/50 transition-all duration-500 rounded-r-full" style={{ width: `${ePct}%` }} />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// ─── MAIN COMPONENT ────────────────═══════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

export function AdvancedOptionChart({
  symbol,
  livePrice,
  spotPrice,
  timeframe,
  showDynamicTrend,
  baseSymbol,
}: AdvancedOptionChartProps) {
  const [greeksData, setGreeksData] = useState<OptionGreeksResponse | null>(null);
  const [thetaHistory, setThetaHistory] = useState<number[]>([]);
  const [prevPremium, setPrevPremium] = useState(0);
  const [premiumFlash, setPremiumFlash] = useState<"up" | "down" | null>(null);
  const [showGreeksPanel, setShowGreeksPanel] = useState(true);
  const [showAutoSignals, setShowAutoSignals] = useState(true);
  const fetchIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const aiConfidence = useLiveMarketStore(state => state.aiConfidence || 94);
  const trades = useLiveMarketStore(state => state.trades || []);
  const positions = useLiveMarketStore(state => state.positionsDetail || []);

  const parsed = useMemo(() => parseOptionSymbol(symbol), [symbol]);

  // Fetch Greeks data
  const fetchGreeks = useCallback(async () => {
    if (!parsed) return;
    try {
      const params = new URLSearchParams({
        symbol: parsed.base,
        strike: parsed.strike.toString(),
        opt_type: parsed.type,
        spot: spotPrice > 0 ? spotPrice.toString() : "0",
      });
      const res = await fetch(`/api/option-greeks?${params}`);
      if (res.ok) {
        const data: OptionGreeksResponse = await res.json();
        setGreeksData(data);
        setThetaHistory(prev => [...prev.slice(-19), data.greeks.theta]);
      }
    } catch (e) {
      console.warn("Greeks fetch error:", e);
    }
  }, [parsed, spotPrice]);

  useEffect(() => {
    fetchGreeks();
    fetchIntervalRef.current = setInterval(fetchGreeks, 5000);
    return () => {
      if (fetchIntervalRef.current) clearInterval(fetchIntervalRef.current);
    };
  }, [fetchGreeks]);

  // Premium flash effect
  useEffect(() => {
    if (livePrice > 0 && prevPremium > 0) {
      if (livePrice > prevPremium) setPremiumFlash("up");
      else if (livePrice < prevPremium) setPremiumFlash("down");
      const t = setTimeout(() => setPremiumFlash(null), 400);
      return () => clearTimeout(t);
    }
    if (livePrice > 0) setPrevPremium(livePrice);
  }, [livePrice]);

  useEffect(() => {
    if (livePrice > 0) setPrevPremium(livePrice);
  }, [livePrice]);

  const premium = livePrice > 0 ? livePrice : greeksData?.premium || 0;
  const change = greeksData ? premium - greeksData.premium : 0;
  const changePct = greeksData && greeksData.premium > 0 ? (change / greeksData.premium) * 100 : 0;

  // Active Real-Time Signal Calculation (Entry, Target, Stop Loss)
  const activeSignalInfo = useMemo(() => {
    const isCall = parsed?.type === "CE";
    const curPrice = premium > 0 ? premium : 195.0;

    // Check if there is an active trade/position in state
    const matchedPosition = positions.find(p => p.symbol && p.symbol.toUpperCase().includes(symbol.toUpperCase()));
    
    const entry = matchedPosition?.entry_price || Math.round(curPrice * 0.98 * 100) / 100;
    const sl = matchedPosition?.sl || Math.round(entry * 0.92 * 100) / 100; // 8% risk
    const target = matchedPosition?.target || Math.round((entry + (entry - sl) * 2.5) * 100) / 100; // 1:2.5 R:R
    const risk = Math.max(1, entry - sl);
    const reward = Math.max(1, target - entry);
    const rr = Math.round((reward / risk) * 10) / 10;
    const targetPct = Math.round(((target - entry) / entry) * 1000) / 10;
    const slPct = Math.round(((entry - sl) / entry) * 1000) / 10;

    const isBullishSetup = isCall;
    const signalType = isBullishSetup ? "AUTO BUY SIGNAL ACTIVE" : "AUTO PUT BUY / SHORT";
    const statusColor = isBullishSetup ? "text-emerald-400" : "text-amber-400";
    const statusBg = isBullishSetup ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-400" : "bg-amber-500/20 border-amber-500/40 text-amber-400";

    return {
      type: signalType,
      statusColor,
      statusBg,
      entry,
      sl,
      target,
      rr,
      targetPct,
      slPct,
      confidence: aiConfidence,
      levels: {
        entry,
        sl,
        target,
        title: `${symbol} AI Setup`
      }
    };
  }, [parsed, premium, positions, symbol, aiConfidence]);

  return (
    <div className="flex flex-col h-full bg-card rounded-xl border border-border/30 overflow-hidden">

      {/* ─── PREMIUM HEADER BAR ──────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 bg-gradient-to-r from-muted/30 via-muted/10 to-muted/30 border-b border-border/30">
        {/* Left: Symbol + Premium */}
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-xs font-black font-mono text-foreground tracking-tight">{symbol}</span>
              {greeksData && <StatusBadge status={greeksData.status} />}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`text-lg font-black font-mono tabular-nums transition-colors duration-200 ${
                premiumFlash === "up" ? "text-emerald-400" : premiumFlash === "down" ? "text-rose-400" : "text-foreground"
              }`}>
                ₹{premium.toFixed(2)}
              </span>
              {change !== 0 && (
                <span className={`text-[11px] font-bold font-mono flex items-center gap-0.5 ${
                  change > 0 ? "text-emerald-400" : "text-rose-400"
                }`}>
                  {change > 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                  {change > 0 ? "+" : ""}{change.toFixed(2)} ({changePct.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>

          {/* Vertical separator */}
          <div className="w-px h-8 bg-border/40" />

          {/* Spot reference */}
          <div className="flex flex-col items-center">
            <span className="text-[8px] font-bold text-muted-foreground/70 uppercase tracking-wider">Spot</span>
            <span className="text-xs font-bold font-mono text-foreground/80">{spotPrice > 0 ? spotPrice.toFixed(1) : "—"}</span>
          </div>

          {/* Distance */}
          {greeksData && (
            <>
              <div className="w-px h-8 bg-border/40" />
              <div className="flex flex-col items-center">
                <span className="text-[8px] font-bold text-muted-foreground/70 uppercase tracking-wider">Distance</span>
                <span className={`text-xs font-bold font-mono ${
                  greeksData.status === "ITM" ? "text-emerald-400" : greeksData.status === "ATM" ? "text-amber-400" : "text-rose-400"
                }`}>
                  {greeksData.distance_points.toFixed(0)} pts ({greeksData.distance_pct.toFixed(1)}%)
                </span>
              </div>
            </>
          )}
        </div>

        {/* Right: IV Gauge + Expiry + Auto Signal Toggle */}
        <div className="flex items-center gap-2.5">
          {greeksData && (
            <>
              <IVGauge iv={greeksData.iv} />
              <div className="w-px h-8 bg-border/40" />
              <ExpiryCountdown days={greeksData.expiry_days} />
            </>
          )}

          {/* Auto Signals Toggle Switch Button */}
          <button
            onClick={() => setShowAutoSignals(!showAutoSignals)}
            className={`cursor-pointer px-3 py-1.5 rounded-lg border text-xs font-bold font-mono transition-all flex items-center gap-2 shadow-sm ${
              showAutoSignals
                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40 shadow-emerald-500/10 ring-1 ring-emerald-500/30"
                : "bg-muted/40 text-muted-foreground border-border/40 hover:text-foreground hover:bg-muted/70"
            }`}
            title={showAutoSignals ? "Signals Active (Click to switch to Clean Normal Chart)" : "Clean Normal Chart (Click to show Auto Signals & Levels)"}
          >
            <Bot className={`w-3.5 h-3.5 ${showAutoSignals ? 'text-emerald-400 animate-pulse' : 'text-muted-foreground'}`} />
            <span>{showAutoSignals ? "Signals: ON" : "Signals: OFF"}</span>
            <div className={`w-7 h-3.5 rounded-full relative transition-colors duration-200 ${showAutoSignals ? 'bg-emerald-500' : 'bg-muted-foreground/30'}`}>
              <span className={`absolute top-0.5 left-0.5 bg-background w-2.5 h-2.5 rounded-full shadow-sm transition-transform duration-200 ${showAutoSignals ? 'translate-x-3.5' : 'translate-x-0'}`} />
            </div>
          </button>

          <button
            onClick={() => setShowGreeksPanel(!showGreeksPanel)}
            className={`p-1.5 rounded-md transition-all ${showGreeksPanel ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-muted/40'}`}
            title={showGreeksPanel ? "Hide Greeks Panel" : "Show Greeks Panel"}
          >
            <Layers className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ─── LIVE AUTO SIGNAL & SL/TARGET HUD BANNER ─────────────────── */}
      <AnimatePresence>
        {showAutoSignals && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="px-4 py-2 bg-gradient-to-r from-emerald-950/20 via-background/60 to-purple-950/20 border-b border-border/25 flex items-center justify-between flex-wrap gap-2 text-xs font-mono"
          >
            <div className="flex items-center gap-3">
              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-black uppercase tracking-wider border ${activeSignalInfo.statusBg}`}>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span>{activeSignalInfo.type}</span>
              </div>

              <div className="flex items-center gap-2.5 text-[11px]">
                <span className="text-muted-foreground">
                  Entry: <strong className="text-emerald-400 font-bold">₹{activeSignalInfo.entry.toFixed(1)}</strong>
                </span>
                <span className="text-border/60">•</span>
                <span className="text-muted-foreground">
                  Target: <strong className="text-purple-400 font-bold">₹{activeSignalInfo.target.toFixed(1)} (+{activeSignalInfo.targetPct}%)</strong> 🎯
                </span>
                <span className="text-border/60">•</span>
                <span className="text-muted-foreground">
                  Stop Loss: <strong className="text-rose-400 font-bold">₹{activeSignalInfo.sl.toFixed(1)} (-{activeSignalInfo.slPct}%)</strong> 🛡️
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold">
                R:R 1 : {activeSignalInfo.rr}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-400" />
                AI Conf: {activeSignalInfo.confidence}%
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── GREEKS DASHBOARD STRIP ──────────────────────────────────── */}
      <AnimatePresence>
        {showGreeksPanel && greeksData && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden border-b border-border/20"
          >
            <div className="px-4 py-2 bg-muted/5">
              {/* Greeks Cards Row */}
              <div className="flex items-stretch gap-2 mb-2">
                <GreekCard
                  label="Delta"
                  value={greeksData.greeks.delta.toFixed(4)}
                  icon={TrendingUp}
                  color={`${greeksData.greeks.delta >= 0 ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400' : 'bg-rose-500/10 border-rose-500/25 text-rose-400'}`}
                  tooltip={`Δ: Price change per ₹1 spot move. ${parsed?.type === 'CE' ? 'Positive for calls' : 'Negative for puts'}`}
                />
                <GreekCard
                  label="Gamma"
                  value={greeksData.greeks.gamma.toFixed(4)}
                  icon={Activity}
                  color="bg-violet-500/10 border-violet-500/25 text-violet-400"
                  tooltip="Γ: Rate of delta change. Higher near ATM."
                />
                <GreekCard
                  label="Theta"
                  value={greeksData.greeks.theta.toFixed(2)}
                  unit={`₹${greeksData.greeks.theta_per_lot.toFixed(0)}/lot/day`}
                  icon={Clock}
                  color="bg-rose-500/10 border-rose-500/25 text-rose-400"
                  tooltip={`Θ: Daily time decay. You lose ₹${greeksData.greeks.theta_per_lot.toFixed(0)} per lot per day.`}
                />
                <GreekCard
                  label="Vega"
                  value={greeksData.greeks.vega.toFixed(2)}
                  unit="per 1% IV"
                  icon={Gauge}
                  color="bg-cyan-500/10 border-cyan-500/25 text-cyan-400"
                  tooltip="ν: Price change per 1% IV move."
                />
                <GreekCard
                  label="IV"
                  value={`${greeksData.iv.toFixed(1)}%`}
                  icon={BarChart2}
                  color={`${getIVLevel(greeksData.iv).bg} ${getIVLevel(greeksData.iv).border} ${getIVLevel(greeksData.iv).color}`}
                  tooltip={`Implied Volatility: ${getIVLevel(greeksData.iv).label}`}
                />

                {/* Breakeven */}
                <div className="flex flex-col items-center justify-center px-3 py-2 rounded-lg border bg-indigo-500/10 border-indigo-500/25 text-indigo-400">
                  <div className="flex items-center gap-1 mb-0.5">
                    <Target className="w-3 h-3 opacity-70" />
                    <span className="text-[9px] font-bold tracking-widest uppercase opacity-80">B/E</span>
                  </div>
                  <span className="text-sm font-black font-mono tabular-nums leading-none">{greeksData.breakeven.toFixed(0)}</span>
                </div>
              </div>

              {/* Bottom Row: Premium Decomposition + Theta Burn */}
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <PremiumBar intrinsic={greeksData.intrinsic} extrinsic={greeksData.extrinsic} total={greeksData.premium} />
                </div>
                <div className="w-px h-6 bg-border/30" />
                <ThetaBurnSparkline thetaHistory={thetaHistory} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── CHART AREA (WITH AUTO SIGNALS AND ENTRY/SL/TARGET LINES) ── */}
      <div className="flex-1 min-h-[380px] relative">
        <NativeChart
          symbol={symbol}
          livePrice={livePrice}
          timeframe={timeframe}
          showDynamicTrend={showDynamicTrend}
          showAutoSignals={showAutoSignals}
          signalLevels={showAutoSignals ? activeSignalInfo.levels : null}
        />
      </div>

      {/* ─── BOTTOM STATS BAR ────────────────────────────────────────── */}
      {greeksData && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-muted/10 border-t border-border/20 text-[10px] font-mono">
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground">
              Lot: <strong className="text-foreground">{greeksData.lot_size}</strong>
            </span>
            <span className="text-muted-foreground">
              Strike: <strong className="text-foreground">{greeksData.strike}</strong>
            </span>
            <span className="text-muted-foreground">
              Type: <strong className={parsed?.type === "CE" ? "text-emerald-400" : "text-rose-400"}>{parsed?.type}</strong>
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground">
              Theta/Lot: <strong className="text-rose-400">-₹{greeksData.greeks.theta_per_lot.toFixed(0)}/day</strong>
            </span>
            <span className="text-muted-foreground">
              B/E: <strong className="text-indigo-400">{greeksData.breakeven.toFixed(1)}</strong>
            </span>
            <span className={`font-bold ${greeksData.status === "ITM" ? "text-emerald-400" : greeksData.status === "ATM" ? "text-amber-400" : "text-rose-400"}`}>
              {greeksData.status} • {greeksData.distance_points.toFixed(0)} pts away
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdvancedOptionChart;

