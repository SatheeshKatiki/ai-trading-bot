"use client";
import React, { useState, useEffect } from 'react';
import { Brain, TrendingUp, TrendingDown, Target, Zap, ShieldAlert, Activity, ArrowUp, ArrowDown } from 'lucide-react';
import { motion } from 'framer-motion';

interface MergedAiSignalProps {
    symbol: string;
}

interface SignalData {
    confidence: number;
    status: string;
    bias: string;
    error?: string;
}

function MergedAiSignalComponent({ symbol = "NIFTY" }: MergedAiSignalProps) {
    const [signalData, setSignalData] = useState<SignalData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSignal = async () => {
            try {
                let querySymbol = "NIFTY";
                if (symbol.includes("BANKNIFTY")) querySymbol = "BANKNIFTY";
                else if (symbol.includes("FINNIFTY")) querySymbol = "FINNIFTY";
                else if (symbol.includes("MIDCPNIFTY")) querySymbol = "MIDCPNIFTY";

                const res = await fetch(`/api/signals?symbol=${querySymbol}`);
                const data = await res.json();
                if (data && !data.error) {
                    setSignalData(data);
                } else if (data && data.error) {
                    setSignalData({ confidence: 0, status: data.error, bias: "NO SIGNAL" });
                }
            } catch (error) {
                console.error("Failed to fetch AI signal:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchSignal();
        const interval = setInterval(fetchSignal, 1500);
        return () => clearInterval(interval);
    }, [symbol]);

    const isBullish = signalData?.bias?.includes("BUY") || signalData?.bias?.includes("BULLISH");
    const isBearish = signalData?.bias?.includes("SELL") || signalData?.bias?.includes("BEARISH");
    const conf = signalData?.confidence || 0;

    // Determine styles based on signal
    let borderColor = "border-border/40";
    let glowColor = "";
    let iconColor = "text-muted-foreground";
    let Icon = Brain;
    let DirectionIcon = Activity;

    if (isBullish) {
        borderColor = "border-emerald-500/40";
        glowColor = "shadow-[0_0_20px_rgba(16,185,129,0.15)]";
        iconColor = "text-emerald-500";
        Icon = Zap;
        DirectionIcon = ArrowUp;
    } else if (isBearish) {
        borderColor = "border-rose-500/40";
        glowColor = "shadow-[0_0_20px_rgba(244,63,94,0.15)]";
        iconColor = "text-rose-500";
        Icon = ShieldAlert;
        DirectionIcon = ArrowDown;
    }

    if (loading && !signalData) {
        return (
            <div className="glass-card border border-border/40 rounded-xl p-6 flex items-center justify-center h-[120px] animate-pulse">
                <div className="flex items-center gap-3">
                    <Brain className="w-6 h-6 text-muted-foreground animate-bounce" />
                    <span className="text-sm text-muted-foreground font-medium uppercase tracking-wider">Neural Engine Loading...</span>
                </div>
            </div>
        );
    }

    // Determine sub-metrics
    const volSentiment = isBullish ? "BULLISH" : isBearish ? "BEARISH" : "NEUTRAL";
    const trendStrength = conf > 70 ? "STRONG" : conf > 50 ? "MODERATE" : "WEAK";

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`glass-card border ${borderColor} ${glowColor} rounded-2xl p-4 2xl:p-6 relative overflow-hidden transition-all duration-700 w-full h-full flex flex-col justify-center`}
        >
            {/* Background animated gradient */}
            <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
                <div className={`absolute inset-0 bg-gradient-to-r ${isBullish ? 'from-emerald-500' : isBearish ? 'from-rose-500' : 'from-primary'} to-transparent translate-x-[-100%] animate-[shimmer_3s_infinite]`}></div>
            </div>

            <div className="relative z-10 flex flex-nowrap items-center justify-between gap-2 2xl:gap-8">

                {/* 1. Main Signal Bias & Status */}
                <div className="flex items-center gap-3 2xl:gap-5 flex-1 min-w-0 overflow-hidden">
                    <div className={`w-14 h-14 2xl:w-16 2xl:h-16 shrink-0 rounded-full flex items-center justify-center bg-background/50 border ${borderColor} relative`}>
                        <Icon className={`w-6 h-6 2xl:w-8 2xl:h-8 ${iconColor}`} />
                        {/* Direction Arrow Badge */}
                        <div className={`absolute -bottom-1 -right-1 w-6 h-6 2xl:w-8 2xl:h-8 rounded-full border-2 border-background flex items-center justify-center ${isBullish ? 'bg-emerald-500 text-black' : isBearish ? 'bg-rose-500 text-white' : 'bg-muted text-muted-foreground'}`}>
                            <DirectionIcon className="w-4 h-4 2xl:w-5 2xl:h-5" strokeWidth={3} />
                        </div>
                    </div>
                    <div className="min-w-0 flex-1 overflow-hidden">
                        <div className="flex items-center gap-3 mb-1">
                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1 whitespace-nowrap">
                                <Target className="w-3 h-3 shrink-0" /> AI Market Direction
                            </span>
                        </div>
                        <h3 className={`text-sm xl:text-base 2xl:text-xl font-black tracking-tight ${iconColor} uppercase leading-tight truncate`}>
                            {signalData?.bias ? signalData.bias.replace(/ DETECTED| Detected/ig, "") : "NEUTRAL"}
                        </h3>
                        <p className="text-[9px] 2xl:text-sm text-muted-foreground font-medium tracking-wide mt-0.5 leading-tight truncate">
                            {signalData?.status || "Awaiting optimal setup..."}
                        </p>
                    </div>
                </div>

                {/* 2. Sub Metrics (Vol Sentiment & Trend) */}
                <div className="hidden lg:flex gap-1.5 2xl:gap-4 items-center bg-background/40 px-2 py-1.5 2xl:px-6 2xl:py-4 rounded-xl border border-border/20 flex-shrink-0 justify-center">
                    <div className="flex flex-col items-center justify-center border-r border-border/20 pr-1.5 2xl:pr-6">
                        <span className="text-[9px] text-muted-foreground font-bold uppercase tracking-wider mb-1">Vol Sentiment</span>
                        <span className={`text-[10px] 2xl:text-xs font-mono font-bold ${isBullish ? 'text-emerald-500' : isBearish ? 'text-rose-500' : 'text-warning'}`}>
                            {volSentiment}
                        </span>
                    </div>
                    <div className="flex flex-col items-center justify-center pl-1 2xl:pl-2">
                        <span className="text-[9px] text-muted-foreground font-bold uppercase tracking-wider mb-1">Trend Strength</span>
                        <span className={`text-[10px] 2xl:text-xs font-mono font-bold ${conf > 70 ? 'text-success' : 'text-muted-foreground'}`}>
                            {trendStrength}
                        </span>
                    </div>
                </div>

                {/* 3. Circular Signal Quality Meter */}
                <div className="flex items-center gap-2 2xl:gap-4 border-l-0 md:border-l border-border/20 pl-0 md:pl-2 2xl:pl-6 shrink-0 h-full">
                    <div className="hidden sm:flex flex-col items-center justify-center">
                        <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Signal Quality</span>
                        <span className={`text-[10px] 2xl:text-xs font-bold uppercase tracking-wider ${conf >= 75 ? "text-success" : conf >= 50 ? "text-warning" : "text-destructive"}`}>
                            {conf >= 75 ? "High Conviction" : conf >= 50 ? "Mild Bias" : "Scan Mode"}
                        </span>
                    </div>
                    <div className="relative w-[65px] h-[65px] 2xl:w-[90px] 2xl:h-[90px] group shrink-0">
                        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100">
                            <defs>
                                <mask id="mergedProgressMask">
                                    <circle
                                        cx="50" cy="50" r="42" fill="none"
                                        stroke="#ffffff" strokeWidth="8"
                                        strokeDasharray="263.89"
                                        strokeDashoffset={263.89 - (263.89 * conf) / 100}
                                        strokeLinecap="round" transform="rotate(-90 50 50)"
                                        className="transition-all duration-1000 ease-out"
                                    />
                                </mask>
                            </defs>
                            <circle cx="50" cy="50" r="42" fill="none" className="stroke-muted/30" strokeWidth="8" />

                            <foreignObject x="0" y="0" width="100" height="100" mask="url(#mergedProgressMask)">
                                <div className="w-full h-full" style={{ background: 'conic-gradient(var(--destructive) 0%, var(--warning) 50%, var(--success) 100%)' }}></div>
                            </foreignObject>
                        </svg>
                        <div className={`absolute inset-0 flex items-center justify-center text-[10px] 2xl:text-base font-black font-mono group-hover:scale-110 transition-transform ${conf >= 75 ? "text-success" : conf >= 50 ? "text-warning" : "text-destructive"}`}>
                            {conf}%
                        </div>
                    </div>
                </div>

            </div>
        </motion.div>
    );
}

export const MergedAiSignal = React.memo(MergedAiSignalComponent);
