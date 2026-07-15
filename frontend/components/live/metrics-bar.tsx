import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useLiveMarketStore } from '@/store/useLiveMarketStore';
import { useLiveSettingsStore } from '@/store/useLiveSettingsStore';

interface MetricsBarProps {
    isLoading: boolean;
}

export function MetricsBar({ isLoading }: MetricsBarProps) {
    const equity = useLiveMarketStore(state => state.equity);
    const pnl = useLiveMarketStore(state => state.pnl);
    const aiConfidence = useLiveMarketStore(state => state.aiConfidence);
    const riskStatus = useLiveMarketStore(state => state.riskStatus);
    const strategy = useLiveSettingsStore(state => state.strategy);
    const stoploss = useLiveSettingsStore(state => state.stoploss);

    return (
        <motion.div
            className="grid grid-cols-1 md:grid-cols-4 gap-6"
            initial="hidden"
            animate="show"
            variants={{
                hidden: { opacity: 0 },
                show: {
                    opacity: 1,
                    transition: { staggerChildren: 0.1 }
                }
            }}
        >
            {/* Card 1: Current Equity */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-warning to-amber-600 rounded-l-lg transition-shadow"></div>
                <div className="flex items-center gap-2 mb-0.5 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">💰 Current Equity</span>
                </div>
                <div className="text-xl md:text-2xl font-bold font-mono text-foreground pl-2 tracking-tight">
                    {isLoading ? "---" : `₹${(equity || 100000.00).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
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
                    {isLoading ? "---" : `${pnl >= 0 ? "+" : ""}₹${(pnl ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
                </div>
            </motion.div>



            {/* Card 4: Risk Engine */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-purple-500 to-indigo-600 rounded-l-lg transition-shadow"></div>
                <div className="flex items-center gap-2 mb-0.5 pl-2">
                    <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">🛡️ Risk Engine</span>
                </div>
                <div className="text-lg md:text-xl font-bold font-mono text-success pl-2 flex items-center gap-2">
                    ACTIVE
                    <div className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                    </div>
                </div>
                <div className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider pl-2 mt-0.5">
                    Limits OK &bull; SL {stoploss}%
                </div>
            </motion.div>
            {/* Card 5: Total Trades */}
            <motion.div
                variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
                className="stat-card px-3 py-2 flex flex-col justify-between relative overflow-hidden group"
            >
                <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-sky-500 to-indigo-600 rounded-l-lg transition-shadow"></div>

                <div className="flex items-center justify-between w-full mb-0.5">
                    <div className="space-y-0 pl-2">
                        <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-wider">📈 Total Trades</span>
                        </div>
                        <div className="text-xl md:text-2xl font-bold font-mono text-foreground tracking-tight">
                            {useLiveMarketStore(state => state.trades).length}
                        </div>
                        <div className="text-[8px] text-muted-foreground font-mono mt-0.5 uppercase">
                            Executed Today
                        </div>
                    </div>
                </div>
            </motion.div>
        </motion.div>
    );
}
