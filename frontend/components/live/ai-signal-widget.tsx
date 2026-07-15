import React, { useState, useEffect } from 'react';
import { Brain, TrendingUp, TrendingDown, Target, Zap, ShieldAlert, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface AiSignalWidgetProps {
    symbol: string;
}

interface SignalData {
    confidence: number;
    status: string;
    bias: string;
    error?: string;
}

export function AiSignalWidget({ symbol }: AiSignalWidgetProps) {
    const [signalData, setSignalData] = useState<SignalData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSignal = async () => {
            try {
                // Determine base index from symbol
                let querySymbol = "NIFTY";
                if (symbol.includes("BANKNIFTY")) querySymbol = "BANKNIFTY";
                else if (symbol.includes("FINNIFTY")) querySymbol = "FINNIFTY";
                else if (symbol.includes("MIDCPNIFTY")) querySymbol = "MIDCPNIFTY";
                
                const res = await fetch(`/api/signals?symbol=${querySymbol}`);
                const data = await res.json();
                if (data && !data.error) {
                    setSignalData(data);
                } else if (data && data.error) {
                    setSignalData({ confidence: 0, status: "Error", bias: data.error });
                }
            } catch (error) {
                console.error("Failed to fetch AI signal:", error);
            } finally {
                setLoading(false);
            }
        };

        // Initial fetch
        fetchSignal();

        // Poll every 5 seconds
        const interval = setInterval(fetchSignal, 5000);
        return () => clearInterval(interval);
    }, [symbol]);

    const isBullish = signalData?.bias?.includes("BUY") || signalData?.bias?.includes("BULLISH");
    const isBearish = signalData?.bias?.includes("SELL") || signalData?.bias?.includes("BEARISH");
    
    // Determine styles based on signal
    let borderColor = "border-border/40";
    let glowColor = "";
    let iconColor = "text-muted-foreground";
    let Icon = Brain;
    let confidenceColor = "bg-primary";

    if (isBullish) {
        borderColor = "border-emerald-500/30";
        glowColor = "shadow-[0_0_15px_rgba(16,185,129,0.15)]";
        iconColor = "text-emerald-500";
        Icon = TrendingUp;
        confidenceColor = "bg-emerald-500";
    } else if (isBearish) {
        borderColor = "border-rose-500/30";
        glowColor = "shadow-[0_0_15px_rgba(244,63,94,0.15)]";
        iconColor = "text-rose-500";
        Icon = TrendingDown;
        confidenceColor = "bg-rose-500";
    }

    if (loading && !signalData) {
        return (
            <div className="glass-card border border-border/40 rounded-xl p-4 flex items-center justify-center h-[90px] animate-pulse">
                <div className="flex items-center gap-3">
                    <Brain className="w-5 h-5 text-muted-foreground animate-bounce" />
                    <span className="text-sm text-muted-foreground font-medium uppercase tracking-wider">Neural Engine Loading...</span>
                </div>
            </div>
        );
    }

    const conf = signalData?.confidence || 0;

    return (
        <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`glass-card border ${borderColor} ${glowColor} rounded-xl p-4 relative overflow-hidden transition-all duration-700`}
        >
            {/* Background animated gradient */}
            <div className="absolute inset-0 opacity-5 pointer-events-none">
                <div className={`absolute inset-0 bg-gradient-to-r ${isBullish ? 'from-emerald-500' : isBearish ? 'from-rose-500' : 'from-primary'} to-transparent translate-x-[-100%] animate-[shimmer_3s_infinite]`}></div>
            </div>

            <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                {/* Left side: Icon and Signal Text */}
                <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center bg-background/50 border ${borderColor}`}>
                        {isBullish ? (
                            <Zap className={`w-6 h-6 ${iconColor}`} />
                        ) : isBearish ? (
                            <ShieldAlert className={`w-6 h-6 ${iconColor}`} />
                        ) : (
                            <Activity className={`w-6 h-6 ${iconColor}`} />
                        )}
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className={`text-xl font-black tracking-tight ${iconColor}`}>
                                {signalData?.bias || "NEUTRAL"}
                            </h3>
                            {conf > 80 && (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-primary/20 text-primary uppercase tracking-wider">
                                    High Conviction
                                </span>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mt-0.5">
                            {signalData?.status || "Awaiting optimal setup..."}
                        </p>
                    </div>
                </div>

                {/* Right side: Confidence Bar */}
                <div className="w-full md:w-48 flex flex-col gap-2">
                    <div className="flex justify-between items-center text-xs font-bold uppercase tracking-wider">
                        <span className="text-muted-foreground flex items-center gap-1">
                            <Target className="w-3 h-3" /> AI Confidence
                        </span>
                        <span className={iconColor}>{conf}%</span>
                    </div>
                    <div className="h-2 w-full bg-background/50 rounded-full overflow-hidden border border-border/20">
                        <motion.div 
                            initial={{ width: 0 }}
                            animate={{ width: `${conf}%` }}
                            transition={{ duration: 1, ease: "easeOut" }}
                            className={`h-full ${confidenceColor} shadow-[0_0_10px_rgba(255,255,255,0.3)]`}
                        />
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
