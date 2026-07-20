"use client";
import { useState } from "react";
import { useLiveMarketStore } from "@/store/useLiveMarketStore";
import { XCircle, Clock, CheckCircle2, AlertTriangle, X } from "lucide-react";
import { toast } from "sonner";

// IST-aware today date string
function getTodayIST(): string {
    const formatter = new Intl.DateTimeFormat('en-IN', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric', month: '2-digit', day: '2-digit'
    });
    const parts = formatter.formatToParts(new Date());
    const y = parts.find(p => p.type === 'year')?.value;
    const m = parts.find(p => p.type === 'month')?.value;
    const d = parts.find(p => p.type === 'day')?.value;
    return `${y}-${m}-${d}`;
}

// Confirmation Modal Component
function ConfirmModal({
    title, message, confirmLabel = "Confirm", onConfirm, onCancel
}: {
    title: string;
    message: string;
    confirmLabel?: string;
    onConfirm: () => void;
    onCancel: () => void;
}) {
    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
            <div className="relative z-10 bg-card border border-border rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
                <div className="flex items-start gap-3 mb-4">
                    <div className="p-2 bg-destructive/10 rounded-xl shrink-0">
                        <AlertTriangle className="w-5 h-5 text-destructive" />
                    </div>
                    <div>
                        <h4 className="font-bold text-foreground text-base">{title}</h4>
                        <p className="text-sm text-muted-foreground mt-1">{message}</p>
                    </div>
                </div>
                <div className="flex gap-3 mt-5">
                    <button
                        onClick={onCancel}
                        className="flex-1 px-4 py-2 rounded-xl border border-border bg-background text-sm font-semibold text-foreground hover:bg-muted transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        className="flex-1 px-4 py-2 rounded-xl bg-destructive hover:bg-destructive/90 text-white text-sm font-bold transition-colors"
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}

