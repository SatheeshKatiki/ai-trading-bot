"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { 
  BookOpen, 
  Brain, 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  Filter, 
  ArrowUpRight, 
  ArrowDownRight, 
  Sparkles,
  Calendar,
  Layers,
  ArrowRight,
  ShieldCheck,
  Tag
} from "lucide-react";

interface JournalEntry {
  id: number;
  trade_date: string;
  symbol: string;
  strategy_name: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  ai_feedback: string | null;
  tags: string | null;
}

function parseSymbol(symbol: string) {
  // Formats 'NSE:NIFTY26AUG24050CE' into clean 'NIFTY 24050 CE'
  const clean = symbol.replace(/^NSE:/, "");
  const match = clean.match(/^(NIFTY|BANKNIFTY|FINNIFTY|SENSEX).*?(\d{5})(CE|PE)$/);
  if (match) {
    return {
      index: match[1],
      strike: match[2],
      type: match[3] as "CE" | "PE",
      displayName: `${match[1]} ${match[2]} ${match[3]}`
    };
  }
  return {
    index: clean.includes("NIFTY") ? "NIFTY" : "INDEX",
    strike: clean,
    type: clean.endsWith("PE") ? ("PE" as const) : ("CE" as const),
    displayName: clean
  };
}

function formatTradeDate(dateStr: string) {
  try {
    const d = new Date(dateStr.replace(" ", "T"));
    if (isNaN(d.getTime())) {
      return { date: dateStr.split(" ")[0] || dateStr, time: dateStr.split(" ")[1] || "" };
    }
    const dateFormatted = d.toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
    const timeFormatted = d.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true
    });
    return { date: dateFormatted, time: timeFormatted };
  } catch {
    return { date: dateStr, time: "" };
  }
}

