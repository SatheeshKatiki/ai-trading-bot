"use client";
import { useState } from "react";
import { useLiveMarketStore, type PositionDetail } from "@/store/useLiveMarketStore";
import { XCircle, Clock, CheckCircle2, AlertTriangle, X, Zap } from "lucide-react";
import { toast } from "sonner";
import { extractApiError } from "@/lib/api-error";
import { ExecutionFeed } from "./execution-feed";
import { parseBackendDatetimeToEpochSeconds, getISTDateStringFromEpoch, getTodayISTDateString } from "@/lib/ist-time";

// Root-cause fix (chart timestamp audit): state.db's trade records are NOT
// consistently tagged (some IST, some UTC isoformat -- see the manual
// dashboard order-execution endpoint) -- a naive substring of the raw
// string's first 10 characters silently trusted whatever calendar date the
// ORIGINAL timezone happened to produce, wrong for UTC-tagged trades placed
// in the ~5.5-hour window where the UTC and IST calendar dates differ.
function isTradeFromTodayIST(time: unknown, todayIST: string): boolean {
    if (!time) return false;
    const epoch = parseBackendDatetimeToEpochSeconds(String(time));
    if (epoch === null) return false;
    return getISTDateStringFromEpoch(epoch) === todayIST;
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
    const [tab, setTab] = useState<"positions" | "orders" | "execution">("positions");
    const [isExecuting, setIsExecuting] = useState(false);
    const [showTodayOnly, setShowTodayOnly] = useState(true);
    const [squareOffConfirm, setSquareOffConfirm] = useState(false);
    const [exitConfirm, setExitConfirm] = useState<PositionDetail | null>(null);

    const trades = useLiveMarketStore(state => state.trades);
    // Open positions come from the live positions frame, NOT the trade log.
    // state.db trade records carry no `status` field at all (shared.state's
    // load_state builds {symbol, side, price, time, qty}), so the previous
    // `trades.filter(t => t.status === "Entered")` matched nothing, ever --
    // this table was permanently empty and its EXIT button unreachable while
    // positions were genuinely open. positionsDetail is the live frame the
    // backend already computes, with the traded contract, qty, SL and a
    // server-side mark-to-market.
    const openPositions = useLiveMarketStore(state => state.positionsDetail);
    const todayIST = getTodayISTDateString();

    const orderHistory = showTodayOnly
        ? trades.filter(t => isTradeFromTodayIST(t.time, todayIST))
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
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Error", { id: "square-off" });
        } finally {
            setIsExecuting(false);
        }
    };

    const doExit = async (position: PositionDetail) => {
        setExitConfirm(null);
        if (isExecuting) return;
        setIsExecuting(true);
        try {
            toast.loading(`Exiting ${position.symbol}...`, { id: "exit" });

            // Deliberately NOT /api/order/execute. That places a counter-order
            // at the broker and stops there -- and main.py runs in a separate
            // process, so it would never learn the position is gone: it would
            // keep managing it, try to exit it again (a double sell), and
            // leave its exchange stop-loss working against a position no
            // longer held. /api/positions/exit does both halves: it places the
            // order AND tells the engine to cancel the stop and close its book.
            const res = await fetch("/api/positions/exit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol: position.symbol,
                    quantity: position.qty,
                    side: position.side === 1 ? "BUY" : "SELL",
                })
            });

            const data = await res.json();
            if (res.ok) {
                toast.success(`Exit placed for ${position.symbol}`, { id: "exit" });
            } else {
                toast.error(extractApiError(data, "Exit failed"), { id: "exit" });
            }
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Error", { id: "exit" });
        } finally {
            setIsExecuting(false);
        }
    };

    // computeMTM is gone: positionsDetail already carries a server-side
    // mark-to-market (unrealized_pnl / invested / roi), computed from the same
    // prices the engine trades on. Deriving it again in the browser from
    // ticker data -- with a "fall back to the global P&L if only one position
    // is open" guess -- could disagree with the engine about the same trade.

    const todayTradesCount = trades.filter(t => isTradeFromTodayIST(t.time, todayIST)).length;

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
                    message={`This will place a ${exitConfirm.side === 1 ? 'SELL' : 'BUY'} market order for ${exitConfirm.qty} qty of ${exitConfirm.symbol}, cancel its stop-loss, and close it in the engine.`}
                    confirmLabel="Yes, Exit Position"
                    onConfirm={() => doExit(exitConfirm)}
                    onCancel={() => setExitConfirm(null)}
                />
            )}

            <div className="flex flex-col h-full bg-card/60 border border-border/40 rounded-xl overflow-hidden shadow-sm mt-6">
                {/* Header Tabs */}
                <div className="flex items-center justify-between px-6 border-b border-border/40 bg-muted/20 shrink-0">
                    <div className="flex items-center gap-6">
                        <button
                            onClick={() => setTab("positions")}
                            className={`py-3 text-sm font-bold border-b-2 transition-all ${tab === "positions" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Live Positions ({openPositions.length})
                        </button>
                        <button
                            onClick={() => setTab("orders")}
                            className={`py-3 text-sm font-bold border-b-2 transition-all ${tab === "orders" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Order History ({showTodayOnly ? orderHistory.length : trades.filter(t => t.time).length})
                        </button>
                        <button
                            onClick={() => setTab("execution")}
                            className={`py-3 text-sm font-bold border-b-2 transition-all flex items-center gap-1.5 ${tab === "execution" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            <Zap className="w-4 h-4 text-warning" />
                            Live Execution Feed ({showTodayOnly ? todayTradesCount : trades.length})
                        </button>
                    </div>

                    <div className="flex items-center gap-3">
                        {(tab === "orders" || tab === "execution") && (
                            <button
                                onClick={() => setShowTodayOnly(!showTodayOnly)}
                                className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${showTodayOnly ? 'bg-primary/10 border-primary/30 text-primary' : 'border-border/50 text-muted-foreground hover:text-foreground'}`}
                            >
                                {showTodayOnly ? "Today Only" : "All History"}
                            </button>
                        )}
                        {tab === "positions" && openPositions.length > 0 && (
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
                    {tab === "execution" ? (
                        <div className="p-4 h-[320px]">
                            <ExecutionFeed showTodayOnly={showTodayOnly} />
                        </div>
                    ) : tab === "positions" ? (
                        <table className="w-full text-left text-sm whitespace-nowrap">
                            <thead className="bg-muted/50 text-xs font-semibold uppercase tracking-wider text-muted-foreground sticky top-0 z-10 shadow-sm border-b border-border/40">
                                <tr>
                                    <th className="px-4 py-3">Symbol</th>
                                    <th className="px-4 py-3">Side</th>
                                    <th className="px-4 py-3 text-right">Qty</th>
                                    <th className="px-4 py-3 text-right">Entry Price</th>
                                    <th className="px-4 py-3 text-right">Invested Margin</th>
                                    <th className="px-4 py-3 text-right">Live MTM & ROI</th>
                                    <th className="px-4 py-3 text-center">Action</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                                {openPositions.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-16 text-center text-muted-foreground">
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
                                    openPositions.map((position) => {
                                        // Marked to market by the backend on every frame.
                                        const mtm = position.unrealized_pnl ?? null;
                                        const qty = position.qty || 1;
                                        const invested = position.invested ?? position.entry_price * qty;
                                        const roi = position.roi ?? ((mtm !== null && invested > 0) ? (mtm / invested) * 100 : null);
                                        const isProfit = mtm !== null && mtm > 0.009;
                                        const isLoss = mtm !== null && mtm < -0.009;

                                        return (
                                            <tr key={position.symbol} className={`transition-colors ${isProfit ? 'hover:bg-success/[0.04] bg-success/[0.01]' : isLoss ? 'hover:bg-destructive/[0.04] bg-destructive/[0.01]' : 'hover:bg-muted/30'}`}>
                                                <td className="px-4 py-3 font-semibold text-foreground flex items-center gap-2">
                                                    <span className={`w-2 h-2 rounded-full ${isProfit ? 'bg-success animate-pulse' : isLoss ? 'bg-destructive animate-pulse' : 'bg-muted-foreground'}`}></span>
                                                    {position.symbol}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${position.side === 1 ? 'bg-emerald-500/15 text-emerald-500 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-500 border border-rose-500/30'}`}>
                                                        {position.side === 1 ? 'BUY' : 'SELL'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono">{position.qty || '-'}</td>
                                                <td className="px-4 py-3 text-right font-mono">₹{position.entry_price.toFixed(2)}</td>
                                                <td className="px-4 py-3 text-right font-mono text-muted-foreground">₹{invested.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                                                <td className="px-4 py-3 text-right font-mono">
                                                    <div className="flex items-center justify-end gap-1.5">
                                                        <span className={`font-bold ${isProfit ? 'text-success drop-shadow-[0_0_6px_rgba(34,197,94,0.3)]' : isLoss ? 'text-destructive drop-shadow-[0_0_6px_rgba(239,68,68,0.3)]' : 'text-foreground'}`}>
                                                            {mtm === null ? '—' : `${mtm >= 0 ? '+' : ''}₹${mtm.toFixed(2)}`}
                                                        </span>
                                                        {roi !== null && (
                                                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border transition-colors ${
                                                                isProfit 
                                                                    ? 'bg-success/15 border-success/30 text-success' 
                                                                    : isLoss 
                                                                        ? 'bg-destructive/15 border-destructive/30 text-destructive' 
                                                                        : 'bg-muted border-border text-muted-foreground'
                                                            }`}>
                                                                {roi >= 0 ? '+' : ''}{roi.toFixed(1)}%
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 flex items-center justify-center">
                                                    <button
                                                        onClick={() => setExitConfirm(position)}
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
