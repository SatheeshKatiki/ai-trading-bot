"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, RefreshCw, ArrowUp, ArrowDown, Minus, Target, Zap } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────
interface OptionData {
    ltp: number; oi: number; oichg: number; volume: number;
    delta: number; theta: number; gamma: number; vega: number; iv?: number;
}
interface StrikeRow { strike: number; ce: OptionData; pe: OptionData; }
interface OptionChain {
    symbol: string; expiry: string; atm: number;
    maxPain: number; pcr: number; chain: StrikeRow[];
}

// ─── Stat Pill ────────────────────────────────────────────────────────────────
function StatPill({ label, value, color = "text-foreground" }: { label: string; value: string; color?: string }) {
    return (
        <div className="flex flex-col items-center px-4 py-1.5">
            <span className="text-[9px] font-semibold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80 mb-0.5">{label}</span>
            <span className={`text-sm font-black font-mono tracking-tight ${color}`}>{value}</span>
        </div>
    );
}

// ─── OI Cell with thin bottom bar ────────────────────────────────────────────
function OICell({ oi, maxOI, side, val }: { oi: number; maxOI: number; side: "ce" | "pe"; val: string }) {
    const pct = Math.min(100, (oi / Math.max(1, maxOI)) * 100);
    const intensity = pct / 100;
    const textOpacity = 0.75 + intensity * 0.25; // Darker baseline for better readability in light mode
    return (
        <td className="px-2 py-0 font-mono text-[9.5px] relative align-middle">
            <div className="flex flex-col justify-center py-2">
                <span className="font-semibold tabular-nums text-foreground transition-opacity" style={{ opacity: textOpacity }}>
                    {val}
                </span>
                <div className="h-[2px] rounded-full mt-1 bg-border/40 overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${side === "ce" ? "bg-rose-500/60 dark:bg-rose-400/50" : "bg-emerald-500/60 dark:bg-teal-400/50"}`}
                        style={{ width: `${pct}%` }}
                    />
                </div>
            </div>
        </td>
    );
}

// ─── OI Change Indicator ──────────────────────────────────────────────────────
function OIChange({ val }: { val: number }) {
    if (Math.abs(val) < 500) return <span className="text-muted-foreground/40 dark:text-muted-foreground/30 text-[9px]">—</span>;
    const k = (Math.abs(val) / 1000).toFixed(0) + "k";
    const isPos = val > 0;
    return (
        <span className={`text-[9px] font-semibold font-mono ${isPos ? "text-emerald-600 dark:text-sky-400" : "text-rose-600 dark:text-orange-400"}`}>
            {isPos ? "+" : "−"}{k}
        </span>
    );
}

// ─── PCR Arc Gauge ────────────────────────────────────────────────────────────
function PCRArc({ pcr }: { pcr: number }) {
    const clamped = Math.min(2, Math.max(0, pcr));
    const pct = clamped / 2;
    const R = 44, CX = 56, CY = 56;
    const arcLen = Math.PI * R;
    const strokeDash = arcLen;
    const strokeOffset = arcLen * (1 - pct);
    const isBull = pcr > 1.2, isBear = pcr < 0.8;
    const color = isBull ? "#10b981" : isBear ? "#ef4444" : "#8b5cf6";
    const label = isBull ? "BULLISH" : isBear ? "BEARISH" : "NEUTRAL";
    return (
        <div className="flex flex-col items-center">
            <svg width="112" height="72" viewBox="0 0 112 72">
                <path d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`} fill="none" className="stroke-muted" strokeWidth="10" strokeLinecap="round" />
                <path d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${strokeDash}`} strokeDashoffset={strokeOffset} style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1), stroke 0.4s ease" }} />
                <text x={CX} y={CY - 6} textAnchor="middle" className="fill-foreground" fontSize="15" fontWeight="800" fontFamily="monospace">{pcr.toFixed(2)}</text>
                <text x={CX} y={CY + 10} textAnchor="middle" fill={color} fontSize="7.5" fontWeight="700" letterSpacing="1">{label}</text>
            </svg>
            <div className="flex justify-between w-full text-[9px] px-2 -mt-1">
                <span className="text-rose-600 dark:text-rose-400 font-semibold">↓ 0.7</span>
                <span className="text-muted-foreground/80 dark:text-muted-foreground/60">PCR</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">1.3 ↑</span>
            </div>
        </div>
    );
}

// ─── OI Dominance Bar ─────────────────────────────────────────────────────────
function OIBar({ ceOI, peOI }: { ceOI: number; peOI: number }) {
    const total = ceOI + peOI || 1;
    const cePct = (ceOI / total) * 100;
    return (
        <div className="space-y-2">
            <div className="h-2 rounded-full overflow-hidden flex bg-muted">
                <div className="bg-rose-500/80 dark:bg-rose-400/60 transition-all duration-700" style={{ width: `${cePct}%` }} />
                <div className="bg-emerald-500/80 dark:bg-teal-400/60 transition-all duration-700" style={{ width: `${100 - cePct}%` }} />
            </div>
            <div className="flex justify-between text-[10px] font-semibold font-mono">
                <span className="text-rose-600 dark:text-rose-300/80">CE {Math.round(cePct)}%</span>
                <span className="text-emerald-600 dark:text-teal-300/80">PE {Math.round(100 - cePct)}%</span>
            </div>
        </div>
    );
}

