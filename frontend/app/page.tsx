"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import { 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  Zap, 
  Shield, 
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Activity
} from "lucide-react";
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from "recharts";

export default function Dashboard() {
  const [equity, setEquity] = useState(100000.0);
  const [pnl, setPnl] = useState(0.0);
  const [trades, setTrades] = useState<any[]>([]);
  const [curve, setCurve] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch live state from the API route we created
  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('/api/state');
        const data = await res.json();
        
        if (data && !data.error) {
          setEquity(data.equity || 100000.0);
          setPnl(data.pnl || 0.0);
          setTrades(data.trades || []);
          
          if (data.chartData && data.chartData.length > 0) {
            const mappedCurve = data.chartData.map((c: any) => ({
              name: new Date(c.time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              value: c.close
            }));
            setCurve(mappedCurve);
          }
        }
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch dashboard state:", error);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 5000); // Auto refresh every 5s
    
    return () => clearInterval(interval);
  }, []);

  // Calculate some derived stats
  const winRate = trades.length > 0 
    ? (trades.filter(t => t.pnl > 0).length / trades.length * 100).toFixed(1)
    : "0.0";

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground">Institutional Dashboard</h1>
              <p className="text-sm text-muted-foreground">Welcome back. Here's your live algorithm performance overview.</p>
            </div>
            
            <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/30 rounded-lg border border-border/50">
              <div className="w-2 h-2 bg-success rounded-full animate-pulse"></div>
              <span className="text-xs font-medium text-foreground">System Live</span>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {/* Stat Card 1 */}
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <span className="text-xs text-muted-foreground font-medium">Account Equity</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold font-mono text-foreground">
                  ₹{equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {/* Stat Card 2 */}
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <span className="text-xs text-muted-foreground font-medium">Today's Net P&L</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className={`text-2xl font-bold font-mono ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                  {pnl >= 0 ? "+" : ""}₹{pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
                <span className={`text-xs font-bold flex items-center gap-0.5 ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                  {pnl >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                  {equity > 0 ? ((pnl / equity) * 100).toFixed(2) : "0.00"}%
                </span>
              </div>
            </div>

            {/* Stat Card 3 */}
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <span className="text-xs text-muted-foreground font-medium">Win Rate</span>
              <div className="text-2xl font-bold font-mono mt-1 text-foreground">{winRate}%</div>
              <p className="text-xs text-muted-foreground mt-1">{trades.filter(t => t.pnl > 0).length} of {trades.length} trades</p>
            </div>

            {/* Stat Card 4 */}
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <span className="text-xs text-muted-foreground font-medium">Execution Count</span>
              <div className="text-2xl font-bold font-mono mt-1 text-foreground">{trades.length}</div>
              <p className="text-xs text-muted-foreground mt-1">Total orders filled</p>
            </div>
          </div>

          {/* Main Content Area */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart Area */}
            <div className="lg:col-span-2 glass-card rounded-xl p-6 border border-border/20">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h3 className="font-display font-bold text-lg text-foreground">Intraday Growth</h3>
                  <p className="text-xs text-muted-foreground">Live account equity projection</p>
                </div>
                <div className="flex gap-2">
                  <span className="px-3 py-1 bg-primary/10 text-primary text-xs font-medium rounded-full">Live</span>
                </div>
              </div>

              <div className="h-[350px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={curve}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ff4d4d" stopOpacity={0.2}/>
                        <stop offset="95%" stopColor="#ff4d4d" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} domain={['dataMin - 1000', 'dataMax + 1000']} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "hsl(var(--background))", borderColor: "hsl(var(--border))", borderRadius: "8px" }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="value" 
                      stroke="#ff4d4d" 
                      strokeWidth={2}
                      fillOpacity={1} 
                      fill="url(#colorValue)" 
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Right Widget Area */}
            <div className="glass-card rounded-xl p-6 border border-border/20 space-y-6">
              <div>
                <h3 className="font-display font-bold text-lg text-foreground mb-4">Live Activity</h3>
                
                <div className="space-y-4">
                  {trades.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No recent trades found in state.</p>
                  ) : (
                    trades.slice(-4).reverse().map((trade, index) => (
                      <div key={index} className="flex items-center justify-between border-b border-border/10 pb-3 last:border-0 last:pb-0">
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                            trade.pnl >= 0 ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
                          }`}>
                            {trade.pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-foreground">{trade.symbol || "Asset"}</p>
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <Clock className="w-3 h-3" /> {trade.time || "Just now"}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className={`text-sm font-bold font-mono ${trade.pnl >= 0 ? "text-success" : "text-destructive"}`}>
                            {trade.pnl >= 0 ? "+" : ""}₹{trade.pnl?.toFixed(2)}
                          </p>
                          <p className="text-xs text-muted-foreground">Qty: {trade.qty || "N/A"}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="pt-2 border-t border-border/20">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-foreground">AI Signal Scanner</span>
                  <Zap className="w-4 h-4 text-warning" />
                </div>
                <div className="p-3 bg-muted/30 rounded-lg border border-border/50">
                  <p className="text-xs text-foreground font-medium">Scanning NIFTY 50...</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Model expects resistance at top range. Bias: Neutral.</p>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
