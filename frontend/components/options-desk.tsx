"use client";

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Activity, Shield, TrendingDown, TrendingUp, Settings2 } from 'lucide-react';

interface OptionData {
    ltp: number;
    oi: number;
    oichg: number;
    volume: number;
    delta: number;
    theta: number;
    gamma: number;
    vega: number;
}

interface StrikeRow {
    strike: number;
    ce: OptionData;
    pe: OptionData;
}

interface OptionChain {
    symbol: string;
    expiry: string;
    atm: number;
    maxPain: number;
    pcr: number;
    chain: StrikeRow[];
}

export function OptionsDesk({ symbol }: { symbol: string }) {
    const [data, setData] = useState<OptionChain | null>(null);
    const [loading, setLoading] = useState(true);
    const [showGreeks, setShowGreeks] = useState(false);

    useEffect(() => {
        const fetchChain = async () => {
            try {
                let querySymbol = "NIFTY";
                if (symbol.includes("BANKNIFTY")) querySymbol = "BANKNIFTY";
                else if (symbol.includes("FINNIFTY")) querySymbol = "FINNIFTY";
                else if (symbol.includes("MIDCPNIFTY")) querySymbol = "MIDCPNIFTY";

                const res = await fetch(`/api/option-chain?symbol=${querySymbol}`);
                const resData = await res.json();
                if (resData) setData(resData);
            } catch (error) {
                console.error("Failed to fetch option chain:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchChain();
        const interval = setInterval(fetchChain, 15000); // 15s refresh for options
        return () => clearInterval(interval);
    }, [symbol]);

    if (loading && !data) {
        return (
            <div className="glass-card border border-border/40 rounded-2xl p-6 h-[400px] flex items-center justify-center animate-pulse">
                <div className="flex flex-col items-center gap-4">
                    <Activity className="w-8 h-8 text-muted-foreground animate-spin" />
                    <span className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Loading Options Desk...</span>
                </div>
            </div>
        );
    }

    if (!data || !data.chain || !Array.isArray(data.chain)) return null;

    const formatOI = (oi: number) => (oi / 1000).toFixed(1) + 'k';
    const formatLTP = (ltp: number) => ltp.toFixed(1);

    // Calculate max OI for heatmap coloring safely
    const maxCeOI = Math.max(1, ...data.chain.map(r => r.ce?.oi || 0));
    const maxPeOI = Math.max(1, ...data.chain.map(r => r.pe?.oi || 0));

    return (
        <div className="glass-card border border-border/40 rounded-2xl overflow-hidden flex flex-col w-full shadow-lg">
            
            {/* Header: Market Stats */}
            <div className="bg-background/50 border-b border-border/40 p-4 2xl:p-6 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center border border-primary/30">
                        <Activity className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                        <h2 className="text-sm 2xl:text-base font-black uppercase tracking-wider text-foreground">Options Desk</h2>
                        <div className="flex items-center gap-2 text-[10px] 2xl:text-xs text-muted-foreground font-mono mt-0.5">
                            <span>{data.symbol}</span>
                            <span>•</span>
                            <span>Exp: {data.expiry}</span>
                        </div>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 2xl:gap-8">
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Max Pain</span>
                        <span className="text-sm 2xl:text-base font-black text-warning font-mono">{data.maxPain}</span>
                    </div>
                    <div className="w-px h-8 bg-border/40"></div>
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Put-Call Ratio</span>
                        <span className={`text-sm 2xl:text-base font-black font-mono ${data.pcr > 1.2 ? 'text-success' : data.pcr < 0.8 ? 'text-destructive' : 'text-primary'}`}>
                            {data.pcr}
                        </span>
                    </div>
                    <button 
                        onClick={() => setShowGreeks(!showGreeks)}
                        className={`ml-2 px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors border ${showGreeks ? 'bg-primary/20 border-primary/50 text-primary' : 'bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground'}`}
                    >
                        <Settings2 className="w-3.5 h-3.5 inline mr-1.5" />
                        Greeks
                    </button>
                </div>
            </div>

            {/* Option Chain Grid */}
            <div className="w-full overflow-x-auto custom-scrollbar">
                <table className="w-full text-xs font-mono text-right whitespace-nowrap">
                    <thead>
                        <tr className="bg-background/80 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/40">
                            {/* CALLS HEADER */}
                            {showGreeks && <th className="px-3 py-2 font-medium">Vega</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium">Gamma</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium">Theta</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium">Delta</th>}
                            <th className="px-3 py-2 font-medium">Vol</th>
                            <th className="px-3 py-2 font-medium">Chg OI</th>
                            <th className="px-3 py-2 font-medium">OI</th>
                            <th className="px-3 py-2 font-medium text-foreground">LTP (CE)</th>
                            
                            {/* STRIKE HEADER */}
                            <th className="px-4 py-2 font-black text-center text-primary bg-primary/5 border-x border-border/40">Strike</th>
                            
                            {/* PUTS HEADER */}
                            <th className="px-3 py-2 font-medium text-foreground text-left">LTP (PE)</th>
                            <th className="px-3 py-2 font-medium text-left">OI</th>
                            <th className="px-3 py-2 font-medium text-left">Chg OI</th>
                            <th className="px-3 py-2 font-medium text-left">Vol</th>
                            {showGreeks && <th className="px-3 py-2 font-medium text-left">Delta</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium text-left">Theta</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium text-left">Gamma</th>}
                            {showGreeks && <th className="px-3 py-2 font-medium text-left">Vega</th>}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                        {data.chain.map((row) => {
                            const isATM = row.strike === data.atm;
                            const ce = row.ce || { ltp:0, oi:0, oichg:0, volume:0, delta:0, theta:0, gamma:0, vega:0 };
                            const pe = row.pe || { ltp:0, oi:0, oichg:0, volume:0, delta:0, theta:0, gamma:0, vega:0 };
                            
                            // Heatmap calculations
                            const ceOIPct = ce.oi / maxCeOI;
                            const peOIPct = pe.oi / maxPeOI;

                            return (
                                <tr key={row.strike} className={`hover:bg-muted/10 transition-colors ${isATM ? 'bg-primary/5' : ''}`}>
                                    
                                    {/* CALLS */}
                                    {showGreeks && <td className="px-3 py-2 text-muted-foreground/70">{ce.vega.toFixed(1)}</td>}
                                    {showGreeks && <td className="px-3 py-2 text-muted-foreground/70">{ce.gamma.toFixed(3)}</td>}
                                    {showGreeks && <td className="px-3 py-2 text-rose-500/80">{ce.theta.toFixed(1)}</td>}
                                    {showGreeks && <td className="px-3 py-2 font-medium text-success/90">{ce.delta.toFixed(2)}</td>}
                                    
                                    <td className="px-3 py-2 text-muted-foreground">{formatOI(ce.volume)}</td>
                                    <td className={`px-3 py-2 ${ce.oichg > 0 ? 'text-success' : 'text-destructive'}`}>
                                        {ce.oichg > 0 ? '+' : ''}{formatOI(ce.oichg)}
                                    </td>
                                    <td className="px-3 py-2 relative">
                                        <div className="absolute right-0 top-0 bottom-0 bg-rose-500/10" style={{ width: `${ceOIPct * 100}%` }}></div>
                                        <span className="relative z-10 font-bold">{formatOI(ce.oi)}</span>
                                    </td>
                                    <td className="px-3 py-2 font-black text-foreground">{formatLTP(ce.ltp)}</td>

                                    {/* STRIKE */}
                                    <td className={`px-4 py-2 font-black text-center border-x border-border/40 ${isATM ? 'text-primary bg-primary/10 border-primary/30 shadow-[inset_0_0_10px_rgba(var(--primary),0.2)]' : 'text-muted-foreground'}`}>
                                        {row.strike}
                                    </td>

                                    {/* PUTS */}
                                    <td className="px-3 py-2 font-black text-foreground text-left">{formatLTP(pe.ltp)}</td>
                                    <td className="px-3 py-2 relative text-left">
                                        <div className="absolute left-0 top-0 bottom-0 bg-emerald-500/10" style={{ width: `${peOIPct * 100}%` }}></div>
                                        <span className="relative z-10 font-bold">{formatOI(pe.oi)}</span>
                                    </td>
                                    <td className={`px-3 py-2 text-left ${pe.oichg > 0 ? 'text-success' : 'text-destructive'}`}>
                                        {pe.oichg > 0 ? '+' : ''}{formatOI(pe.oichg)}
                                    </td>
                                    <td className="px-3 py-2 text-muted-foreground text-left">{formatOI(pe.volume)}</td>
                                    
                                    {showGreeks && <td className="px-3 py-2 font-medium text-destructive/90 text-left">{pe.delta.toFixed(2)}</td>}
                                    {showGreeks && <td className="px-3 py-2 text-rose-500/80 text-left">{pe.theta.toFixed(1)}</td>}
                                    {showGreeks && <td className="px-3 py-2 text-muted-foreground/70 text-left">{pe.gamma.toFixed(3)}</td>}
                                    {showGreeks && <td className="px-3 py-2 text-muted-foreground/70 text-left">{pe.vega.toFixed(1)}</td>}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            
            {/* Footer / Legend */}
            <div className="bg-background/30 p-2 px-4 border-t border-border/20 flex items-center justify-between text-[9px] text-muted-foreground font-medium uppercase tracking-widest">
                <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-rose-500/30"></div> Call Resistance</span>
                    <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-emerald-500/30"></div> Put Support</span>
                </div>
                <span>Updates every 15s</span>
            </div>
        </div>
    );
}
