"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { 
  BookOpen, 
  Search, 
  Filter, 
  Download, 
  Smile, 
  Meh, 
  Frown, 
  Brain, 
  Clock, 
  Tag, 
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  ImageIcon,
  Plus
} from "lucide-react";

const journalEntries = [
  {
    date: "May 09, 11:30",
    symbol: "RELIANCE",
    type: "BUY",
    pnl: "₹12,450",
    status: "success",
    emotion: "Calm",
    mistake: "None",
    notes: "Followed the plan perfectly. Waited for the 5m candle to close above the EMA 24 before entering. The AI confidence was high (87%) which gave me conviction to hold through a minor pullback.",
    reason: "EMA crossover + RSI breakout."
  },
  {
    date: "May 09, 12:00",
    symbol: "NIFTY",
    type: "ADJ", // Manual Adjustment
    pnl: "-₹500",
    status: "loss",
    emotion: "Neutral",
    mistake: "Manual Override",
    notes: "Manually closed position due to unexpected volatility before a news event. The AI was still holding but I decided to reduce risk. Better safe than sorry.",
    reason: "Manual risk reduction."
  },
  {
    date: "May 09, 10:15",
    symbol: "TCS",
    type: "SELL",
    pnl: "₹8,100",
    status: "success",
    emotion: "Anxious",
    mistake: "None",
    notes: "Entered on a resistance rejection. The move was fast. I was anxious about a sudden reversal but stuck to the ATR trailing stop loss. Booked full profit at target.",
    reason: "Resistance rejection at ₹4,150."
  },
  {
    date: "May 08, 14:30",
    symbol: "INFY",
    type: "BUY",
    pnl: "-₹2,500",
    status: "loss",
    emotion: "Frustrated",
    mistake: "Chased Trend",
    notes: "I entered too late after the move had already happened. I feared missing out (FOMO). The AI confidence was low (45%) and I ignored it. Need to stick to the rules.",
    reason: "Late entry on breakout."
  }
];