export function LivePositions({ urlSymbol }: { urlSymbol: string }) {
    const [tab, setTab] = useState<"positions" | "orders">("positions");
    const [isExecuting, setIsExecuting] = useState(false);
    const [showTodayOnly, setShowTodayOnly] = useState(true);
    const [squareOffConfirm, setSquareOffConfirm] = useState(false);
    const [exitConfirm, setExitConfirm] = useState<any>(null);

    const trades = useLiveMarketStore(state => state.trades);
    const tickerData = useLiveMarketStore(state => state.tickerData);
    const pnl = useLiveMarketStore(state => state.pnl);

    const openTrades = trades.filter(t => t.status === "Entered");
    const todayIST = getTodayIST();

    const orderHistory = showTodayOnly
        ? trades.filter(t => t.time && String(t.time).substring(0, 10) === todayIST)
        : trades;

    const doSquareOffAll = async () => {
        setSquareOffConfirm(false);
        if (isExecuting) return;
        setIsExecuting(true);
        try {
            toast.loading("Squaring off all positions...", { id: "square-off" });
            const res = await fetch("/api/panic-exit", { method: "POST" });
            if (res.ok) {
                toast.success("All positions squared off successfully", { id: "square-off" });
            } else {
                toast.error("Failed to square off positions", { id: "square-off" });
            }
        } catch (e: any) {
            toast.error(e.message || "Error", { id: "square-off" });
        } finally {
            setIsExecuting(false);
        }
    };

    const doExit = async (trade: any) => {
        setExitConfirm(null);
        if (isExecuting) return;
        setIsExecuting(true);
        try {
            toast.loading(`Exiting ${trade.symbol}...`, { id: "exit" });

            const payload = {
                symbol: trade.symbol,
                action: trade.side === "BUY" ? "SELL" : "BUY",
                quantity: trade.quantity,
                order_type: "MARKET",
                product_type: "INTRADAY"
            };

            const res = await fetch("/api/order/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok) {
                toast.success(`Exited: ${data.order_id || 'Success'}`, { id: "exit" });
            } else {
                toast.error(data.error || "Execution failed", { id: "exit" });
            }
        } catch (e: any) {
            toast.error(e.message || "Error", { id: "exit" });
        } finally {
            setIsExecuting(false);
        }
    };

    // Compute real MTM for a trade using live ticker data
    const computeMTM = (trade: any): number | null => {
        const sym = trade.symbol;
        // Try exact match first, then partial match
        const ticker = tickerData[sym] || Object.entries(tickerData).find(([k]) => sym.includes(k) || k.includes(sym))?.[1];
        if (ticker && ticker.lp && trade.price) {
            const ltp = ticker.lp;
            const qty = trade.quantity || 0;
            const side = trade.side === 'BUY' ? 1 : -1;
            return (ltp - trade.price) * qty * side;
        }
        // Fallback to global pnl when only 1 position open
        if (openTrades.length === 1) return pnl;
        return null;
    };

    return (
        <>
            {/* Square Off All Confirmation */}
            {squareOffConfirm && (
                <ConfirmModal
                    title="Square Off All Positions"
                    message="This will close ALL open positions at market price immediately. This action cannot be undone."
                    confirmLabel="Yes, Square Off All"
                    onConfirm={doSquareOffAll}
                    onCancel={() => setSquareOffConfirm(false)}
                />
            )}

            {/* Individual Exit Confirmation */}
            {exitConfirm && (
                <ConfirmModal
                    title={`Exit ${exitConfirm.symbol}`}
                    message={`This will place a ${exitConfirm.side === 'BUY' ? 'SELL' : 'BUY'} market order for ${exitConfirm.quantity} qty of ${exitConfirm.symbol}.`}
                    confirmLabel="Yes, Exit Position"
                    onConfirm={() => doExit(exitConfirm)}
                    onCancel={() => setExitConfirm(null)}
                />
            )}

            <div className="w-full glass-card rounded-2xl border border-border/20 overflow-hidden flex flex-col shadow-sm mt-6">
                {/* Header Tabs */}
                <div className="flex items-center justify-between border-b border-border/40 px-4 bg-muted/20">
                    <div className="flex gap-6">
                        <button
                            onClick={() => setTab("positions")}
                            className={`py-3 text-sm font-bold border-b-2 transition-all ${tab === "positions" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Live Positions ({openTrades.length})
                        </button>
                        <button
                            onClick={() => setTab("orders")}
                            className={`py-3 text-sm font-bold border-b-2 transition-all ${tab === "orders" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Order History ({orderHistory.length})
                        </button>
                    </div>

                    <div className="flex items-center gap-3">
                        {tab === "orders" && (
                            <button
                                onClick={() => setShowTodayOnly(!showTodayOnly)}
                                className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${showTodayOnly ? 'bg-primary/10 border-primary/30 text-primary' : 'border-border/50 text-muted-foreground hover:text-foreground'}`}
                            >
                                {showTodayOnly ? "Today Only" : "All History"}
                            </button>
                        )}
                        {tab === "positions" && openTrades.length > 0 && (
                            <button
                                onClick={() => setSquareOffConfirm(true)}
                                disabled={isExecuting}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/20 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-50"
                            >
                                <XCircle className="w-3.5 h-3.5" />
                                Square Off All
                            </button>
                        )}
                    </div>
                </div>

                {/* Content area */}
                <div className="flex-1 overflow-y-auto max-h-[350px] bg-background/30">
                    {tab === "positions" ? (
                        <table className="w-full text-left text-sm whitespace-nowrap">
                            <thead className="bg-muted/50 text-xs font-semibold uppercase tracking-wider text-muted-foreground sticky top-0 z-10 shadow-sm border-b border-border/40">
                                <tr>
                                    <th className="px-4 py-3">Symbol</th>
                                    <th className="px-4 py-3">Side</th>
                                    <th className="px-4 py-3 text-right">Qty</th>
                                    <th className="px-4 py-3 text-right">Entry Price</th>
                                    <th className="px-4 py-3 text-right">Live MTM</th>
                                    <th className="px-4 py-3 text-center">Action</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                                {openTrades.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-16 text-center text-muted-foreground">
                                            <div className="flex flex-col items-center justify-center">
                                                <div className="w-12 h-12 rounded-full bg-muted/50 flex items-center justify-center mb-3">
                                                    <CheckCircle2 className="w-6 h-6 opacity-50" />
                                                </div>
                                                <p className="font-semibold text-foreground">No Open Positions</p>
                                                <p className="text-xs mt-1">Your net open positions are zero.</p>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    openTrades.map((trade, i) => {
                                        const mtm = computeMTM(trade);
                                        return (
                                            <tr key={i} className="hover:bg-muted/30 transition-colors">
                                                <td className="px-4 py-3 font-semibold text-foreground">{trade.symbol}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${trade.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`}>
                                                        {trade.side}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono">{trade.quantity || '-'}</td>
                                                <td className="px-4 py-3 text-right font-mono">₹{trade.price.toFixed(2)}</td>
                                                <td className={`px-4 py-3 text-right font-mono font-bold ${mtm === null ? 'text-muted-foreground' : mtm > 0 ? 'text-success' : mtm < 0 ? 'text-destructive' : 'text-foreground'}`}>
                                                    {mtm === null ? '—' : `${mtm > 0 ? '+' : ''}₹${mtm.toFixed(2)}`}
                                                </td>
                                                <td className="px-4 py-3 flex items-center justify-center">
                                                    <button
                                                        onClick={() => setExitConfirm(trade)}
                                                        disabled={isExecuting}
                                                        className="px-3 py-1 bg-background hover:bg-rose-500/10 border border-border hover:border-rose-500/30 hover:text-rose-500 rounded text-[10px] font-bold text-muted-foreground transition-all disabled:opacity-50"
                                                    >
                                                        EXIT
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    ) : (
                        <table className="w-full text-left text-sm whitespace-nowrap">
                            <thead className="bg-muted/50 text-xs font-semibold uppercase tracking-wider text-muted-foreground sticky top-0 z-10 shadow-sm border-b border-border/40">
                                <tr>
                                    <th className="px-4 py-3">Time</th>
                                    <th className="px-4 py-3">Symbol</th>
                                    <th className="px-4 py-3">Side</th>
                                    <th className="px-4 py-3 text-right">Qty</th>
                                    <th className="px-4 py-3 text-right">Exec. Price</th>
                                    <th className="px-4 py-3 text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                                {orderHistory.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-16 text-center text-muted-foreground">
                                            <div className="flex flex-col items-center justify-center">
                                                <Clock className="w-8 h-8 opacity-30 mb-3" />
                                                <p className="font-semibold text-foreground">No Order History</p>
                                                {showTodayOnly && <p className="text-xs mt-1 opacity-70">Switch to "All History" to see older orders</p>}
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    [...orderHistory].reverse().map((trade, i) => (
                                        <tr key={i} className="hover:bg-muted/30 transition-colors">
                                            <td className="px-4 py-3 text-xs text-muted-foreground">
                                                {new Date(trade.time).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                            </td>
                                            <td className="px-4 py-3 font-semibold text-foreground">{trade.symbol}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${trade.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`}>
                                                    {trade.side}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-right font-mono">{trade.quantity || '-'}</td>
                                            <td className="px-4 py-3 text-right font-mono">₹{trade.price.toFixed(2)}</td>
                                            <td className="px-4 py-3 flex items-center justify-center">
                                                <span className="px-2 py-0.5 bg-background border border-border rounded text-[10px] font-bold text-muted-foreground">
                                                    {trade.status || 'EXECUTED'}
                                                </span>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </>
    );
}
