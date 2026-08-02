import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, ArrowUpRight, ArrowDownRight, Zap } from 'lucide-react';
import { useLiveMarketStore } from '@/store/useLiveMarketStore';

function formatTradeDisplay(symbol: string, price: number, side: string, qty?: number) {
    if (symbol === "NIFTY") {
        return side === "BUY" ? "Long NIFTY 50" : "Short NIFTY 50";
    }
    if (symbol === "BANKNIFTY") {
        return side === "BUY" ? "Long Bank Nifty" : "Short Bank Nifty";
    }
    if (symbol === "SENSEX") {
        return side === "BUY" ? "Long Sensex" : "Short Sensex";
    }
    const cleanSym = symbol.split(':')[1]?.replace('-EQ', '') || symbol;
    if (qty && qty > 1) {
        return `${side === "BUY" ? "Long" : "Short"} ${cleanSym} (${qty}x)`;
    }
    return `${side === "BUY" ? "Long" : "Short"} ${cleanSym}`;
}

export function ExecutionFeed() {
    const trades = useLiveMarketStore(state => state.trades);
    const todayTrades = trades.filter(t => {
        if (!t.time) return false;
        // Use IST timezone (not UTC) to avoid date rollover issues after 6:30 PM IST
        const formatter = new Intl.DateTimeFormat('en-IN', {
            timeZone: 'Asia/Kolkata',
            year: 'numeric', month: '2-digit', day: '2-digit'
        });
        const parts = formatter.formatToParts(new Date());
        const y = parts.find(p => p.type === 'year')?.value;
        const m = parts.find(p => p.type === 'month')?.value;
        const d = parts.find(p => p.type === 'day')?.value;
        const todayIST = `${y}-${m}-${d}`;
        const tradeDateStr = String(t.time).substring(0, 10);
        return tradeDateStr === todayIST;
    });

    return (
        <div className="glass-card rounded-xl p-6 border border-border/20 flex flex-col flex-1 h-full min-h-0">
            <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
                    <Zap className="w-5 h-5 text-warning" />
                    Live Execution Feed
                </h3>
                <span className="text-xs font-bold px-2 py-1 bg-muted/50 rounded-md text-muted-foreground">{todayTrades.length} Trades</span>
            </div>

            <div className="flex-1 overflow-y-auto pr-2 space-y-3 custom-scrollbar">
                <AnimatePresence mode="popLayout">
                    {todayTrades.length === 0 ? (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            className="h-full flex flex-col items-center justify-center text-center text-muted-foreground"
                        >
                            <motion.div
                                animate={{ y: [0, -10, 0] }}
                                transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
                            >
                                <Shield className="w-12 h-12 mb-4 opacity-20 mx-auto" />
                            </motion.div>
                            <p className="text-sm font-medium">System Armed & Ready</p>
                            <p className="text-[10px] mt-1 opacity-50 uppercase tracking-wider">Awaiting Signals...</p>
                        </motion.div>
                    ) : (
                        todayTrades.map((trade, i) => (
                            <motion.div
                                key={trade.id || i}
                                initial={{ opacity: 0, x: -20, height: 0 }}
                                animate={{
                                    opacity: 1,
                                    x: 0,
                                    height: 'auto',
                                    backgroundColor: trade.side === "BUY"
                                        ? ['rgba(16, 185, 129, 0.2)', 'rgba(16, 185, 129, 0)']
                                        : ['rgba(239, 68, 68, 0.2)', 'rgba(239, 68, 68, 0)']
                                }}
                                exit={{ opacity: 0, x: 20, height: 0 }}
                                transition={{
                                    type: "spring", stiffness: 500, damping: 30,
                                    backgroundColor: { duration: 1.5, ease: "easeOut" }
                                }}
                                className={`flex items-center justify-between p-3 rounded-lg border-l-4 bg-muted/10 hover:bg-muted/30 transition-colors ${trade.side === "BUY" ? "border-l-success" : "border-l-destructive"}`}
                            >
                                <div className="flex items-center gap-3">
                                    <div className={`p-2 rounded-lg ${trade.side === "BUY" ? "bg-success/10 text-success " : "bg-destructive/10 text-destructive "}`}>
                                        {trade.side === "BUY" ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-foreground tracking-tight">{formatTradeDisplay(trade.symbol, trade.price, trade.side, trade.quantity)}</p>
                                        <p className="text-[10px] font-mono tabular-nums text-muted-foreground">
                                            {String(trade.time).includes('T')
                                                ? String(trade.time).split('T')[1].substring(0, 8)
                                                : String(trade.time).includes(' ')
                                                    ? String(trade.time).split(' ')[1]
                                                    : trade.time}
                                        </p>
                                    </div>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm font-mono tabular-nums font-bold text-foreground">₹{trade.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                                    <p className={`text-[10px] font-bold uppercase tracking-widest mt-0.5 ${trade.side === "BUY" ? "text-success" : "text-destructive"}`}>
                                        {trade.side}
                                    </p>
                                </div>
                            </motion.div>
                        ))
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