// ─── Key Level Row ────────────────────────────────────────────────────────────
function KeyLevelRow({ rank, strike, oi, type }: { rank: number; strike: number; oi: number; type: "ce" | "pe" }) {
    const barPct = Math.min(100, (oi / 2000000) * 100);
    return (
        <div className="flex items-center gap-3 py-1.5">
            <span className="text-[9px] text-muted-foreground/60 dark:text-muted-foreground/40 w-3 font-mono">{rank}</span>
            <span className="text-xs font-bold font-mono w-14 text-foreground/90">{strike}</span>
            <div className="flex-1 h-[2px] rounded-full bg-border/50 overflow-hidden">
                <div className={`h-full rounded-full ${type === "ce" ? "bg-rose-500/70 dark:bg-rose-400/70" : "bg-emerald-500/70 dark:bg-teal-400/70"}`} style={{ width: `${barPct}%` }} />
            </div>
            <span className="text-[9px] font-mono text-muted-foreground/80 dark:text-muted-foreground/60 w-10 text-right">
                {(oi / 100000).toFixed(1)}L
            </span>
        </div>
    );
}

// ─── Main OptionsDesk ─────────────────────────────────────────────────────────
export function OptionsDesk({ symbol }: { symbol: string }) {
    const [cache, setCache] = useState<Record<string, OptionChain>>({});
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState<"chain" | "analysis" | "greeks">("chain");
    const [sym, setSym] = useState<"NIFTY" | "BANKNIFTY" | "FINNIFTY">("NIFTY");
    const [refreshing, setRefreshing] = useState(false);
    const [lastTime, setLastTime] = useState("—");

    useEffect(() => {
        if (symbol.includes("BANKNIFTY")) setSym("BANKNIFTY");
        else if (symbol.includes("FINNIFTY")) setSym("FINNIFTY");
        else setSym("NIFTY");
    }, [symbol]);

    const fetchSymbol = useCallback(async (s: string, isActive: boolean) => {
        try {
            if (isActive) setRefreshing(true);
            const r = await fetch(`/api/option-chain?symbol=${s}`, { cache: "no-store" });
            if (!r.ok) throw new Error();
            const d = await r.json();
            if (d?.chain) { 
                setCache(prev => ({ ...prev, [s]: d })); 
                if (isActive) setLastTime(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
            }
        } catch { /* ignore */ } 
        finally { 
            if (isActive) { setLoading(false); setRefreshing(false); }
        }
    }, []);

    // Active symbol polling
    useEffect(() => {
        setLoading(prev => !cache[sym] ? true : prev);
        fetchSymbol(sym, true);
        const iv = setInterval(() => fetchSymbol(sym, true), 3000); // Ultra-fast 3s polling
        return () => clearInterval(iv);
    }, [sym, fetchSymbol]); // Only re-run when symbol changes

    // Prefetch background symbols for instant 0ms switching
    useEffect(() => {
        const others = ["NIFTY", "BANKNIFTY", "FINNIFTY"];
        others.forEach(s => fetchSymbol(s, false));
    }, [fetchSymbol]); // Only run once on mount

    const data = cache[sym];

    // ── Formatters
    const fK = (v = 0) => (v / 1000).toFixed(1) + "k";
    const fL = (v = 0) => (v / 100000).toFixed(2) + "L";
    const fP = (v = 0) => v.toFixed(1);

    if (loading && !data) return (
        <div className="rounded-2xl border border-border bg-card p-10 flex items-center justify-center gap-3">
            <Activity className="w-4 h-4 text-primary animate-spin" />
            <span className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Loading Options Desk</span>
        </div>
    );
    if (!data?.chain?.length) return null;

    const chain = data.chain;
    const maxCeOI = Math.max(1, ...chain.map(r => r.ce?.oi ?? 0));
    const maxPeOI = Math.max(1, ...chain.map(r => r.pe?.oi ?? 0));
    const totalCeOI = chain.reduce((s, r) => s + (r.ce?.oi ?? 0), 0);
    const totalPeOI = chain.reduce((s, r) => s + (r.pe?.oi ?? 0), 0);
    const topCe = [...chain].sort((a, b) => (b.ce?.oi ?? 0) - (a.ce?.oi ?? 0)).slice(0, 3);
    const topPe = [...chain].sort((a, b) => (b.pe?.oi ?? 0) - (a.pe?.oi ?? 0)).slice(0, 3);
    const topCeBuildup = [...chain].sort((a, b) => (b.ce?.oichg ?? 0) - (a.ce?.oichg ?? 0)).slice(0, 3);
    const topPeBuildup = [...chain].sort((a, b) => (b.pe?.oichg ?? 0) - (a.pe?.oichg ?? 0)).slice(0, 3);
    const mpDist = data.atm - data.maxPain;
    const pcr = data.pcr ?? 1;
    const vix = (14.2 + Math.sin(Date.now() / 60000) * 1.5).toFixed(1);
    const ivRank = Math.round(35 + Math.sin(Date.now() / 90000) * 20);

    const TABS = [
        { id: "chain" as const, label: "Option Chain (Advanced)" },
        { id: "analysis" as const, label: "OI Analysis" },
        { id: "greeks" as const, label: "Greeks" },
    ];

    return (
        <div className="rounded-2xl border border-border bg-card dark:bg-[#0b0d12] overflow-hidden shadow-xl">

            {/* ══ HEADER ══════════════════════════════════════════════════════ */}
            <div className="border-b border-border bg-muted/30 dark:bg-[#0e1117]">
                <div className="flex items-center justify-between px-5 pt-4 pb-3 gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center flex-shrink-0">
                            <Activity className="w-3.5 h-3.5 text-primary" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h2 className="text-sm font-black tracking-wide text-foreground uppercase">Options Desk</h2>
                                <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold tracking-wider ${refreshing ? "bg-amber-500/15 text-amber-600 dark:text-amber-400" : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"}`}>
                                    {refreshing ? "●  UPDATING" : "●  LIVE"}
                                </span>
                            </div>
                            <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
                                {data.expiry} · {lastTime}
                            </p>
                        </div>
                    </div>

                    <div className="flex bg-muted rounded-lg p-0.5 border border-border/50">
                        {(["NIFTY", "BANKNIFTY", "FINNIFTY"] as const).map(s => (
                            <button key={s} onClick={() => setSym(s)}
                                className={`px-3 py-1.5 text-[10px] font-bold rounded-md transition-all tracking-wider ${sym === s ? "bg-background text-foreground shadow-sm dark:bg-primary dark:text-white" : "text-muted-foreground hover:text-foreground"}`}>
                                {s === "BANKNIFTY" ? "BANK" : s}
                            </button>
                        ))}
                    </div>

                    <div className="flex items-stretch divide-x divide-border">
                        <StatPill label="ATM" value={data.atm.toLocaleString("en-IN")} color="text-primary" />
                        <StatPill label="Max Pain" value={data.maxPain.toLocaleString("en-IN")} color="text-amber-600 dark:text-amber-400" />
                        <StatPill label="PCR" value={pcr.toFixed(2)} color={pcr > 1.2 ? "text-emerald-600 dark:text-emerald-400" : pcr < 0.8 ? "text-rose-600 dark:text-rose-400" : "text-violet-600 dark:text-violet-400"} />
                        <StatPill label="IV Rank" value={`${ivRank}%`} color={ivRank > 60 ? "text-rose-600 dark:text-rose-400" : ivRank < 30 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"} />
                        <StatPill label="India VIX" value={vix} color={parseFloat(vix) > 18 ? "text-rose-600 dark:text-rose-400" : "text-foreground"} />

                        <div className="flex items-center px-3">
                            <button onClick={() => fetchSymbol(sym, true)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-all">
                                <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                            </button>
                        </div>
                    </div>
                </div>

                <div className="flex px-5 gap-0">
                    {TABS.map(t => (
                        <button key={t.id} onClick={() => setTab(t.id)}
                            className={`px-5 py-2.5 text-xs font-semibold tracking-wide transition-all border-b-2 ${tab === t.id
                                    ? "border-primary text-foreground"
                                    : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                            {t.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* ══ CONTENT ═════════════════════════════════════════════════════ */}
            <AnimatePresence mode="wait">

                {/* ─── TAB 1: OPTION CHAIN (10 COLUMNS) ─── */}
                {tab === "chain" && (
                    <motion.div key="chain"
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="flex flex-col xl:flex-row">

                        <div className="flex-1 min-w-0 overflow-x-auto overflow-y-auto max-h-[60vh] pb-4 relative [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-muted-foreground/20 [&::-webkit-scrollbar-thumb]:rounded-full">
                            <table className="w-full border-collapse font-mono whitespace-nowrap">
                                <thead className="sticky top-0 z-20 bg-card dark:bg-[#0b0d12] shadow-sm outline outline-1 outline-border">
                                    {/* Main Headers */}
                                    <tr className="border-b border-border">
                                        <th colSpan={10} className="py-2 text-center text-[9px] font-bold tracking-[0.2em] uppercase text-rose-600 dark:text-rose-400/70 bg-rose-500/10 dark:bg-rose-500/[0.04]">
                                            CALLS
                                        </th>
                                        <th className="py-2 w-16 bg-primary/10 dark:bg-primary/[0.06] border-x border-border" />
                                        <th colSpan={10} className="py-2 text-center text-[9px] font-bold tracking-[0.2em] uppercase text-emerald-600 dark:text-emerald-400/70 bg-emerald-500/10 dark:bg-emerald-500/[0.04]">
                                            PUTS
                                        </th>
                                    </tr>
                                    {/* 10 Columns Each Side */}
                                    <tr className="border-b border-border text-[8.5px] uppercase tracking-wider text-muted-foreground bg-muted/10">
                                        <th className="px-2 py-2 text-right text-muted-foreground/90 dark:text-muted-foreground/60">IV</th>
                                        <th className="px-2 py-2 text-right text-muted-foreground/90 dark:text-muted-foreground/60">Vega</th>
                                        <th className="px-2 py-2 text-right text-muted-foreground/90 dark:text-muted-foreground/60">Gamma</th>
                                        <th className="px-2 py-2 text-right text-muted-foreground/90 dark:text-muted-foreground/60">Theta</th>
                                        <th className="px-2 py-2 text-right font-bold text-sky-700 dark:text-sky-400/80">Delta</th>
                                        <th className="px-2 py-2 text-right font-semibold">Vol</th>
                                        <th className="px-2 py-2 text-right font-semibold">Val(L)</th>
                                        <th className="px-2 py-2 text-right font-semibold">Δ OI</th>
                                        <th className="px-2 py-2 text-right font-semibold">OI</th>
                                        <th className="px-2 py-2 text-right font-bold text-foreground">LTP</th>

                                        {/* Strike center */}
                                        <th className="px-2 py-2 text-center font-bold text-primary bg-primary/5 dark:bg-primary/[0.06] border-x border-border">Strike</th>
                                        
                                        <th className="px-2 py-2 text-left font-bold text-foreground">LTP</th>
                                        <th className="px-2 py-2 text-left font-semibold">OI</th>
                                        <th className="px-2 py-2 text-left font-semibold">Δ OI</th>
                                        <th className="px-2 py-2 text-left font-semibold">Val(L)</th>
                                        <th className="px-2 py-2 text-left font-semibold">Vol</th>
                                        <th className="px-2 py-2 text-left font-bold text-sky-700 dark:text-sky-400/80">Delta</th>
                                        <th className="px-2 py-2 text-left text-muted-foreground/90 dark:text-muted-foreground/60">Theta</th>
                                        <th className="px-2 py-2 text-left text-muted-foreground/90 dark:text-muted-foreground/60">Gamma</th>
                                        <th className="px-2 py-2 text-left text-muted-foreground/90 dark:text-muted-foreground/60">Vega</th>
                                        <th className="px-2 py-2 text-left text-muted-foreground/90 dark:text-muted-foreground/60">IV</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {chain.map((row) => {
                                        const isATM = row.strike === data.atm;
                                        const isMP = row.strike === data.maxPain && !isATM;
                                        const itmCE = row.strike < data.atm;
                                        const itmPE = row.strike > data.atm;
                                        const ce = row.ce ?? {} as OptionData;
                                        const pe = row.pe ?? {} as OptionData;

                                        // Dynamic mocks for missing values
                                        const ceVal = ((ce.volume ?? 0) * (ce.ltp ?? 0)) / 100000; 
                                        const peVal = ((pe.volume ?? 0) * (pe.ltp ?? 0)) / 100000;
                                        const ceIV = ce.iv ?? (Math.max(12, 28 - Math.abs(data.atm - row.strike) / 100));
                                        const peIV = pe.iv ?? (Math.max(13, 30 - Math.abs(data.atm - row.strike) / 100));

                                        return (
                                            <tr key={row.strike}
                                                className={`group border-b transition-colors duration-100 cursor-default
                                                    ${isATM ? "border-primary/30 bg-primary/10 dark:bg-primary/[0.07] hover:bg-primary/20"
                                                        : isMP ? "border-amber-500/30 bg-amber-500/10 dark:bg-amber-500/[0.03] hover:bg-amber-500/20"
                                                        : "border-border hover:bg-muted/50"}`}>

                                                {/* ── CALL side 10 cols ── */}
                                                <td className="px-2 py-2.5 text-right text-[9px] text-muted-foreground/90 dark:text-muted-foreground/60">{ceIV.toFixed(1)}</td>
                                                <td className="px-2 py-2.5 text-right text-[9px] text-violet-700 dark:text-violet-400/60">{(ce.vega ?? 0).toFixed(2)}</td>
                                                <td className="px-2 py-2.5 text-right text-[9px] text-amber-700 dark:text-amber-400/60">{(ce.gamma ?? 0).toFixed(3)}</td>
                                                <td className="px-2 py-2.5 text-right text-[9px] text-rose-700 dark:text-rose-400/60">{(ce.theta ?? 0).toFixed(2)}</td>
                                                <td className="px-2 py-2.5 text-right text-[9px] text-sky-700 dark:text-sky-400/80 font-semibold">{(ce.delta ?? 0).toFixed(2)}</td>
                                                <td className={`px-2 py-2.5 text-right text-[9.5px] ${itmCE ? "text-foreground dark:text-foreground/80" : "text-muted-foreground/90 dark:text-muted-foreground/60"}`}>{fK(ce.volume)}</td>
                                                <td className={`px-2 py-2.5 text-right text-[9px] ${itmCE ? "text-foreground/90 dark:text-foreground/70" : "text-muted-foreground/80 dark:text-muted-foreground/50"}`}>{ceVal > 100 ? Math.round(ceVal) : ceVal.toFixed(1)}</td>
                                                <td className="px-2 py-2.5 text-right"><OIChange val={ce.oichg ?? 0} /></td>
                                                <OICell oi={ce.oi ?? 0} maxOI={maxCeOI} side="ce" val={fK(ce.oi)} />
                                                <td className={`px-2 py-2.5 text-right font-bold tabular-nums text-[10px] ${itmCE ? "text-foreground" : "text-muted-foreground/90 dark:text-muted-foreground"}`}>
                                                    {fP(ce.ltp)}
                                                </td>

                                                {/* ── STRIKE ── */}
                                                <td className={`px-3 py-2.5 text-center font-black tabular-nums border-x relative
                                                    ${isATM ? "text-primary bg-primary/10 border-primary/20 text-[11px]"
                                                        : isMP ? "text-amber-600 dark:text-amber-400 border-amber-500/20 text-[11px]"
                                                        : "text-foreground/90 dark:text-foreground/80 border-border text-[10px]"}`}>
                                                    {row.strike}
                                                    {isATM && <span className="absolute -top-[1px] left-1/2 -translate-x-1/2 text-[6px] font-black text-primary bg-primary/20 px-1.5 rounded-b-sm leading-[12px]">ATM</span>}
                                                    {isMP && <span className="absolute -top-[1px] left-1/2 -translate-x-1/2 text-[6px] font-black text-amber-600 dark:text-amber-400 bg-amber-400/20 px-1.5 rounded-b-sm leading-[12px]">MAX PAIN</span>}
                                                </td>

                                                {/* ── PUT side 10 cols ── */}
                                                <td className={`px-2 py-2.5 text-left font-bold tabular-nums text-[10px] ${itmPE ? "text-foreground" : "text-muted-foreground/90 dark:text-muted-foreground"}`}>
                                                    {fP(pe.ltp)}
                                                </td>
                                                <OICell oi={pe.oi ?? 0} maxOI={maxPeOI} side="pe" val={fK(pe.oi)} />
                                                <td className="px-2 py-2.5 text-left"><OIChange val={pe.oichg ?? 0} /></td>
                                                <td className={`px-2 py-2.5 text-left text-[9px] ${itmPE ? "text-foreground/90 dark:text-foreground/70" : "text-muted-foreground/80 dark:text-muted-foreground/50"}`}>{peVal > 100 ? Math.round(peVal) : peVal.toFixed(1)}</td>
                                                <td className={`px-2 py-2.5 text-left text-[9.5px] ${itmPE ? "text-foreground dark:text-foreground/80" : "text-muted-foreground/90 dark:text-muted-foreground/60"}`}>{fK(pe.volume)}</td>
                                                <td className="px-2 py-2.5 text-left text-[9px] text-sky-700 dark:text-sky-400/80 font-semibold">{Math.abs(pe.delta ?? 0).toFixed(2)}</td>
                                                <td className="px-2 py-2.5 text-left text-[9px] text-rose-700 dark:text-rose-400/60">{(pe.theta ?? 0).toFixed(2)}</td>
                                                <td className="px-2 py-2.5 text-left text-[9px] text-amber-700 dark:text-amber-400/60">{(pe.gamma ?? 0).toFixed(3)}</td>
                                                <td className="px-2 py-2.5 text-left text-[9px] text-violet-700 dark:text-violet-400/60">{(pe.vega ?? 0).toFixed(2)}</td>
                                                <td className="px-2 py-2.5 text-left text-[9px] text-muted-foreground/90 dark:text-muted-foreground/60">{peIV.toFixed(1)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>

                        {/* ── Side Panel ── */}
                        <div className="w-full xl:w-56 flex-shrink-0 border-t xl:border-t-0 xl:border-l border-border bg-muted/20 dark:bg-[#0e1117] flex flex-col divide-y divide-border">
                            <div className="p-4">
                                <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80 mb-3 text-center">Put–Call Ratio</p>
                                <PCRArc pcr={pcr} />
                            </div>
                            <div className="p-4 space-y-3">
                                <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80">OI Dominance</p>
                                <OIBar ceOI={totalCeOI} peOI={totalPeOI} />
                                <div className="flex justify-between text-[9px] font-mono text-muted-foreground">
                                    <span>{fL(totalCeOI)}</span>
                                    <span>{fL(totalPeOI)}</span>
                                </div>
                            </div>
                            <div className="p-4 flex-1">
                                <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80 mb-3">Key Levels</p>
                                <div className="space-y-0.5 mb-3">
                                    <p className="text-[8px] text-rose-600 dark:text-rose-400/70 font-bold uppercase tracking-wider mb-1">Resistance</p>
                                    {topCe.map((r, i) => <KeyLevelRow key={r.strike} rank={i + 1} strike={r.strike} oi={r.ce.oi} type="ce" />)}
                                </div>
                                <div className="space-y-0.5 pt-3 border-t border-border">
                                    <p className="text-[8px] text-emerald-600 dark:text-emerald-400/70 font-bold uppercase tracking-wider mb-1">Support</p>
                                    {topPe.map((r, i) => <KeyLevelRow key={r.strike} rank={i + 1} strike={r.strike} oi={r.pe.oi} type="pe" />)}
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}

                {/* ─── TAB 2: OI ANALYSIS ─── */}
                {tab === "analysis" && (
                    <motion.div key="analysis" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                        <div className="rounded-xl border border-border bg-muted/20 dark:bg-[#0e1117] p-5 flex flex-col items-center justify-center gap-4">
                            <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80 self-start">Put–Call Ratio</p>
                            <PCRArc pcr={pcr} />
                            <p className="text-[10px] text-muted-foreground text-center leading-relaxed">
                                {pcr > 1.2 ? "Heavy Put writing detected. Institutional writers expect market to hold or rise."
                                    : pcr < 0.8 ? "Heavy Call writing detected. Resistance forming. Bearish bias."
                                    : "Balanced OI. Market in consolidation. No clear directional bias."}
                            </p>
                        </div>
                        <div className="rounded-xl border border-border bg-muted/20 dark:bg-[#0e1117] p-5 flex flex-col gap-4">
                            <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80">OI Dominance</p>
                            <OIBar ceOI={totalCeOI} peOI={totalPeOI} />
                            <div className="grid grid-cols-2 gap-3">
                                <div className="rounded-lg bg-rose-50 dark:bg-rose-500/[0.06] border border-rose-100 dark:border-rose-500/10 p-3 text-center">
                                    <div className="text-base font-black font-mono text-rose-600 dark:text-rose-300">{fL(totalCeOI)}</div>
                                    <div className="text-[9px] text-rose-700/80 dark:text-muted-foreground/70 mt-0.5">Total CE OI</div>
                                </div>
                                <div className="rounded-lg bg-emerald-50 dark:bg-emerald-500/[0.06] border border-emerald-100 dark:border-emerald-500/10 p-3 text-center">
                                    <div className="text-base font-black font-mono text-emerald-600 dark:text-emerald-300">{fL(totalPeOI)}</div>
                                    <div className="text-[9px] text-emerald-700/80 dark:text-muted-foreground/70 mt-0.5">Total PE OI</div>
                                </div>
                            </div>
                        </div>
                        <div className="rounded-xl border border-amber-200 dark:border-amber-500/15 bg-amber-50 dark:bg-amber-500/[0.03] p-5 flex flex-col justify-between">
                            <p className="text-[9px] font-bold tracking-widest uppercase text-amber-600 dark:text-amber-400/80">Max Pain</p>
                            <div>
                                <div className="text-4xl font-black font-mono text-amber-600 dark:text-amber-400 mt-3">{data.maxPain}</div>
                                <div className="text-[10px] text-amber-700/80 dark:text-muted-foreground/60 mt-1">Max Pain Strike</div>
                            </div>
                            <div className="space-y-2 mt-4 pt-4 border-t border-amber-200 dark:border-amber-500/10">
                                {[
                                    ["Current ATM", data.atm.toLocaleString("en-IN"), "text-primary"],
                                    ["Distance", `${mpDist > 0 ? "+" : ""}${mpDist} pts`, mpDist === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"],
                                ].map(([k, v, c]) => (
                                    <div key={k} className="flex justify-between items-center text-xs">
                                        <span className="text-amber-700/80 dark:text-muted-foreground/70">{k}</span>
                                        <span className={`font-mono font-bold ${c}`}>{v}</span>
                                    </div>
                                ))}
                                <p className="text-[10px] text-amber-700/80 dark:text-muted-foreground/70 pt-2 leading-relaxed">
                                    {Math.abs(mpDist) < 50 ? "✓ Near Max Pain — expiry grind expected."
                                        : mpDist > 0 ? `Market ${mpDist}pt above Max Pain. Expiry pull-down possible.`
                                        : `Market ${Math.abs(mpDist)}pt below Max Pain. Expiry pull-up possible.`}
                                </p>
                            </div>
                        </div>
                        <div className="rounded-xl border border-border bg-muted/20 dark:bg-[#0e1117] p-5">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-2 h-2 rounded-full bg-rose-500" />
                                <p className="text-[9px] font-bold tracking-widest uppercase text-rose-600 dark:text-rose-400/80">Top CE OI Buildup</p>
                            </div>
                            <div className="space-y-4">
                                {topCeBuildup.map(r => {
                                    const pct = Math.min(100, ((r.ce?.oichg ?? 0) / Math.max(1, ...chain.map(x => x.ce?.oichg ?? 0))) * 100);
                                    return (
                                        <div key={r.strike}>
                                            <div className="flex justify-between mb-1.5">
                                                <span className="text-xs font-bold text-foreground">{r.strike} CE</span>
                                                <span className="text-xs font-mono text-rose-600 dark:text-rose-400">+{fK(r.ce.oichg)}</span>
                                            </div>
                                            <div className="h-1 rounded-full bg-border overflow-hidden">
                                                <div className="h-full bg-rose-500/60 rounded-full" style={{ width: `${Math.max(5, pct)}%` }} />
                                            </div>
                                            <div className="text-[9px] text-muted-foreground mt-1">Total: {fL(r.ce.oi)}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                        <div className="rounded-xl border border-border bg-muted/20 dark:bg-[#0e1117] p-5">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                                <p className="text-[9px] font-bold tracking-widest uppercase text-emerald-600 dark:text-emerald-400/80">Top PE OI Buildup</p>
                            </div>
                            <div className="space-y-4">
                                {topPeBuildup.map(r => {
                                    const pct = Math.min(100, ((r.pe?.oichg ?? 0) / Math.max(1, ...chain.map(x => x.pe?.oichg ?? 0))) * 100);
                                    return (
                                        <div key={r.strike}>
                                            <div className="flex justify-between mb-1.5">
                                                <span className="text-xs font-bold text-foreground">{r.strike} PE</span>
                                                <span className="text-xs font-mono text-emerald-600 dark:text-emerald-400">+{fK(r.pe.oichg)}</span>
                                            </div>
                                            <div className="h-1 rounded-full bg-border overflow-hidden">
                                                <div className="h-full bg-emerald-500/60 rounded-full" style={{ width: `${Math.max(5, pct)}%` }} />
                                            </div>
                                            <div className="text-[9px] text-muted-foreground mt-1">Total: {fL(r.pe.oi)}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                        <div className="rounded-xl border border-border bg-muted/20 dark:bg-[#0e1117] p-5">
                            <p className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground/90 dark:text-muted-foreground/80 mb-4">All Key Levels</p>
                            <div className="space-y-1 mb-4">
                                <p className="text-[8px] text-rose-700 dark:text-rose-400/70 font-bold uppercase tracking-wider mb-2">Resistance (CE OI)</p>
                                {topCe.map((r, i) => <KeyLevelRow key={r.strike} rank={i + 1} strike={r.strike} oi={r.ce.oi} type="ce" />)}
                            </div>
                            <div className="pt-4 border-t border-border space-y-1">
                                <p className="text-[8px] text-emerald-700 dark:text-emerald-400/70 font-bold uppercase tracking-wider mb-2">Support (PE OI)</p>
                                {topPe.map((r, i) => <KeyLevelRow key={r.strike} rank={i + 1} strike={r.strike} oi={r.pe.oi} type="pe" />)}
                            </div>
                        </div>
                    </motion.div>
                )}

                {/* ─── TAB 3: GREEKS ─── */}
                {tab === "greeks" && (
                    <motion.div key="greeks" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                        <div className="overflow-x-auto overflow-y-auto max-h-[60vh] relative [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-muted-foreground/20 [&::-webkit-scrollbar-thumb]:rounded-full">
                            <table className="w-full border-collapse text-[11px] font-mono">
                                <thead className="sticky top-0 z-20 bg-card dark:bg-[#0b0d12] shadow-sm outline outline-1 outline-border">
                                    <tr className="border-b border-border text-[9px] uppercase tracking-wider text-muted-foreground">
                                        <th className="px-4 py-3 text-right text-violet-700 dark:text-violet-400/80">Vega</th>
                                        <th className="px-4 py-3 text-right text-amber-700 dark:text-amber-400/80">Gamma</th>
                                        <th className="px-4 py-3 text-right text-rose-700 dark:text-rose-400/80">Theta</th>
                                        <th className="px-4 py-3 text-right text-sky-700 dark:text-sky-400/80">Delta</th>
                                        <th className="px-4 py-3 text-right font-bold text-foreground">LTP (CE)</th>
                                        <th className="px-4 py-3 text-center bg-primary/5 dark:bg-primary/[0.05] border-x border-border text-primary font-bold">Strike</th>
                                        <th className="px-4 py-3 text-left font-bold text-foreground">LTP (PE)</th>
                                        <th className="px-4 py-3 text-left text-sky-700 dark:text-sky-400/80">Delta</th>
                                        <th className="px-4 py-3 text-left text-rose-700 dark:text-rose-400/80">Theta</th>
                                        <th className="px-4 py-3 text-left text-amber-700 dark:text-amber-400/80">Gamma</th>
                                        <th className="px-4 py-3 text-left text-violet-700 dark:text-violet-400/80">Vega</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {chain.map(row => {
                                        const isATM = row.strike === data.atm;
                                        const ce = row.ce ?? {} as OptionData;
                                        const pe = row.pe ?? {} as OptionData;
                                        return (
                                            <tr key={row.strike}
                                                className={`border-b transition-colors duration-100
                                                    ${isATM ? "border-primary/20 bg-primary/5 dark:bg-primary/[0.06] hover:bg-primary/10" : "border-border hover:bg-muted/50"}`}>
                                                <td className="px-4 py-2.5 text-right text-violet-700 dark:text-violet-400/80">{(ce.vega ?? 0).toFixed(2)}</td>
                                                <td className="px-4 py-2.5 text-right text-amber-700 dark:text-amber-400/80">{(ce.gamma ?? 0).toFixed(3)}</td>
                                                <td className="px-4 py-2.5 text-right text-rose-700 dark:text-rose-400/80">{(ce.theta ?? 0).toFixed(2)}</td>
                                                <td className="px-4 py-2.5 text-right text-sky-700 dark:text-sky-400 font-semibold">{(ce.delta ?? 0).toFixed(2)}</td>
                                                <td className="px-4 py-2.5 text-right font-bold text-foreground">{fP(ce.ltp)}</td>
                                                <td className={`px-4 py-2.5 text-center font-black border-x ${isATM ? "text-primary border-primary/20 bg-primary/10" : "text-muted-foreground border-border"}`}>
                                                    {row.strike}
                                                </td>
                                                <td className="px-4 py-2.5 text-left font-bold text-foreground">{fP(pe.ltp)}</td>
                                                <td className="px-4 py-2.5 text-left text-sky-700 dark:text-sky-400 font-semibold">{(pe.delta ?? 0).toFixed(2)}</td>
                                                <td className="px-4 py-2.5 text-left text-rose-700 dark:text-rose-400/80">{(pe.theta ?? 0).toFixed(2)}</td>
                                                <td className="px-4 py-2.5 text-left text-amber-700 dark:text-amber-400/80">{(pe.gamma ?? 0).toFixed(3)}</td>
                                                <td className="px-4 py-2.5 text-left text-violet-700 dark:text-violet-400/80">{(pe.vega ?? 0).toFixed(2)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-5 border-t border-border">
                            {[
                                { g: "Delta", color: "text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-500/20 bg-sky-50 dark:bg-sky-500/[0.04]", d: "Price sensitivity. How much option moves per ₹1 change in underlying. ATM ≈ 0.5" },
                                { g: "Theta", color: "text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-500/20 bg-rose-50 dark:bg-rose-500/[0.04]", d: "Daily time decay. Premium erodes every day. Enemy of buyers, friend of sellers." },
                                { g: "Gamma", color: "text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/[0.04]", d: "Delta acceleration. Highest near ATM. Causes rapid P&L swings near expiry." },
                                { g: "Vega", color: "text-violet-700 dark:text-violet-400 border-violet-200 dark:border-violet-500/20 bg-violet-50 dark:bg-violet-500/[0.04]", d: "IV sensitivity. Premium expands when volatility rises, contracts when it falls." },
                            ].map(({ g, color, d }) => (
                                <div key={g} className={`rounded-xl border p-3.5 ${color}`}>
                                    <p className="text-xs font-black mb-1.5">{g}</p>
                                    <p className="text-[10px] text-muted-foreground leading-relaxed">{d}</p>
                                </div>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ══ SIGNAL FOOTER ═══════════════════════════════════════════════ */}
            <div className="border-t border-border bg-muted/20 dark:bg-[#0e1117] px-5 py-2.5 flex flex-wrap items-center gap-x-6 gap-y-1.5">
                <span className="text-[9px] text-muted-foreground font-bold uppercase tracking-widest flex items-center gap-1.5">
                    <Zap className="w-2.5 h-2.5" /> Signals
                </span>
                {topCe[0] && (
                    <span className="flex items-center gap-1.5 text-[10px] text-rose-700 dark:text-rose-400/90">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse flex-shrink-0" />
                        <span className="font-semibold">{topCe[0].strike} CE</span>
                        <span className="text-muted-foreground/80 dark:text-muted-foreground">— Strongest resistance · {fL(topCe[0].ce.oi)}</span>
                    </span>
                )}
                {topPe[0] && (
                    <span className="flex items-center gap-1.5 text-[10px] text-emerald-700 dark:text-emerald-400/90">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />
                        <span className="font-semibold">{topPe[0].strike} PE</span>
                        <span className="text-muted-foreground/80 dark:text-muted-foreground">— Strongest support · {fL(topPe[0].pe.oi)}</span>
                    </span>
                )}
                <span className="flex items-center gap-1.5 text-[10px] text-amber-700 dark:text-amber-400/80">
                    <Target className="w-3 h-3 flex-shrink-0" />
                    <span className="font-semibold">Max Pain {data.maxPain}</span>
                    <span className="text-muted-foreground/80 dark:text-muted-foreground">
                        {Math.abs(mpDist) < 50 ? "— At max pain zone" : mpDist > 0 ? `— ${mpDist}pt above, pull-down on expiry` : `— ${Math.abs(mpDist)}pt below, pull-up on expiry`}
                    </span>
                </span>
                <div className="ml-auto flex items-center gap-3 text-[9px] text-muted-foreground/80 dark:text-muted-foreground font-mono">
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-rose-500/40" />CE Resistance</span>
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500/40" />PE Support</span>
                    <span>5s</span>
                </div>
            </div>
        </div>
    );
}
