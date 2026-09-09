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
    const unrealizedPnl = useLiveMarketStore(state => state.unrealizedPnl);
    const totalPnl = useLiveMarketStore(state => state.totalPnl);
    const marginDeployed = useLiveMarketStore(state => state.marginDeployed);
    const marginRoi = useLiveMarketStore(state => state.marginRoi);
    const accountRoi = useLiveMarketStore(state => state.accountRoi);
    const positionsDetail = useLiveMarketStore(state => state.positionsDetail);
    const openPositionsCount = useLiveMarketStore(state => state.openPositionsCount);
    const aiConfidence = useLiveMarketStore(state => state.aiConfidence);
    const riskStatus = useLiveMarketStore(state => state.riskStatus);
    const trades = useLiveMarketStore(state => state.trades);
    const tradingMode = useLiveMarketStore(state => state.tradingMode);
    const strategy = useLiveSettingsStore(state => state.strategy);
    const stoploss = useLiveSettingsStore(state => state.stoploss);

    const isLive = tradingMode === "live";

    // Dynamic ROI calculations (Strictly dynamic - NO hardcoding)
    const computedMargin = marginDeployed > 0 
        ? marginDeployed 
        : positionsDetail.reduce((acc, p) => acc + (p.entry_price * p.qty), 0);
    const computedMarginRoi = computedMargin > 0 ? (totalPnl / computedMargin) * 100 : (marginRoi || 0);
    const computedAccountRoi = equity > 0 ? (totalPnl / equity) * 100 : (accountRoi || 0);
    const isProfit = totalPnl > 0.009;
    const isLoss = totalPnl < -0.009;

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
            className="grid grid-cols-2 md:grid-cols-6 gap-4"
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
                className={`stat-card px-3 py-2 relative overflow-hidden group transition-all duration-300 ${
                    isProfit 
                        ? 'border-success/40 bg-success/[0.04] shadow-[0_0_20px_rgba(34,197,94,0.12)]' 
                        : isLoss 
                            ? 'border-destructive/40 bg-destructive/[0.04] shadow-[0_0_20px_rgba(239,68,68,0.12)]' 
                            : 'border-border/40'
                }`}
            >
                <div className={`absolute left-0 top-0 w-1.5 h-full rounded-l-lg transition-all duration-300 ${
                    isProfit 
                        ? 'bg-gradient-to-b from-success via-emerald-500 to-emerald-600 shadow-[0_0_8px_rgba(34,197,94,0.6)]' 
                        : isLoss 
                            ? 'bg-gradient-to-b from-destructive via-rose-500 to-rose-600 shadow-[0_0_8px_rgba(239,68,68,0.6)]' 
                            : 'bg-muted-foreground'
                }`}></div>
                <div className="flex items-center justify-between mb-0.5 pl-2 pr-1">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">📊 Today's PNL</span>
                    <div className="flex items-center gap-1.5">
                        {openPositionsCount > 0 && (
                            <span className="inline-flex items-center gap-1 text-[8px] font-black uppercase px-1.5 py-0.5 rounded bg-primary/20 text-primary animate-pulse">
                                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span> Live M2M
                            </span>
                        )}
                        {/* Dual Dynamic ROI Pill (Margin ROI) */}
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold tracking-tight border transition-colors ${
                            isProfit 
                                ? 'bg-success/15 border-success/30 text-success shadow-[0_0_10px_rgba(34,197,94,0.2)]' 
                                : isLoss 
                                    ? 'bg-destructive/15 border-destructive/30 text-destructive shadow-[0_0_10px_rgba(239,68,68,0.2)]' 
                                    : 'bg-muted/50 border-border text-muted-foreground'
                        }`}>
                            {computedMarginRoi >= 0 ? '+' : ''}{computedMarginRoi.toFixed(2)}% ROI
                        </span>
                    </div>
                </div>
                <div className={`text-xl md:text-2xl font-bold font-mono pl-2 tracking-tight flex items-center gap-1.5 ${
                    isProfit ? "text-success drop-shadow-[0_0_8px_rgba(34,197,94,0.3)]" : isLoss ? "text-destructive drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]" : "text-foreground"
                }`}>
                    {isProfit ? <TrendingUp className="w-4 h-4 animate-pulse text-success" /> : isLoss ? <TrendingDown className="w-4 h-4 animate-pulse text-destructive" /> : null}
                    {isLoading ? <div className="h-6 w-24 bg-muted animate-pulse rounded"></div> : `${totalPnl >= 0 ? "+" : ""}₹${(totalPnl ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                </div>
                {/* Account Impact & Margin Breakdown */}
                <div className="pl-2 text-[9px] font-mono mt-0.5 flex items-center gap-2 text-muted-foreground">
                    <span>Acct: <strong className={isProfit ? "text-success font-bold" : isLoss ? "text-destructive font-bold" : "text-foreground font-medium"}>{computedAccountRoi >= 0 ? '+' : ''}{computedAccountRoi.toFixed(2)}%</strong></span>
                    {computedMargin > 0 && (
                        <span className="border-l border-border/50 pl-2">Margin: ₹{computedMargin.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                    )}
                </div>
                {openPositionsCount > 0 && (
                    <div className="pl-2 text-[9px] font-mono text-muted-foreground mt-0.5 border-t border-border/20 pt-0.5">
                        Running: <span className={unrealizedPnl >= 0 ? "text-success font-semibold" : "text-destructive font-semibold"}>{unrealizedPnl >= 0 ? "+" : ""}₹{unrealizedPnl.toFixed(2)}</span> | Realized: {pnl >= 0 ? "+" : ""}₹{pnl.toFixed(2)}
                    </div>
                )}
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

            {/* Card 6: Paper / Live Mode Badge — always visible, unmissable */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 flex flex-col justify-center relative overflow-hidden group col-span-2 md:col-span-1"
                title={isLive ? "Live mode: real orders are being sent to the broker" : "Paper mode: simulated trades, no real orders"}
            >
                {/* Accent bar — blue for paper, red for live */}
                <div className={`absolute left-0 top-0 w-1 h-full rounded-l-lg transition-all duration-500 ${
                    isLive
                        ? 'bg-gradient-to-b from-rose-500 to-red-700'
                        : 'bg-gradient-to-b from-sky-400 to-blue-600'
                }`} />

                <div className="flex items-center gap-2 mb-1 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">🏦 Trading Mode</span>
                </div>

                {/* The badge itself */}
                <div className="pl-2 flex items-center gap-2">
                    {isLive ? (
                        // Red pulsing badge — must be impossible to miss
                        <span
                            id="trading-mode-live-badge"
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/20 border border-rose-500/50 text-rose-400 text-xs font-black uppercase tracking-widest animate-pulse"
                        >
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
                            </span>
                            LIVE
                        </span>
                    ) : (
                        // Calm blue badge — paper mode is safe
                        <span
                            id="trading-mode-paper-badge"
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-sky-500/15 border border-sky-500/40 text-sky-400 text-xs font-black uppercase tracking-widest"
                        >
                            <span className="relative flex h-2 w-2">
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-400" />
                            </span>
                            PAPER
                        </span>
                    )}
                </div>

                <div className="text-[8px] text-muted-foreground font-mono mt-1 pl-2 truncate">
                    {isLive ? 'Real orders → Broker' : 'Simulated — no risk'}
                </div>
            </motion.div>
        </motion.div>
    );
}

export const MetricsBar = React.memo(MetricsBarComponent);
