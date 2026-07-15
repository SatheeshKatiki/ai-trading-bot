"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { BookOpen, AlertTriangle, CheckCircle, Brain, TrendingUp, TrendingDown, Target, Clock, Filter } from "lucide-react";

export default function JournalPage() {
  const [loading, setLoading] = useState(true);
  const [trades, setTrades] = useState<any[]>([]);
  const [stats, setStats] = useState({ total: 0, winRate: 0, netPnl: 0, bestTrade: 0, worstTrade: 0 });

  useEffect(() => {
    fetchJournal();
  }, []);

  const fetchJournal = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/journal");
      const data = await res.json();
      if (data.trades) {
        setTrades(data.trades);
        
        // Calculate basic stats
        const wins = data.trades.filter((t: any) => t.pnl > 0).length;
        const net = data.trades.reduce((sum: number, t: any) => sum + t.pnl, 0);
        const best = Math.max(...data.trades.map((t: any) => t.pnl), 0);
        const worst = Math.min(...data.trades.map((t: any) => t.pnl), 0);
        
        setStats({
          total: data.trades.length,
          winRate: data.trades.length > 0 ? Math.round((wins / data.trades.length) * 100) : 0,
          netPnl: net,
          bestTrade: best,
          worstTrade: worst
        });
      }
    } catch (error) {
      console.error("Error fetching journal:", error);
    }
    setLoading(false);
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <div className="flex-1 overflow-y-auto p-4 md:p-8 bg-background relative z-10 w-full">
      <div className="w-full space-y-6">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 text-xs font-bold uppercase tracking-widest mb-4">
              <BookOpen className="w-3.5 h-3.5" /> Post-Trade Analytics
            </div>
            <h1 className="text-4xl font-display font-black tracking-tight text-foreground">
              Trading Journal
            </h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-lg">
              AI-driven analysis of your historical trades to identify mistakes and improve edge.
            </p>
          </div>
          <button className="flex items-center gap-2 bg-card border border-border/50 hover:bg-muted/50 transition-colors px-4 py-2 rounded-xl text-sm font-semibold text-foreground">
            <Filter className="w-4 h-4" /> Filter Logs
          </button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="glass-card rounded-2xl p-5 border border-border/50">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Total Trades</span>
            <div className="text-3xl font-bold font-mono mt-2 text-foreground">{stats.total}</div>
          </div>
          <div className="glass-card rounded-2xl p-5 border border-border/50">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Win Rate</span>
            <div className={`text-3xl font-bold font-mono mt-2 ${stats.winRate > 50 ? 'text-success' : 'text-warning'}`}>
              {stats.winRate}%
            </div>
          </div>
          <div className="glass-card rounded-2xl p-5 border border-border/50">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Net PnL</span>
            <div className={`text-3xl font-bold font-mono mt-2 ${stats.netPnl >= 0 ? 'text-success' : 'text-destructive'}`}>
              {stats.netPnl >= 0 ? '+' : ''}₹{stats.netPnl.toLocaleString('en-IN')}
            </div>
          </div>
          <div className="glass-card rounded-2xl p-5 border border-border/50">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-success" /> Best Trade
            </span>
            <div className="text-3xl font-bold font-mono mt-2 text-success">
              +₹{stats.bestTrade.toLocaleString('en-IN')}
            </div>
          </div>
          <div className="glass-card rounded-2xl p-5 border border-border/50">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-destructive" /> Worst Trade
            </span>
            <div className="text-3xl font-bold font-mono mt-2 text-destructive">
              ₹{stats.worstTrade.toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Journal Entries */}
        <div className="space-y-4 mt-8">
          <h2 className="text-xl font-bold flex items-center gap-2 mb-4">
            <Clock className="w-5 h-5 text-primary" /> Execution Timeline
          </h2>
          
          {loading ? (
            <div className="h-32 flex items-center justify-center glass-card rounded-2xl">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : trades.length === 0 ? (
            <div className="glass-card rounded-2xl p-8 text-center border border-border/50">
              <BookOpen className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-bold text-foreground">No Trades Logged Yet</h3>
              <p className="text-muted-foreground mt-1">Run the live bot or manually log trades to see the autopsy here.</p>
            </div>
          ) : (
            <div className="glass-card rounded-2xl overflow-hidden border border-border/50">
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-muted/30 border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="py-3 px-4 font-medium">Date & Time</th>
                      <th className="py-3 px-4 font-medium">Symbol / Strategy</th>
                      <th className="py-3 px-4 font-medium text-center">Type</th>
                      <th className="py-3 px-4 font-medium text-right">Qty</th>
                      <th className="py-3 px-4 font-medium text-right">Entry → Exit</th>
                      <th className="py-3 px-4 font-medium text-right">PnL</th>
                      <th className="py-3 px-4 font-medium">AI Feedback</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {trades.map((trade: any) => {
                      const isProfit = trade.pnl > 0;
                      return (
                        <tr key={trade.id} className="border-b border-border hover:bg-muted/10 transition-colors group">
                          <td className="py-3 px-4 font-mono text-[11px] whitespace-nowrap text-muted-foreground">
                            {trade.trade_date}
                          </td>
                          <td className="py-3 px-4">
                            <div className="font-bold text-foreground text-sm">{trade.symbol}</div>
                            <div className="text-[10px] text-muted-foreground font-mono uppercase mt-0.5">{trade.strategy_name}</div>
                          </td>
                          <td className="py-3 px-4 text-center">
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${trade.direction === 'BUY' ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'}`}>
                              {trade.direction}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-xs">
                            {trade.qty}
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-[11px] text-muted-foreground">
                            <span className="text-foreground">₹{trade.entry_price}</span> <span className="text-border mx-1">→</span> <span className="text-foreground">₹{trade.exit_price}</span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className={`font-bold font-mono text-sm ${isProfit ? 'text-success' : 'text-destructive'}`}>
                              {isProfit ? '+' : ''}₹{trade.pnl.toLocaleString('en-IN')}
                            </div>
                          </td>
                          <td className="py-3 px-4 min-w-[300px]">
                            <div className="flex items-start gap-2">
                              <Brain className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5 opacity-70 group-hover:opacity-100 transition-opacity" />
                              <div className="text-xs text-muted-foreground line-clamp-2 group-hover:line-clamp-none transition-all">
                                {trade.ai_feedback || "-"}
                                {trade.tags && (
                                  <div className="flex flex-wrap gap-1 mt-1.5">
                                    {trade.tags.split(',').map((tag: string, idx: number) => (
                                      <span key={idx} className="text-[9px] font-mono px-1.5 py-0.5 bg-background border border-border/50 rounded text-muted-foreground uppercase tracking-wider">
                                        #{tag.trim()}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        
        </div>
      </div>
    </div>
    </div>
  );
}
