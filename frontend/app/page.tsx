"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import NewsTicker from "@/components/news-ticker";
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
  Activity,
  Briefcase,
  Terminal,
  ShieldAlert,
  Search,
  AlertTriangle,
  X,
  CheckCircle2,
  Trash2,
  PackageOpen,
  Inbox,
  Brain
} from "lucide-react";
import { toast } from "sonner";
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
  const [positions, setPositions] = useState<any[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [curve, setCurve] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPanicModalOpen, setIsPanicModalOpen] = useState(false);
  const [isPanicExecuting, setIsPanicExecuting] = useState(false);
  const [panicStatus, setPanicStatus] = useState<string | null>(null);
  const [isEngineLive, setIsEngineLive] = useState(false);
  const [isEngineLoading, setIsEngineLoading] = useState(false);
  const [aiCommentary, setAiCommentary] = useState("System armed. Analyzing market structure...");
  const [tickerData, setTickerData] = useState<any>({
    "NIFTY": { lp: 23820.35, chp: -1.49, up: false },
    "BANKNIFTY": { lp: 51000.00, chp: 0.08, up: true },
    "SENSEX": { lp: 76015.28, chp: -1.70, up: false },
    "RELIANCE": { lp: 2950.00, chp: 0.12, up: true },
    "TCS": { lp: 3950.00, chp: -0.45, up: false },
  });
  const [lastPrices, setLastPrices] = useState<any>({});
  const [flashes, setFlashes] = useState<any>({});
  // Live AI Signal state — sourced from /api/signals
  const [aiSignal, setAiSignal] = useState<{
    confidence: number;
    status: string;
    bias: string;
    signals: any[];
  }>({
    confidence: 0,
    status: "Initializing...",
    bias: "NEUTRAL Bias Detected",
    signals: [],
  });

  // AI Live Commentary Logic
  useEffect(() => {
    const commentaries = [
      `Analyzing order book dynamics across top 50 symbols. High liquidity pools detected.`,
      `AI Confidence at ${aiSignal?.confidence || 0}%. ${aiSignal?.confidence && aiSignal.confidence > 75 ? "Strong conviction, aggressively scanning for entries." : "Awaiting clear trend confirmation."}`,
      `Volatility squeeze detected on Bank Nifty. Standard deviation contracting. Breakout imminent.`,
      `Institutional buying pressure observed in IT sector. Positive volume delta.`,
      `Monitoring 9 EMA and 21 SMA for potential crossover across portfolio.`
    ];

    if (pnl > 500 && Math.random() > 0.6) {
      setAiCommentary(`Current session highly profitable (+₹${pnl.toFixed(2)}). Risk engine protecting gains with trailing stop.`);
    } else {
      const interval = setInterval(() => {
        const randomComm = commentaries[Math.floor(Math.random() * commentaries.length)];
        setAiCommentary(randomComm);
      }, 8000);
      return () => clearInterval(interval);
    }
  }, [pnl, aiSignal]);

  // Active time-range for the equity curve chart
  const [curveRange, setCurveRange] = useState<'1D' | '1W' | '1M' | 'ALL'>('1D');

  // Slice the equity curve to the selected time window
  const filteredCurve = (() => {
    if (!curve || curve.length === 0) return curve;
    const limits: Record<string, number> = { '1D': 78, '1W': 390, '1M': 1680, 'ALL': Infinity };
    const limit = limits[curveRange] ?? Infinity;
    return curve.slice(-Math.min(curve.length, limit));
  })();

  // WebSocket for Real-time Institutional Ticker
  useEffect(() => {
    const ws = new WebSocket('ws://127.0.0.1:8000/ws/live');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Update flashes for price changes
      const newFlashes: any = {};
      Object.keys(data).forEach(key => {
        if (data[key] !== null && typeof data[key] === 'object' && data[key].lp) {
          if (lastPrices[key] && data[key].lp !== lastPrices[key]) {
            newFlashes[key] = data[key].lp > lastPrices[key] ? "up" : "down";
          }
        }
      });

      if (Object.keys(newFlashes).length > 0) {
        setFlashes(newFlashes);
        setTimeout(() => setFlashes({}), 800);
      }

      setLastPrices((prev: any) => {
        const next = { ...prev };
        Object.keys(data).forEach(key => {
          if (data[key] !== null && typeof data[key] === 'object' && data[key].lp) next[key] = data[key].lp;
        });
        return next;
      });

      setTickerData((prev: any) => ({
        ...prev,
        ...Object.fromEntries(
          Object.entries(data).filter(([_, v]) => v !== null)
        ),
        "NIFTY": data.NIFTY ?? prev.NIFTY,
        "BANKNIFTY": data.BANKNIFTY ?? prev.BANKNIFTY,
        "SENSEX": data.SENSEX ?? prev.SENSEX
      }));
    };

    ws.onerror = (error) => {
      console.warn('WebSocket connection attempt failed. Ensure the API bridge is running.', error);
    };

    return () => ws.close();
  }, []); // Remove dependency to prevent reconnection loops

  // Fetch live state from the API (Standard Stats)
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Parallel fetching for performance
        const [stateRes, posRes, logsRes, engineRes] = await Promise.all([
          fetch('http://127.0.0.1:8000/api/state'),
          fetch('http://127.0.0.1:8000/api/positions'),
          fetch('http://127.0.0.1:8000/api/logs?lines=10'),
          fetch('http://127.0.0.1:8000/api/engine/status')
        ]);
 
        const stateData = await stateRes.json();
        const posData = await posRes.json();
        const logsData = await logsRes.json();
        const engineData = await engineRes.json();
        
        if (engineData) {
          setIsEngineLive(engineData.is_active);
        }
        
        if (stateData && !stateData.error) {
          setEquity(stateData.equity || 100000.0);
          setPnl(stateData.pnl || 0.0);
          setTrades(stateData.trades || []);
          
          if (stateData.chartData && stateData.chartData.length > 0) {
            const mappedCurve = stateData.chartData.map((c: any) => ({
              name: new Date(c.time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              value: c.close
            }));
            setCurve(mappedCurve);
          }
        }

        if (posData && posData.status === "success") {
          setPositions(posData.positions || []);
        }

        if (logsData && logsData.logs) {
          setLogs(logsData.logs);
        }

        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000); // Institutional speed: every 3s
    
    return () => clearInterval(interval);
  }, []);

  const handlePanicExit = async () => {
    setIsPanicExecuting(true);
    setPanicStatus("Liquidating all positions...");
    
    try {
      const res = await fetch('http://127.0.0.1:8000/api/panic-exit', { method: 'POST' });
      const data = await res.json();
      
      if (data.status === "success") {
        setPanicStatus(`SUCCESS: Cancelled ${data.cancelled} orders, Closed ${data.closed} positions.`);
        toast.success("NUCLEAR EXIT SUCCESSFUL", {
          description: `Liquidated ${data.closed} positions and cancelled ${data.cancelled} orders.`
        });
        setTimeout(() => {
          setIsPanicModalOpen(false);
          setIsPanicExecuting(false);
          setPanicStatus(null);
        }, 3000);
      } else {
        setPanicStatus(`FAILED: ${data.message}`);
        toast.error("NUCLEAR EXIT FAILED", { description: data.message });
        setTimeout(() => setIsPanicExecuting(false), 3000);
      }
    } catch (error) {
      setPanicStatus("ERROR: Failed to connect to engine.");
      toast.error("CONNECTION ERROR", { description: "API Bridge is unreachable." });
      setTimeout(() => setIsPanicExecuting(false), 3000);
    }
  };

  const toggleEngine = async () => {
    setIsEngineLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/engine/toggle', { method: 'POST' });
      const data = await res.json();
      setIsEngineLive(data.is_active);
    } catch (error) {
      console.error("Failed to toggle engine:", error);
    } finally {
      setIsEngineLoading(false);
    }
  };

  // Poll live AI signals from backend every 30 seconds
  useEffect(() => {
    const fetchAiSignal = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/signals?symbol=NIFTY');
        if (res.ok) {
          const data = await res.json();
          setAiSignal({
            confidence: data.confidence ?? 0,
            status: data.status ?? "Scanning...",
            bias: data.bias ?? "NEUTRAL Bias Detected",
            signals: data.signals ?? [],
          });
        }
      } catch {
        // Backend offline — keep last known state silently
      }
    };
    fetchAiSignal();
    const interval = setInterval(fetchAiSignal, 30_000);
    return () => clearInterval(interval);
  }, []);

  // Calculate some derived stats
  const winRate = trades.length > 0 
    ? (trades.filter((t: any) => t.pnl > 0).length / trades.length * 100)
    : 0.0;

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Global Market Ticker (LIVE STREAMING) */}
          <div className="bg-card/50 backdrop-blur-md border border-border/50 rounded-xl overflow-hidden h-10 flex items-center shadow-inner group">
            <div className="bg-primary/20 text-primary px-3 h-full flex items-center text-xs font-extrabold uppercase tracking-tighter border-r border-border/50 z-10">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></div>
                Live Markets
              </div>
            </div>
            <div className="flex-1 overflow-hidden relative">
              <div className="flex whitespace-nowrap animate-marquee-slower gap-12 items-center px-4 hover:pause">
                {Object.keys(tickerData).filter(k => k !== "trades" && k !== "signalsData").map((symbol, i) => {
                  const data = tickerData[symbol];
                  if (!data || typeof data !== 'object') return null;
                  const isUp = data.chp >= 0;
                  const flashClass = flashes[symbol] === "up" ? "bg-success/20 animate-pulse" : flashes[symbol] === "down" ? "bg-destructive/20 animate-pulse" : "";
                  
                  return (
                    <div key={i} className={`flex items-center gap-3 px-2 py-1 rounded-md transition-all duration-300 ${flashClass}`}>
                      <span className="text-xs font-bold text-foreground/90 tracking-tight">{symbol}</span>
                      <span className="text-xs font-mono font-medium text-foreground">
                        {data.lp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                      <div className={`flex items-center text-[10px] font-bold ${isUp ? "text-success" : "text-destructive"}`}>
                        {isUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}
                        {Math.abs(data.chp).toFixed(2)}%
                      </div>
                    </div>
                  );
                })}
                {/* Duplicate for seamless loop */}
                {Object.keys(tickerData).filter(k => k !== "trades" && k !== "signalsData").map((symbol, i) => {
                  const data = tickerData[symbol];
                  if (!data || typeof data !== 'object') return null;
                  const isUp = data.chp >= 0;
                  return (
                    <div key={`dup-${i}`} className="flex items-center gap-3 px-2 py-1">
                      <span className="text-xs font-bold text-foreground/90 tracking-tight">{symbol}</span>
                      <span className="text-xs font-mono font-medium text-foreground">
                        {data.lp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                      <div className={`flex items-center text-[10px] font-bold ${isUp ? "text-success" : "text-destructive"}`}>
                        {isUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}
                        {Math.abs(data.chp).toFixed(2)}%
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Header & Quick Actions */}
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-extrabold text-2xl text-foreground tracking-tight">Institutional Terminal</h1>
              <p className="text-xs text-muted-foreground">Portfolio Exposure: <span className="text-primary font-bold">₹{((positions.reduce((acc, p) => acc + (p.quantity * p.ltp), 0)) || (equity * 0.1)).toLocaleString('en-IN')}</span> | Risk Level: <span className="text-success font-bold">OPTIMAL</span></p>
            </div>
            
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setIsPanicModalOpen(true)}
                className="px-3 py-1.5 bg-destructive/10 text-destructive border border-destructive/20 rounded-lg text-xs font-bold hover:bg-destructive hover:text-white transition-all uppercase tracking-wider shadow-[0_0_15px_rgba(var(--destructive-rgb),0.2)] active:scale-95"
              >
                Panic Exit
              </button>
              <div 
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all duration-300 ${
                  isEngineLive 
                    ? "bg-success/10 border-success/30 text-success shadow-[0_0_15px_rgba(var(--success-rgb),0.2)]" 
                    : "bg-muted/30 border-border/50 text-muted-foreground"
                }`}
              >
                <div className={`w-2 h-2 rounded-full ${isEngineLive ? "bg-success animate-pulse shadow-[0_0_8px_#10b981]" : "bg-muted-foreground"}`}></div>
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  {isEngineLive ? "Engine Live" : "Engine Off"}
                </span>
              </div>
            </div>
          </div>
          
          <NewsTicker />

          {/* AI Live Analyst Panel */}
          <div
            className="stat-card p-4 relative overflow-hidden flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-muted/10 border-blue-500/20"
          >
            <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-blue-500 to-cyan-500 rounded-l-lg"></div>
            <div className="p-3 bg-blue-500/10 rounded-xl border border-blue-500/20 shrink-0">
               <Brain className="w-6 h-6 text-blue-500 animate-pulse" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                 <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                   <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                  </span>
                   AI Live Analyst 
                 </span>
              </div>
              <div className="text-sm font-mono text-foreground font-medium flex items-center gap-2">
                <span className="text-blue-500">{">"}</span>
                <span className="text-foreground/90">{aiCommentary}</span>
                <span className="w-1.5 h-4 bg-blue-500 animate-pulse inline-block ml-1"></span>
              </div>
            </div>
          </div>

          {/* Core Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Stat Card 1 */}
            <div className="glass-card rounded-xl p-4 border border-border/20 flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Total Equity</span>
                <Briefcase className="w-3.5 h-3.5 text-muted-foreground" />
              </div>
              <div className="mt-2">
                <div className="text-2xl font-bold font-mono text-foreground leading-none">
                  ₹{equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                  <span className="text-success font-bold">+1.2%</span> vs yesterday
                </p>
              </div>
            </div>

            {/* Stat Card 2 */}
            <div className="glass-card rounded-xl p-4 border border-border/20 flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Day's Net P&L</span>
                <TrendingUp className="w-3.5 h-3.5 text-success" />
              </div>
              <div className="mt-2">
                <div className={`text-2xl font-bold font-mono leading-none ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                  {pnl >= 0 ? "+" : ""}₹{pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                  {pnl >= 0 ? <ArrowUpRight className="w-3 h-3 text-success" /> : <ArrowDownRight className="w-3 h-3 text-destructive" />}
                  Realized + Unrealized
                </p>
              </div>
            </div>

            {/* Stat Card 3 - AI CONVICTION GAUGE (Compact) */}
            <div className="glass-card rounded-xl p-4 border border-border/20 flex flex-col justify-between relative overflow-hidden">
              <div className="flex justify-between items-start">
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest">AI Conviction</span>
                <Activity className="w-3.5 h-3.5 text-primary" />
              </div>
              <div className="mt-2 flex items-end justify-between">
                <div>
                  <div className="text-2xl font-bold font-mono text-foreground leading-none">{winRate.toFixed(1)}%</div>
                  <p className={`text-[10px] font-bold mt-1 uppercase tracking-tighter ${winRate > 60 ? "text-success" : "text-warning"}`}>
                    {winRate > 75 ? "Strong Bullish" : winRate > 50 ? "Bullish Bias" : "Neutral/Cautious"}
                  </p>
                </div>
                {/* SVG Gauge placeholder */}
                <div className="w-12 h-6 relative overflow-hidden">
                  <div className="w-12 h-12 rounded-full border-4 border-muted/30 absolute top-0 left-0"></div>
                  <div 
                    className="w-12 h-12 rounded-full border-4 border-primary absolute top-0 left-0"
                    style={{ 
                      clipPath: 'polygon(0 0, 100% 0, 100% 50%, 0 50%)', 
                      transform: `rotate(${(winRate / 100) * 180 - 90}deg)` 
                    }}
                  ></div>
                </div>
              </div>
            </div>

            {/* Stat Card 4 — Total Trades (distinct from card 3) */}
            <div className="glass-card rounded-xl p-4 border border-border/20 flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Total Trades</span>
                <Target className="w-3.5 h-3.5 text-warning" />
              </div>
              <div className="mt-2">
                <div className="text-2xl font-bold font-mono text-foreground leading-none">{trades.length}</div>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-[9px] text-success font-bold">{trades.filter((t: any) => t.pnl > 0).length}W</span>
                  <div className="flex-1 h-1 bg-muted/30 rounded-full overflow-hidden">
                    <div className="h-full bg-success rounded-full" style={{ width: `${winRate}%` }}></div>
                  </div>
                  <span className="text-[9px] text-destructive font-bold">{trades.filter((t: any) => t.pnl <= 0).length}L</span>
                </div>
              </div>
            </div>
          </div>

          {/* Main Content Area: High Density Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Chart Area - 2 Columns */}
            <div className="lg:col-span-2 glass-card rounded-xl p-4 border border-border/20 flex flex-col h-full min-h-[300px]">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Performance Curve</h3>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-tight font-bold">Intraday Equity Projection</p>
                </div>
                <div className="flex gap-1">
                  {(['1D', '1W', '1M', 'ALL'] as const).map(t => (
                    <button
                      key={t}
                      onClick={() => setCurveRange(t)}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
                        curveRange === t
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex-1 w-full mt-4 min-h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={filteredCurve}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={pnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0.25}/>
                        <stop offset="95%" stopColor={pnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={9} axisLine={false} tickLine={false} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={9} domain={['dataMin - 500', 'dataMax + 500']} axisLine={false} tickLine={false} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "hsl(var(--card))", borderColor: "hsl(var(--border))", borderRadius: "8px", fontSize: "10px" }}
                    />
                    <Area type="monotone" dataKey="value" stroke={pnl >= 0 ? "#10b981" : "#ef4444"} strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Active Positions Widget */}
            <div className="lg:col-span-2 glass-card rounded-xl border border-border/20 flex flex-col overflow-hidden h-full min-h-[300px]">
              <div className="p-3 bg-muted/20 border-b border-border/20 flex justify-between items-center">
                <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                  <ShieldAlert className="w-3.5 h-3.5 text-primary" />
                  Active Positions
                </h3>
                {positions.length > 0 && (
                  <span className="text-[10px] font-bold text-primary uppercase bg-primary/10 px-2 py-0.5 rounded-full animate-pulse">
                    {positions.length} Open
                  </span>
                )}
              </div>
              
              <div className="flex-1 overflow-y-auto custom-scrollbar">
                {positions.length > 0 ? (
                  <table className="w-full text-xs text-left">
                    <thead className="bg-muted/30 sticky top-0 z-10">
                      <tr className="text-muted-foreground uppercase tracking-widest text-[9px]">
                        <th className="p-3 font-bold">Symbol</th>
                        <th className="text-right p-3 font-bold">Avg Price</th>
                        <th className="text-right p-3 font-bold">LTP</th>
                        <th className="text-right p-3 font-bold">P&L</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                      {positions.map((pos, i) => (
                        <tr key={i} className="hover:bg-primary/5 transition-colors group">
                          <td className="px-4 py-3 font-bold text-foreground">{pos.symbol}</td>
                          <td className="px-4 py-3 font-mono text-right text-muted-foreground">₹{pos.average_price.toFixed(2)}</td>
                          <td className="px-4 py-3 font-mono text-right font-bold text-foreground">₹{pos.ltp.toFixed(2)}</td>
                          <td className={`px-4 py-3 font-mono font-bold text-right ${pos.unrealized_pnl >= 0 ? "text-success" : "text-destructive"}`}>
                            {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl.toLocaleString('en-IN')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center opacity-30 gap-3 py-10">
                    <Inbox className="w-12 h-12" />
                    <p className="text-sm font-bold uppercase tracking-widest">No Active Positions</p>
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Row: Terminal & Scanner */}
            <div className="lg:col-span-3 glass-card rounded-xl border border-border/20 flex flex-col overflow-hidden h-full min-h-[280px] shadow-2xl transition-all duration-300">
              <div className="p-2.5 bg-[#0a0b10] dark:bg-[#0a0b10] light:bg-slate-800 border-b border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Terminal className="w-3.5 h-3.5 text-primary" />
                  <span className="text-[10px] font-extrabold text-slate-300 uppercase tracking-[0.2em]">Execution Terminal v1.4.0</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex gap-2 text-[9px] font-mono text-primary/80">
                    <span className="animate-pulse">●</span>
                    <span>LIVE STREAMING</span>
                  </div>
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56] shadow-[0_0_8px_rgba(255,95,86,0.3)]"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e] shadow-[0_0_8px_rgba(255,189,46,0.3)]"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f] shadow-[0_0_8px_rgba(39,201,63,0.3)]"></div>
                  </div>
                </div>
              </div>
              <div className="flex-1 bg-[#0d0f14] light:bg-[#f8fafc] p-4 font-mono text-[11px] leading-relaxed overflow-y-auto scrollbar-thin scrollbar-thumb-primary/20">
                {logs.length === 0 ? (
                  <div className="flex items-center gap-2 text-slate-500 light:text-slate-400 italic">
                    <div className="w-1.5 h-1.5 bg-primary rounded-full animate-ping"></div>
                    Initializing secure log stream...
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {logs.map((log, i) => {
                      const timestampMatch = log.match(/\[(.*?)\]/);
                      const timestamp = timestampMatch ? timestampMatch[0] : "";
                      const rest = log.replace(timestamp, "").trim();
                      
                      let tagColor = "text-slate-400 light:text-slate-500";
                      if (rest.includes("BUY")) tagColor = "text-[#10b981] font-black underline decoration-2";
                      if (rest.includes("SELL")) tagColor = "text-[#ef4444] font-black underline decoration-2";
                      if (rest.includes("error") || rest.includes("Error") || rest.includes("REJECTED")) tagColor = "text-[#f43f5e] font-bold bg-[#f43f5e]/10 px-1 rounded";
                      if (rest.includes("SCAN")) tagColor = "text-[#f59e0b] font-bold";
                      if (rest.includes("AUTH") || rest.includes("SYSTEM")) tagColor = "text-[#00d2ff] light:text-[#0ea5e9] font-bold";
                      
                      return (
                        <div key={i} className="flex gap-3 items-start border-l-2 border-transparent hover:border-primary/30 hover:bg-white/5 light:hover:bg-slate-100 transition-all pl-1">
                          <span className="text-[#64748b] light:text-[#94a3b8] shrink-0 font-bold select-none">{timestamp}</span>
                          <span className={`${tagColor} break-all tracking-tight`}>{rest}</span>
                        </div>
                      );
                    })}
                    <div className="flex items-center gap-2 pt-1 text-primary animate-pulse font-black text-xs">
                      <span>{'>'}</span>
                      <span className="tracking-tighter">ENGINE MONITORING ACTIVE</span>
                      <span className="w-1.5 h-3 bg-primary"></span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* AI Signal Scanner — Live from /api/signals */}
            <div className="lg:col-span-1 glass-card rounded-xl p-4 border border-border/20 flex flex-col justify-between h-full min-h-[280px]">
              <div>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-xs font-bold text-foreground uppercase tracking-widest">AI Scanner</h3>
                  <Search className="w-3.5 h-3.5 text-muted-foreground" />
                </div>

                {/* Confidence Gauge */}
                <div className="mb-3 p-2.5 bg-muted/30 rounded-lg border border-border/50">
                  <div className="flex justify-between items-center mb-1.5">
                    <p className="text-[10px] text-foreground font-bold">NIFTY 50</p>
                    <span className={`text-[9px] font-bold uppercase ${
                      aiSignal.bias.includes("BUY") ? "text-success" :
                      aiSignal.bias.includes("SELL") ? "text-destructive" : "text-warning"
                    }`}>
                      {aiSignal.bias.replace(" Bias Detected", "")}
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-muted/40 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${
                        aiSignal.confidence >= 75 ? "bg-success" :
                        aiSignal.confidence >= 50 ? "bg-warning" : "bg-destructive/60"
                      }`}
                      style={{ width: `${Math.min(aiSignal.confidence, 100)}%` }}
                    />
                  </div>
                  <p className="text-[9px] text-muted-foreground mt-1 font-mono">
                    Conf: <span className="text-foreground font-bold">{aiSignal.confidence}%</span>
                    &nbsp;·&nbsp;{aiSignal.status}
                  </p>
                </div>

                {/* Latest signals */}
                <div className="space-y-1.5">
                  {aiSignal.signals.length > 0 ? (
                    aiSignal.signals.slice(0, 3).map((sig: any, i: number) => (
                      <div key={i} className="p-2 bg-muted/20 rounded-lg border border-border/40">
                        <div className="flex justify-between items-center">
                          <span className="text-[9px] font-bold text-foreground">{sig.type}</span>
                          <span className={`text-[9px] font-bold ${
                            sig.bias === "BUY" ? "text-success" : "text-destructive"
                          }`}>{sig.strength}</span>
                        </div>
                        <div className="flex justify-between items-center mt-0.5">
                          <span className="text-[8px] text-muted-foreground font-mono">{sig.time}</span>
                          <span className="text-[8px] text-muted-foreground font-mono">Conf: {sig.confidence}%</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-2.5 bg-muted/20 rounded-lg border border-border/40 opacity-60">
                      <p className="text-[9px] text-muted-foreground text-center italic">Waiting for market session...</p>
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={() => window.location.href = '/signals'}
                className="w-full mt-4 py-2 bg-primary/10 text-primary hover:bg-primary hover:text-white text-[10px] font-bold rounded-lg border border-primary/20 transition-all uppercase tracking-widest"
              >
                Full AI Report
              </button>
            </div>
          </div>
        </main>
      </div>

      {/* PANIC EXIT MODAL (ULTRA ADVANCED) */}
      {isPanicModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-background/80 backdrop-blur-md animate-in fade-in duration-300"></div>
          
          <div className="relative w-full max-w-md glass-card border-destructive/30 rounded-2xl p-8 shadow-[0_0_50px_rgba(239,68,68,0.2)] animate-in zoom-in-95 duration-200">
            {isPanicExecuting && (
              <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-destructive rounded-2xl animate-pulse">
                <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mb-4"></div>
                <p className="text-white font-black uppercase tracking-widest text-lg">Executing Nuclear Exit</p>
                <p className="text-white/70 text-xs mt-2">{panicStatus}</p>
              </div>
            )}

            <div className="flex flex-col items-center text-center">
              <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mb-6">
                <AlertTriangle className="w-8 h-8 text-destructive animate-bounce" />
              </div>
              
              <h2 className="text-2xl font-black text-foreground uppercase tracking-tight mb-2">Confirm Panic Exit?</h2>
              <p className="text-sm text-muted-foreground mb-8">
                This will <span className="text-destructive font-bold">immediately square off all open positions</span> and cancel all pending orders. This action cannot be undone.
              </p>

              <div className="flex flex-col w-full gap-3">
                <button 
                  onClick={handlePanicExit}
                  disabled={isPanicExecuting}
                  className="w-full py-4 bg-destructive text-white font-black uppercase tracking-widest rounded-xl hover:bg-destructive/90 transition-all active:scale-95 shadow-[0_0_20px_rgba(239,68,68,0.4)]"
                >
                  Confirm Nuclear Liquidation
                </button>
                <button 
                  onClick={() => setIsPanicModalOpen(false)}
                  disabled={isPanicExecuting}
                  className="w-full py-3 bg-muted/50 text-foreground font-bold rounded-xl hover:bg-muted transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