export default function JournalPage() {
  const [loading, setLoading] = useState(true);
  const [trades, setTrades] = useState<JournalEntry[]>([]);
  const [filterType, setFilterType] = useState<"ALL" | "WINS" | "LOSSES">("ALL");
  const [stats, setStats] = useState({ total: 0, winRate: 0, netPnl: 0, bestTrade: 0, worstTrade: 0 });

  useEffect(() => {
    let cancelled = false;

    const fetchJournal = async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/journal");
        const data: { trades?: JournalEntry[]; error?: string } = await res.json();
        if (cancelled) return;
        if (data.trades) {
          setTrades(data.trades);

          // Calculate basic stats
          const wins = data.trades.filter((t: JournalEntry) => t.pnl > 0).length;
          const net = data.trades.reduce((sum: number, t: JournalEntry) => sum + t.pnl, 0);
          const best = Math.max(...data.trades.map((t: JournalEntry) => t.pnl), 0);
          const worst = Math.min(...data.trades.map((t: JournalEntry) => t.pnl), 0);

          setStats({
            total: data.trades.length,
            winRate: data.trades.length > 0 ? Math.round((wins / data.trades.length) * 100) : 0,
            netPnl: net,
            bestTrade: best,
            worstTrade: worst
          });
        }
      } catch (error) {
        if (!cancelled) console.error("Error fetching journal:", error);
      }
      if (!cancelled) setLoading(false);
    };

    fetchJournal();
    return () => { cancelled = true; };
  }, []);

  const filteredTrades = trades.filter((t) => {
    if (filterType === "WINS") return t.pnl > 0;
    if (filterType === "LOSSES") return t.pnl <= 0;
    return true;
  });

  return (
    <div data-testid="journal-page" className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 bg-background relative z-10 w-full">
          <div className="w-full space-y-6">
            
            {/* Header Banner */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2 border-b border-border/40 w-full">
              <div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-xs font-bold uppercase tracking-wider mb-2">
                  <Sparkles className="w-3.5 h-3.5" /> Institutional Trade Journal
                </div>
                <h1 className="text-3xl md:text-4xl font-display font-black tracking-tight text-foreground">
                  Trading Journal & Execution Analytics
                </h1>
                <p className="text-muted-foreground mt-1 max-w-2xl text-sm md:text-base">
                  AI-driven post-trade analysis, entry/exit audit trail, and edge verification.
                </p>
              </div>

              {/* Filter Pills */}
              <div className="flex items-center gap-2 bg-card border border-border/60 p-1 rounded-xl shadow-sm">
                <button
                  onClick={() => setFilterType("ALL")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    filterType === "ALL" 
                      ? "bg-primary text-primary-foreground shadow-sm" 
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  }`}
                >
                  All ({trades.length})
                </button>
                <button
                  onClick={() => setFilterType("WINS")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    filterType === "WINS" 
                      ? "bg-emerald-500 text-white shadow-sm" 
                      : "text-muted-foreground hover:text-emerald-500 hover:bg-emerald-500/10"
                  }`}
                >
                  Wins ({trades.filter(t => t.pnl > 0).length})
                </button>
                <button
                  onClick={() => setFilterType("LOSSES")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    filterType === "LOSSES" 
                      ? "bg-rose-500 text-white shadow-sm" 
                      : "text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10"
                  }`}
                >
                  Losses ({trades.filter(t => t.pnl <= 0).length})
                </button>
              </div>
            </div>

            {/* Performance Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
              <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm hover:border-primary/40 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Total Trades</span>
                  <BookOpen className="w-4 h-4 text-muted-foreground/60" />
                </div>
                <div className="text-2xl md:text-3xl font-black font-mono mt-2 text-foreground">{stats.total}</div>
                <span className="text-[10px] text-muted-foreground mt-0.5 block">Logged sessions</span>
              </div>

              <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm hover:border-primary/40 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Win Rate</span>
                  <ShieldCheck className="w-4 h-4 text-muted-foreground/60" />
                </div>
                <div className={`text-2xl md:text-3xl font-black font-mono mt-2 ${stats.winRate >= 50 ? 'text-emerald-500' : 'text-amber-500'}`}>
                  {stats.winRate}%
                </div>
                <span className="text-[10px] text-muted-foreground mt-0.5 block">Execution accuracy</span>
              </div>

              <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm hover:border-primary/40 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Net P&L</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${stats.netPnl >= 0 ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`}>
                    {stats.netPnl >= 0 ? 'PROFIT' : 'DRAWDOWN'}
                  </span>
                </div>
                <div className={`text-2xl md:text-3xl font-black font-mono mt-2 ${stats.netPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                  {stats.netPnl >= 0 ? '+' : ''}₹{stats.netPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span className="text-[10px] text-muted-foreground mt-0.5 block">Realized net return</span>
              </div>

              <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm hover:border-primary/40 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Best Trade</span>
                  <TrendingUp className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-2xl md:text-3xl font-black font-mono mt-2 text-emerald-500">
                  +₹{stats.bestTrade.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span className="text-[10px] text-muted-foreground mt-0.5 block">Peak profit captured</span>
              </div>

              <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm hover:border-primary/40 transition-colors col-span-2 md:col-span-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Worst Trade</span>
                  <TrendingDown className="w-4 h-4 text-rose-500" />
                </div>
                <div className="text-2xl md:text-3xl font-black font-mono mt-2 text-rose-500">
                  ₹{stats.worstTrade.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span className="text-[10px] text-muted-foreground mt-0.5 block">Controlled stoploss cut</span>
              </div>
            </div>

            {/* Execution Table Card */}
            <div className="bg-card/80 border border-border/60 rounded-2xl shadow-md overflow-hidden">
              <div className="px-6 py-4 border-b border-border/60 bg-muted/20 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-primary" />
                  <h2 className="text-base font-bold text-foreground">Execution Timeline & Trade Audit</h2>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  Showing {filteredTrades.length} of {trades.length} records
                </span>
              </div>
              
              {loading ? (
                <div className="h-48 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-xs text-muted-foreground font-medium">Loading trade records...</span>
                  </div>
                </div>
              ) : filteredTrades.length === 0 ? (
                <div className="p-12 text-center">
                  <BookOpen className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-30" />
                  <h3 className="text-base font-bold text-foreground">No Trades Logged Yet</h3>
                  <p className="text-muted-foreground text-xs mt-1">Live bot session trades and backtest entries will appear here.</p>
                </div>
              ) : (
                <div className="overflow-x-auto w-full">
                  <table data-testid="journal-table" className="w-full text-left border-collapse table-auto">
                    <thead>
                      <tr className="bg-muted/40 border-b border-border/60 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                        <th className="py-3.5 px-6 w-[15%]">Date & Time</th>
                        <th className="py-3.5 px-6 w-[20%]">Instrument / Strike</th>
                        <th className="py-3.5 px-4 text-center w-[10%]">Type / Qty</th>
                        <th className="py-3.5 px-6 text-center w-[22%]">Entry & Exit Prices</th>
                        <th className="py-3.5 px-6 text-right w-[15%]">Net P&L</th>
                        <th className="py-3.5 px-6 w-[18%]">AI Strategy Feedback & Tags</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40 text-sm">
                      {filteredTrades.map((trade) => {
                        const isProfit = trade.pnl > 0;
                        const parsed = parseSymbol(trade.symbol);
                        const { date, time } = formatTradeDate(trade.trade_date);
                        const points = trade.exit_price - trade.entry_price;
                        const returnPct = trade.entry_price > 0 ? ((points / trade.entry_price) * 100) : 0;

                        return (
                          <tr 
                            key={trade.id} 
                            data-testid="journal-row" 
                            data-symbol={trade.symbol} 
                            data-pnl-sign={isProfit ? "positive" : "negative"} 
                            className="hover:bg-muted/20 transition-colors group"
                          >
                            {/* 1. Date & Time */}
                            <td className="py-4.5 px-6 align-top">
                              <div className="flex flex-col">
                                <span className="font-semibold text-foreground text-xs flex items-center gap-1.5">
                                  <Calendar className="w-3.5 h-3.5 text-muted-foreground/70" />
                                  {date}
                                </span>
                                <span className="font-mono text-[11px] text-muted-foreground mt-1 bg-muted/50 px-2 py-0.5 rounded-md w-fit border border-border/40">
                                  {time || trade.trade_date}
                                </span>
                              </div>
                            </td>

                            {/* 2. Instrument / Strike */}
                            <td className="py-4.5 px-6 align-top">
                              <div className="flex flex-col">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-foreground text-sm tracking-tight">
                                    {parsed.displayName}
                                  </span>
                                  <span className={`text-[10px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider font-mono ${
                                    parsed.type === 'CE' 
                                      ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' 
                                      : 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20'
                                  }`}>
                                    {parsed.type}
                                  </span>
                                </div>
                                <span className="text-[11px] text-muted-foreground font-mono mt-1 flex items-center gap-1">
                                  <Layers className="w-3 h-3 text-muted-foreground/60" />
                                  {trade.strategy_name.replace(/_/g, " ").toUpperCase()}
                                </span>
                              </div>
                            </td>

                            {/* 3. Type / Qty */}
                            <td className="py-4.5 px-4 align-top text-center">
                              <div className="flex flex-col items-center gap-1">
                                <span className={`text-[10px] font-black px-2.5 py-1 rounded-md uppercase tracking-wider shadow-sm ${
                                  trade.direction === 'BUY' 
                                    ? 'bg-emerald-500 text-white dark:bg-emerald-600' 
                                    : 'bg-rose-500 text-white dark:bg-rose-600'
                                }`}>
                                  {trade.direction}
                                </span>
                                <span className="text-[11px] font-mono font-semibold text-muted-foreground mt-0.5">
                                  {trade.qty} Qty <span className="text-[9px] text-muted-foreground/60">({Math.round(trade.qty / 65)}L)</span>
                                </span>
                              </div>
                            </td>

                            {/* 4. Entry & Exit Prices Card */}
                            <td className="py-4.5 px-6 align-top">
                              <div className="bg-muted/30 border border-border/50 rounded-xl p-2.5 flex items-center justify-between gap-2 shadow-xs">
                                {/* Entry */}
                                <div className="flex flex-col">
                                  <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Entry</span>
                                  <span className="font-mono font-bold text-xs text-foreground mt-0.5">
                                    ₹{Number(trade.entry_price).toFixed(2)}
                                  </span>
                                </div>

                                <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0" />

                                {/* Exit */}
                                <div className="flex flex-col">
                                  <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Exit</span>
                                  <span className="font-mono font-bold text-xs text-foreground mt-0.5">
                                    ₹{Number(trade.exit_price).toFixed(2)}
                                  </span>
                                </div>

                                {/* Points Badge */}
                                <div className={`text-[10px] font-bold font-mono px-2 py-1 rounded-md border ${
                                  points >= 0 
                                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' 
                                    : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                                }`}>
                                  {points >= 0 ? '+' : ''}{points.toFixed(2)} pts
                                </div>
                              </div>
                            </td>

                            {/* 5. Net P&L */}
                            <td className="py-4.5 px-6 align-top text-right">
                              <div className="flex flex-col items-end">
                                <div className={`text-base font-black font-mono tracking-tight px-2.5 py-1 rounded-lg inline-flex items-center gap-1 ${
                                  isProfit 
                                    ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25' 
                                    : 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/25'
                                }`}>
                                  {isProfit ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                                  {isProfit ? '+' : ''}₹{trade.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </div>
                                <span className={`text-[10px] font-bold font-mono mt-1 ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                                  {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(1)}% ROI
                                </span>
                              </div>
                            </td>

                            {/* 6. AI Strategy Feedback & Tags */}
                            <td className="py-4.5 px-6 align-top">
                              <div className="bg-muted/20 border border-border/40 rounded-xl p-3">
                                <div className="flex items-start gap-2">
                                  <Brain className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                                  <div className="flex-1">
                                    <p className="text-xs text-foreground/90 font-medium leading-relaxed">
                                      {trade.ai_feedback || "Executed based on system crossover & momentum rules."}
                                    </p>
                                    {trade.tags && (
                                      <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-border/30">
                                        {trade.tags.split(',').map((tag: string, idx: number) => (
                                          <span 
                                            key={idx} 
                                            className="inline-flex items-center gap-1 text-[10px] font-mono font-medium px-2 py-0.5 bg-card border border-border/60 rounded-md text-muted-foreground"
                                          >
                                            <Tag className="w-2.5 h-2.5 opacity-60" />
                                            {tag.trim()}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </td>

                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
