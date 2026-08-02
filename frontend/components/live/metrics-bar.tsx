"use client";
import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useLiveMarketStore } from '@/store/useLiveMarketStore';
import { useLiveSettingsStore } from '@/store/useLiveSettingsStore';

interface MetricsBarProps {
    isLoading: boolean;
    isMarketOpen: boolean;
}

function MetricsBarComponent({ isLoading, isMarketOpen }: MetricsBarProps) {
    const equity = useLiveMarketStore(state => state.equity);
    const pnl = useLiveMarketStore(state => state.pnl);
    const aiConfidence = useLiveMarketStore(state => state.aiConfidence);
    const riskStatus = useLiveMarketStore(state => state.riskStatus);
    const trades = useLiveMarketStore(state => state.trades);
    const strategy = useLiveSettingsStore(state => state.strategy);
    const stoploss = useLiveSettingsStore(state => state.stoploss);

    // Determine risk engine colour based on actual riskStatus
    const isRiskOk = !riskStatus || riskStatus === "ACTIVE" || riskStatus === "OK" || riskStatus === "IDLE";
    const riskColor = isRiskOk ? 'text-success' : 'text-destructive';
    const riskDotColor = isRiskOk ? 'bg-success' : 'bg-destructive';
    const riskLabel = riskStatus || "ACTIVE";

    // AI confidence colour
    const confColor = aiConfidence >= 70 ? 'text-success' : aiConfidence >= 50 ? 'text-warning' : 'text-destructive';

    // Today's trade count
    const todayCount = trades.filter(t => {
        if (!t.time) return false;
        const now = new Date();
        const formatter = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' });
        const parts = formatter.formatToParts(now);
        const y = parts.find(p => p.type === 'year')?.value;
        const m = parts.find(p => p.type === 'month')?.value;
        const d = parts.find(p => p.type === 'day')?.value;
        const today = `${y}-${m}-${d}`;
        return String(t.time).startsWith(today) || String(t.time).substring(0, 10) === today;
    }).length;

    return (
        <motion.div
            className="grid grid-cols-2 md:grid-cols-5 gap-4"
            initial="hidden"
            animate="show"
            variants={{
                hidden: { opacity: 0 },
                show: {
                    opacity: 1,
                    transition: { staggerChildren: 0.08 }
                }
            }}
        >
            {/* Card 1: Market Status + Current Equity */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-warning to-amber-600 rounded-l-lg transition-shadow"></div>
                <div className="flex items-center gap-2 mb-0.5 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">💰 Current Equity</span>
                    {/* Market Status pill */}
                    <span className={`ml-auto text-[8px] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-wider ${isMarketOpen ? 'bg-success/10 text-success' : 'bg-muted/50 text-muted-foreground'}`}>
                        {isMarketOpen ? '🟢 Open' : '🔴 Closed'}
                    </span>
                </div>
                <div className="text-xl md:text-2xl font-bold font-mono text-foreground pl-2 tracking-tight">
                    {isLoading ? <div className="h-6 w-24 bg-muted animate-pulse rounded"></div> : `₹${(equity || 100000.00).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
                </div>
            </motion.div>

            {/* Card 2: Today's PNL */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
            >
                <div className={`absolute left-0 top-0 w-1 h-full rounded-l-lg transition-shadow ${pnl >= 0 ? 'bg-gradient-to-b from-success to-emerald-600 ' : 'bg-gradient-to-b from-destructive to-rose-600 '}`}></div>
                <div className="flex items-center gap-2 mb-0.5 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">📊 Today's PNL</span>
                </div>
                <div className={`text-xl md:text-2xl font-bold font-mono pl-2 tracking-tight flex items-center gap-1 ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                    {pnl >= 0 ? <TrendingUp className="w-4 h-4 animate-pulse" /> : <TrendingDown className="w-4 h-4 animate-pulse" />}
                    {isLoading ? <div className="h-6 w-24 bg-muted animate-pulse rounded"></div> : `${pnl >= 0 ? "+" : ""}₹${(pnl ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
                </div>
            </motion.div>

            {/* Card 3: AI Confidence */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
                title="AI signal confidence computed on the last bar by the active strategy"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-blue-500 to-cyan-600 rounded-l-lg transition-shadow"></div>
                <div className="flex items-center gap-2 mb-1 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">🧠 AI Confidence</span>
                </div>
                <div className={`text-xl md:text-2xl font-bold font-mono pl-2 tracking-tight ${confColor}`}>
                    {aiConfidence > 0 ? `${aiConfidence.toFixed(0)}%` : '—'}
                </div>
                {/* Progress bar */}
                <div className="pl-2 pr-2 mt-1">
                    <div className="w-full h-1 bg-muted/50 rounded-full overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all duration-500 ${aiConfidence >= 70 ? 'bg-success' : aiConfidence >= 50 ? 'bg-warning' : 'bg-destructive'}`}
                            style={{ width: `${aiConfidence}%` }}
                        />
                    </div>
                </div>
            </motion.div>

            {/* Card 4: Risk Engine (uses real riskStatus) */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-purple-500 to-indigo-600 rounded-l-lg transition-shadow"></div>
                <div className="flex items-center gap-2 mb-0.5 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">🛡️ Risk Engine</span>
                </div>
                <div className={`text-lg md:text-xl font-bold font-mono pl-2 flex items-center gap-2 ${riskColor}`}>
                    {isRiskOk ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4 animate-pulse" />}
                    {riskLabel}
                    <div className="relative flex h-2 w-2">
                        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${riskDotColor} opacity-75`}></span>
                        <span className={`relative inline-flex rounded-full h-2 w-2 ${riskDotColor}`}></span>
                    </div>
                </div>
                <div className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider pl-2 mt-0.5">
                    SL {stoploss}% • Max Loss Guard
                </div>
            </motion.div>

            {/* Card 5: Total Trades Today */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 flex flex-col justify-between relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-sky-500 to-indigo-600 rounded-l-lg transition-shadow"></div>

                <div className="flex items-center justify-between w-full mb-0.5">
                    <div className="space-y-0 pl-2">
                        <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">📈 Today's Trades</span>
                        </div>
                        <div className="text-xl md:text-2xl font-bold font-mono text-foreground tracking-tight">
                            {todayCount}
                        </div>
                        <div className="text-[8px] text-muted-foreground font-mono mt-0.5 uppercase">
                            of {trades.length} total
                        </div>
                    </div>
                </div>
            </motion.div>
        </motion.div>
    );
}

export const MetricsBar = React.memo(MetricsBarComponent);
