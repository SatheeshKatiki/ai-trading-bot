import React, { useState, useEffect } from 'react';
import { Moon, Sunrise, Sunset, TrendingUp, TrendingDown, Target, Zap, ShieldAlert, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';

interface BtstPredictorProps {
    symbol: string;
}

interface BtstData {
    status: string;
    action: string;
    gapUpProb: number;
    gapDownProb: number;
    reason: string;
    metrics: {
        momentum: number;
        rsi: number;
    };
    error?: string;
}

export function BtstPredictor({ symbol }: BtstPredictorProps) {
    const [data, setData] = useState<BtstData | null>(null);
    const [loading, setLoading] = useState(true);
    const [isActiveWindow, setIsActiveWindow] = useState(false);

    useEffect(() => {
        // Check if current time is within BTST active window (2:30 PM - 3:30 PM)
        const checkWindow = () => {
            const now = new Date();
            const hours = now.getHours();
            const minutes = now.getMinutes();
            const timeInMins = hours * 60 + minutes;
            // 14:30 = 870 mins, 15:30 = 930 mins
            if (timeInMins >= 870 && timeInMins <= 930) {
                setIsActiveWindow(true);
            } else {
                setIsActiveWindow(false);
            }
        };
        checkWindow();
        const timer = setInterval(checkWindow, 60000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        const fetchBtst = async () => {
            try {
                let querySymbol = "NIFTY";
                if (symbol.includes("BANKNIFTY")) querySymbol = "BANKNIFTY";
                else if (symbol.includes("FINNIFTY")) querySymbol = "FINNIFTY";
                else if (symbol.includes("MIDCPNIFTY")) querySymbol = "MIDCPNIFTY";
                
                const res = await fetch(`/api/btst?symbol=${querySymbol}`);
                const resData = await res.json();
                if (resData && !resData.error) {
                    setData(resData);
                } else if (resData && resData.error) {
                    setData({ status: "error", action: "AVOID", gapUpProb: 50, gapDownProb: 50, reason: resData.error, metrics: { momentum: 0, rsi: 50 } });
                }
            } catch (error) {
                console.error("Failed to fetch BTST prediction:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchBtst();
        const interval = setInterval(fetchBtst, 30000); // Poll every 30 seconds for BTST
        return () => clearInterval(interval);
    }, [symbol]);

    const isCall = data?.action === "CARRY CALL";
    const isPut = data?.action === "CARRY PUT";
    const isAvoid = data?.action === "AVOID";
    
    // Determine styles based on action
    let borderColor = "border-border/40";
    let glowColor = "";
    let iconColor = "text-muted-foreground";

    if (isCall) {
        borderColor = "border-emerald-500/40";
        glowColor = "shadow-[0_0_15px_rgba(16,185,129,0.1)]";
        iconColor = "text-emerald-500";
    } else if (isPut) {
        borderColor = "border-rose-500/40";
        glowColor = "shadow-[0_0_15px_rgba(244,63,94,0.1)]";
        iconColor = "text-rose-500";
    } else {
        borderColor = "border-warning/40";
        iconColor = "text-warning";
    }

    if (loading && !data) {
        return (
            <div className="glass-card border border-border/40 rounded-xl p-4 flex items-center justify-center h-[90px] animate-pulse">
                <div className="flex items-center gap-3">
                    <Moon className="w-5 h-5 text-muted-foreground animate-pulse" />
                    <span className="text-sm text-muted-foreground font-medium uppercase tracking-wider">Analyzing Overnight Risk...</span>
                </div>
            </div>
        );
    }

    return (
        <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`glass-card border ${borderColor} ${glowColor} rounded-2xl p-4 2xl:p-6 relative overflow-hidden transition-all duration-700 w-full h-full flex flex-col justify-center`}
        >
            <div className="relative z-10 flex flex-nowrap items-center justify-between gap-4">
                
                {/* Left Side: Icon & Title */}
                <div className="flex items-center gap-3 2xl:gap-5 flex-shrink min-w-0">
                    <div className={`w-14 h-14 2xl:w-16 2xl:h-16 shrink-0 rounded-full flex items-center justify-center bg-background/50 border ${borderColor}`}>
                        {isCall ? (
                            <Sunrise className={`w-6 h-6 ${iconColor}`} />
                        ) : isPut ? (
                            <Sunset className={`w-6 h-6 ${iconColor}`} />
                        ) : (
                            <Moon className={`w-6 h-6 ${iconColor}`} />
                        )}
                    </div>
                    <div>
                        <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1 whitespace-nowrap">
                                <Moon className="w-3 h-3" /> BTST Predictor
                            </span>
                            {!isActiveWindow && (
                                <span className="text-[8px] bg-muted/50 px-1.5 py-0.5 rounded text-muted-foreground uppercase">Off-Peak</span>
                            )}
                        </div>
                        <h3 className={`text-sm xl:text-base 2xl:text-xl font-black tracking-tight ${iconColor} uppercase flex items-center gap-1 2xl:gap-2 leading-tight`}>
                            {data?.action || "AVOID"}
                            {isCall && <TrendingUp className="w-3 h-3 2xl:w-4 2xl:h-4 shrink-0" />}
                            {isPut && <TrendingDown className="w-3 h-3 2xl:w-4 2xl:h-4 shrink-0" />}
                            {isAvoid && <AlertTriangle className="w-3 h-3 2xl:w-4 2xl:h-4 shrink-0" />}
                            {(isCall || isPut) && (
                                <span className="ml-1 md:ml-2 text-[8px] 2xl:text-[10px] px-1.5 py-0.5 rounded-md bg-background/80 border border-border/50 text-foreground whitespace-nowrap">
                                    🎯 {isCall ? "ATM CALL" : "ATM PUT"}
                                </span>
                            )}
                        </h3>
                        <p className="text-[10px] 2xl:text-xs text-muted-foreground font-medium mt-0.5 leading-tight max-w-none">
                            {data?.reason || "Waiting for market setup"}
                        </p>
                    </div>
                </div>

                {/* Right Side: Gap Probability Bar */}
                <div className="flex-1 md:flex-none w-full md:w-56 2xl:w-64 flex flex-col gap-1.5 shrink-0 pl-0 md:pl-4 border-t md:border-t-0 md:border-l border-border/20 pt-3 md:pt-0">
                    <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-wider">
                        <span className="text-emerald-500">Gap Up: {data?.gapUpProb || 50}%</span>
                        <span className="text-rose-500">Gap Down: {data?.gapDownProb || 50}%</span>
                    </div>
                    
                    {/* Dual Progress Bar */}
                    <div className="h-3 w-full bg-background/50 rounded-full overflow-hidden border border-border/20 flex">
                        <motion.div 
                            initial={{ width: '50%' }}
                            animate={{ width: `${data?.gapUpProb || 50}%` }}
                            transition={{ duration: 1, ease: "easeOut" }}
                            className="h-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]"
                        />
                        <motion.div 
                            initial={{ width: '50%' }}
                            animate={{ width: `${data?.gapDownProb || 50}%` }}
                            transition={{ duration: 1, ease: "easeOut" }}
                            className="h-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.3)]"
                        />
                    </div>
                    
                    <div className="flex justify-between mt-1.5 px-1">
                        <span className="text-[8px] 2xl:text-[9px] text-muted-foreground uppercase font-mono tracking-tight font-bold">
                            Est Gap: {(() => {
                                const pts = data?.gapUpProb ? Math.round(Math.abs(data.gapUpProb - 50) * 1.5) : 0;
                                return isCall ? `+${pts} to +${pts+25} pts` : isPut ? `-${pts} to -${pts+25} pts` : 'Flat (±15 pts)';
                            })()}
                        </span>
                        <span className={`text-[8px] 2xl:text-[9px] uppercase font-mono tracking-tight font-bold ${isCall ? 'text-emerald-500' : isPut ? 'text-rose-500' : 'text-muted-foreground'}`}>
                            {isCall ? "GIFT Nifty 🟢" : isPut ? "GIFT Nifty 🔴" : "Mixed Cues ⚪"}
                        </span>
                    </div>
                </div>

            </div>
        </motion.div>
    );
}