export default function Journal() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header with Actions */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground">AI Trading Journal</h1>
              <p className="text-sm text-muted-foreground">Document your trades, emotions, and AI insights in a structured view.</p>
            </div>
            
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search logs..."
                  className="bg-muted/30 border border-border/50 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                />
              </div>
              <button className="flex items-center gap-2 px-4 py-2 bg-muted/50 hover:bg-muted/70 border border-border/50 rounded-lg text-sm font-medium transition-colors">
                <Filter className="w-4 h-4" />
                Filter
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors">
                <Plus className="w-4 h-4" />
                Add Manual Entry
              </button>
            </div>
          </div>

          {/* Quick Stats/Widgets */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="glass-card rounded-xl p-4 flex items-center gap-4 border border-border/20">
              <div className="w-10 h-10 rounded-lg bg-success/10 text-success flex items-center justify-center">
                <Smile className="w-6 h-6" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Dominant Emotion</p>
                <p className="text-lg font-bold text-foreground">Calm (70%)</p>
              </div>
            </div>
            <div className="glass-card rounded-xl p-4 flex items-center gap-4 border border-border/20">
              <div className="w-10 h-10 rounded-lg bg-destructive/10 text-destructive flex items-center justify-center">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Top Mistake</p>
                <p className="text-lg font-bold text-foreground">Chased Trend (1)</p>
              </div>
            </div>
            <div className="glass-card rounded-xl p-4 flex items-center gap-4 border border-border/20">
              <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <Brain className="w-6 h-6" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">AI Alignment</p>
                <p className="text-lg font-bold text-foreground">85% Compliance</p>
              </div>
            </div>
          </div>

          {/* New Active Filter Bar (Added during deep audit) */}
          <div className="glass-card rounded-xl p-4 border border-border/20 flex flex-col md:flex-row gap-4 items-center">
            <div className="flex-1 flex gap-4 w-full md:w-auto">
              <div className="flex-1 min-w-[150px]">
                <label className="text-xs font-medium text-muted-foreground block mb-1">Date</label>
                <input type="date" className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary dark:[color-scheme:dark]" />
              </div>
              <div className="flex-1 min-w-[150px]">
                <label className="text-xs font-medium text-muted-foreground block mb-1">Emotion</label>
                <select className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All Emotions</option>
                  <option value="calm">Calm</option>
                  <option value="anxious">Anxious</option>
                  <option value="neutral">Neutral</option>
                  <option value="frustrated">Frustrated</option>
                </select>
              </div>
            </div>
            <div className="flex-1 flex gap-4 w-full md:w-auto">
              <div className="flex-1 min-w-[150px]">
                <label className="text-xs font-medium text-muted-foreground block mb-1">Symbol</label>
                <select className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All Symbols</option>
                  <option value="reliance">RELIANCE</option>
                  <option value="nifty">NIFTY</option>
                  <option value="tcs">TCS</option>
                  <option value="infy">INFY</option>
                </select>
              </div>
              <div className="flex items-end">
                <button className="px-4 py-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors w-full md:w-auto flex items-center justify-center gap-2">
                  <Filter className="w-4 h-4" />
                  Apply Filters
                </button>
              </div>
            </div>
          </div>

          {/* Tabular Journal */}
          <div className="glass-card rounded-xl p-6 border border-border/20">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-bold text-lg text-foreground">Daily Trade Logs</h3>
                <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-bold">Live</span>
              </div>
              <button className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                <Download className="w-3.5 h-3.5" />
                Export Table
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left text-muted-foreground">
                <thead className="text-xs text-foreground uppercase bg-muted/30">
                  <tr>
                    <th className="px-4 py-3 rounded-l-lg text-left">Date/Time</th>
                    <th className="px-4 py-3 text-left">Symbol</th>
                    <th className="px-4 py-3 text-left">Type</th>
                    <th className="px-4 py-3 text-left">PnL</th>
                    <th className="px-4 py-3 text-left">Emotion</th>
                    <th className="px-4 py-3 text-left">Mistake</th>
                    <th className="px-4 py-3 text-left">AI Reason</th>
                    <th className="px-4 py-3 rounded-r-lg text-left">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {journalEntries.map((entry, index) => (
                    <tr key={index} className="border-b border-border/20 hover:bg-muted/10 transition-colors">
                      <td className="px-4 py-4 text-foreground font-medium text-left">{entry.date}</td>
                      <td className="px-4 py-4 text-foreground font-bold text-left">{entry.symbol}</td>
                      <td className="px-4 py-4 text-left">
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                          entry.type === "BUY" ? "bg-success/10 text-success" : 
                          entry.type === "SELL" ? "bg-destructive/10 text-destructive" : 
                          "bg-primary/10 text-primary" // For ADJ (Adjustment)
                        }`}>
                          {entry.type}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left">
                        <span className={`font-bold flex items-center gap-0.5 ${
                          entry.status === "success" ? "text-success" : 
                          entry.status === "loss" ? "text-destructive" : "text-muted-foreground"
                        }`}>
                          {entry.status === "success" ? <ArrowUpRight className="w-3.5 h-3.5" /> : 
                           entry.status === "loss" ? <ArrowDownRight className="w-3.5 h-3.5" /> : null}
                          <span className="inline-block">{entry.pnl}</span>
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left">
                        <span className="flex items-center gap-1.5 text-xs font-medium">
                          {entry.emotion === "Calm" ? <Smile className="w-4 h-4 text-success" /> : 
                           entry.emotion === "Anxious" ? <Meh className="w-4 h-4 text-warning" /> : 
                           entry.emotion === "Neutral" ? <Meh className="w-4 h-4 text-primary" /> :
                           <Frown className="w-4 h-4 text-destructive" />}
                          {entry.emotion}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                          entry.mistake === "None" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
                        }`}>
                          {entry.mistake}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left">
                        <span className="flex items-center gap-1 text-xs">
                          {entry.type === "ADJ" ? (
                            <AlertTriangle className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                          ) : (
                            <Brain className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                          )}
                          {entry.reason}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left">
                        <p className="text-xs text-muted-foreground line-clamp-2 max-w-xs hover:line-clamp-none cursor-pointer">
                          {entry.notes}
                        </p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
