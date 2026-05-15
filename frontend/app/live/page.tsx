"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect, useRef, Suspense } from "react";
import { 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  Zap, 
  Shield, 
  Target,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Layers,
  Globe,
  Briefcase
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

declare global {
  interface Window {
    TradingView: any;
  }
}

export default function LiveTrading() {
  return (
    <Suspense fallback={
      <div className="flex h-screen bg-background text-foreground items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
        <span className="ml-2">Loading Terminal...</span>
      </div>
    }>
      <LiveTradingContent />
    </Suspense>
  );
}

function LiveTradingContent() {
  const searchParams = useSearchParams();
  const urlSymbol = searchParams.get('symbol') || 'SENSEX';

  const [strategy, setStrategy] = useState("ema_rsi");
  const [timeframe, setTimeframe] = useState("5 Min");
  const [tradingMode, setTradingMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('tradingMode');
      return saved || "paper"; // Default to paper (safer!)
    }
    return "paper";
  });
  const [equity, setEquity] = useState(100000.00);
  const [tickerData, setTickerData] = useState({
    NIFTY: { lp: 23820.35, chp: -1.49 },
    SENSEX: { lp: 76015.28, chp: -1.70 },
    BANKNIFTY: { lp: 51000.00, chp: 0.0 }
  });
  const [pnl, setPnl] = useState(0.00);
  const [trades, setTrades] = useState<any[]>([]);
  const [currentPrice, setCurrentPrice] = useState(0);
  const [changePercent, setChangePercent] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [aiConfidence, setAiConfidence] = useState(0);
  const [riskStatus, setRiskStatus] = useState("ACTIVE");
  const [isWsConnected, setIsWsConnected] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const prevTradesRef = useRef<any[]>([]);

  const addNotification = (message: string, type: 'success' | 'danger' | 'warning' | 'info') => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  };

  // Detect new trades and trigger notifications
  useEffect(() => {
    if (trades.length > prevTradesRef.current.length) {
      // New trade found!
      const newTrades = trades.filter(t => !prevTradesRef.current.some(pt => pt.id === t.id));
      newTrades.forEach(t => {
        let message = "";
        let type: 'success' | 'danger' | 'warning' | 'info' = 'info';
        
        if (t.side === 'BUY') {
          message = `🟢 BUY Order Executed: ${t.symbol} @ ₹${t.price.toFixed(2)}`;
          type = 'success';
        } else if (t.side === 'SELL') {
          message = `🔴 SELL Order Executed: ${t.symbol} @ ₹${t.price.toFixed(2)}`;
          type = 'danger';
        } else if (t.status === 'Target') {
          message = `🎯 Target Hit: ${t.symbol} @ ₹${t.price.toFixed(2)}`;
          type = 'success';
        } else if (t.status === 'SL') {
          message = `🛡️ Stop Loss Hit: ${t.symbol} @ ₹${t.price.toFixed(2)}`;
          type = 'warning';
        } else {
          message = `🔔 Trade Update: ${t.symbol} status is ${t.status}`;
          type = 'info';
        }
        
        addNotification(message, type);
      });
    }
    prevTradesRef.current = trades;
  }, [trades]);

  // Map our symbols to TradingView symbols
  const getTVSymbol = (sym: string) => {
    if (sym === "SENSEX") return "BSE:SENSEX";
    if (sym === "NIFTY") return "NSE:NIFTY";
    if (sym === "BANKNIFTY") return "NSE:BANKNIFTY";
    if (sym === "FINNIFTY") return "NSE:FINNIFTY";
    // Default to NSE for stocks if not a recognized index
    return `NSE:${sym}`;
  };

  // Fetch Settings (to get trading mode and strategy)
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('/api/settings');
        if (res.ok) {
          const data = await res.json();
          const mode = data.live_trading_mode ? "live" : "paper";
          setTradingMode(mode);
          if (typeof window !== 'undefined') {
            localStorage.setItem('tradingMode', mode);
          }
          setStrategy(data.active_strategy || "ema_rsi");
        }
      } catch (error) {
        console.error("Failed to fetch settings:", error);
      }
    };
    fetchSettings();
  }, []);

  // Handle Strategy Change
  const handleStrategyChange = async (newStrategy: string) => {
    setStrategy(newStrategy);
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_strategy: newStrategy })
      });
    } catch (error) {
      console.error("Failed to update strategy:", error);
    }
  };
  
  // Toggle Trading Mode (Live/Paper)
  const toggleTradingMode = async () => {
    const newMode = tradingMode === 'live' ? 'paper' : 'live';
    const isLive = newMode === 'live';
    
    // Optimistically update UI
    setTradingMode(newMode);
    if (typeof window !== 'undefined') {
      localStorage.setItem('tradingMode', newMode);
    }
    
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ live_trading_mode: isLive })
      });
      
      if (!res.ok) {
        console.error("Failed to update trading mode on server");
        // Revert UI on failure
        setTradingMode(tradingMode);
      }
    } catch (error) {
      console.error("Error updating trading mode:", error);
      setTradingMode(tradingMode); // Revert UI
    }
  };

  // Fetch State (P&L, Equity, etc.)
  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch(`/api/state?symbol=${urlSymbol}&live=${tradingMode === 'live'}`, { cache: 'no-store' });
        const data = await res.json();
        
        setEquity(data.equity);
        setPnl(data.pnl);
        setTrades(data.trades || []);
        const parsedPrice = Number(data.currentPrice);
        // Optimization: If WebSocket is connected, let it handle live price updates.
        // If WebSocket is disconnected or price is 0 (initial load), update from polling!
        if (!isWsConnected || currentPrice === 0) {
          if (parsedPrice && parsedPrice !== 0) {
            setCurrentPrice(parsedPrice);
          }
          if (data.changePercent) {
            setChangePercent(data.changePercent);
          }
        }
        
        // Extract AI Confidence if available
        if (data.signalsData && data.signalsData.confidence) {
          setAiConfidence(data.signalsData.confidence);
        }
        
        // Extract Risk Status / Bias if available
        if (data.signalsData && data.signalsData.status) {
          setRiskStatus(data.signalsData.status);
        }
        
        // Equity is now handled directly by the backend in data.equity
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch state:", error);
        setIsLoading(false); // Ensure loading stops on error
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 1000); // Poll every 1s
    return () => clearInterval(interval);
  }, [urlSymbol]);

  // WebSocket for real-time price streaming (Institutional Fast Stream)
  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/live`);
    
    ws.onopen = () => {
      console.log("WebSocket Connected");
      setIsWsConnected(true);
    };
    
    ws.onclose = () => {
      console.log("WebSocket Disconnected");
      setIsWsConnected(false);
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.NIFTY) {
        setTickerData(prev => {
          if (prev.NIFTY.lp === data.NIFTY.lp && 
              prev.SENSEX.lp === data.SENSEX.lp && 
              prev.BANKNIFTY.lp === data.BANKNIFTY.lp) {
            return prev; // Optimization: Don't re-render if data is same
          }
          return data;
        });
        
        // Also update the selected symbol's price in the header if it matches
        const selectedData = data[urlSymbol];
        if (selectedData) {
          setCurrentPrice(prev => prev === selectedData.lp ? prev : selectedData.lp);
          setChangePercent(prev => prev === selectedData.chp ? prev : selectedData.chp);
        }
        
        // Update trades from WebSocket
        if (data.trades) {
          setTrades(data.trades);
        }
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };
    
    return () => ws.close();
  }, [urlSymbol]);


  // Load the REAL Advanced TradingView Widget with ALL features!
  useEffect(() => {
    const initWidget = () => {
      if (window.TradingView && document.getElementById(`tradingview_chart_${urlSymbol}`)) {
        const tvSymbol = getTVSymbol(urlSymbol);
        console.log(`Initializing Advanced TradingView for: ${tvSymbol}`);
        
        new window.TradingView.widget({
          "width": "100%",
          "height": 450,
          "symbol": tvSymbol,
          "interval": "D",
          "timezone": "Asia/Kolkata",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#090a0f",
          "enable_publishing": false,
          "hide_side_toolbar": false, // SHOW THE DRAWING TOOLBAR!
          "allow_symbol_change": true,
          "details": true,
          "hotlist": true,
          "calendar": true,
          "show_popup_button": true,
          "popup_width": "1000",
          "popup_height": "650",
          "container_id": `tradingview_chart_${urlSymbol}`
        });
      }
    };

    if (window.TradingView) {
      initWidget();
    } else {
      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = initWidget;
      document.head.appendChild(script);
    }
  }, [urlSymbol]);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Ticker Tape & Broker Login Row */}
          <div className="flex justify-between items-center gap-4">
            {/* Ticker Tape */}
            <div className="flex-1 flex items-center gap-6 px-4 py-2 bg-muted/20 border border-border/50 rounded-lg text-xs font-mono overflow-x-auto">
              <span className="text-muted-foreground font-bold uppercase tracking-wider">Indices:</span>
              {/* NIFTY */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className="font-bold text-foreground">NIFTY</span>
                <span className={tickerData.NIFTY.chp >= 0 ? 'text-success' : 'text-destructive'}>₹{(tickerData.NIFTY.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                <span className={`text-xs ${tickerData.NIFTY.chp >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {tickerData.NIFTY.chp >= 0 ? '+' : ''}{tickerData.NIFTY.chp.toFixed(2)}%
                </span>
              </div>
              {/* SENSEX */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className="font-bold text-foreground">SENSEX</span>
                <span className={tickerData.SENSEX.chp >= 0 ? 'text-success' : 'text-destructive'}>₹{(tickerData.SENSEX.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                <span className={`text-xs ${tickerData.SENSEX.chp >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {tickerData.SENSEX.chp >= 0 ? '+' : ''}{tickerData.SENSEX.chp.toFixed(2)}%
                </span>
              </div>
              {/* BANKNIFTY */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className="font-bold text-foreground">BANKNIFTY</span>
                <span className={tickerData.BANKNIFTY.chp >= 0 ? 'text-success' : 'text-destructive'}>₹{(tickerData.BANKNIFTY.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                <span className={`text-xs ${tickerData.BANKNIFTY.chp >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {tickerData.BANKNIFTY.chp >= 0 ? '+' : ''}{tickerData.BANKNIFTY.chp.toFixed(2)}%
                </span>
              </div>
            </div>

          </div>

          {/* Header */}
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground">Live Trading Terminal</h1>
              <p className="text-sm text-muted-foreground">Monitor real-time executions and account equity.</p>
            </div>
            
            <div className="flex items-center gap-4">
              {/* Prominent Symbol, Price & Percentage Display */}
              <div className="flex items-center gap-2 px-4 py-2 bg-muted/30 border border-border/50 rounded-lg text-sm font-bold font-mono">
                <span className="text-primary">{urlSymbol}</span>
                <span className="text-muted-foreground">|</span>
                <span className={`${changePercent >= 0 ? 'text-success' : 'text-destructive'}`}>₹{(currentPrice ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                <span className={`flex items-center gap-0.5 ml-1 ${changePercent >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {changePercent >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                  {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
                </span>
              </div>

              {/* Strategy Selector */}
              <div className="relative">
                <Layers className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                <select 
                  value={strategy}
                  onChange={(e) => handleStrategyChange(e.target.value)}
                  className="bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="ema_rsi">EMA + RSI (Classic)</option>
                  <option value="enhanced_ai">Enhanced AI Strategy</option>
                  <option value="institutional_ema">Institutional EMA</option>
                  <option value="advanced_ai">Advanced AI/ML</option>
                  <option value="premium">Premium Options Alpha</option>
                </select>
              </div>
              
              {/* Timeframe Selector */}
              <div className="relative">
                <Clock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                <select 
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="1 Min">1 Min</option>
                  <option value="3 Min">3 Min</option>
                  <option value="5 Min">5 Min</option>
                  <option value="15 Min">15 Min</option>
                  <option value="30 Min">30 Min</option>
                  <option value="1 Hour">1 Hour</option>
                  <option value="1 Week">1 Week</option>
                  <option value="1 Month">1 Month</option>
                </select>
              </div>
                {/* Toggle Switch */}
                <div className="flex items-center gap-2 bg-muted/20 px-3 py-1.5 rounded-lg border border-border/10">
                  <span className={`text-xs font-bold flex items-center gap-1 transition-colors ${tradingMode === 'live' ? 'text-success' : 'text-muted-foreground/40'}`}>
                    <Globe className="w-3.5 h-3.5" />
                    Live
                  </span>
                  
                  <button
                    onClick={toggleTradingMode}
                    className={`relative w-8 h-4.5 rounded-full transition-colors focus:outline-none ${tradingMode === 'live' ? 'bg-success' : 'bg-[#d946ef]'}`}
                  >
                    <div className={`absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-white rounded-full shadow-md transition-transform duration-200 transform ${tradingMode === 'paper' ? 'translate-x-3.5' : 'translate-x-0'}`}></div>
                  </button>
                  
                  <span className={`text-xs font-bold flex items-center gap-1 transition-colors ${tradingMode === 'paper' ? 'text-[#d946ef]' : 'text-muted-foreground/40'}`}>
                    <Briefcase className="w-3.5 h-3.5" />
                    Paper
                  </span>
                </div>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {/* Card 1: Current Equity */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 space-y-2 shadow-xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">💰 Current Equity</span>
              </div>
              <div className="text-2xl font-bold font-mono text-foreground">
                {isLoading ? "---" : `₹${(equity || 100000.00).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </div>
            
            {/* Card 2: Today's PNL */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 space-y-2 shadow-xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">📊 Today's PNL</span>
              </div>
              <div className={`text-2xl font-bold font-mono ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                {isLoading ? "---" : `${pnl >= 0 ? "+" : ""}₹${(pnl ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </div>

            {/* Card 3: AI Confidence */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 shadow-xl flex items-center justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">🤖 AI Confidence</span>
                </div>
                <div className={`text-sm font-bold ${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"}`}>
                  {aiConfidence >= 75 ? "High Conviction" : aiConfidence >= 50 ? "Mild Bias" : "Scan Mode"}
                </div>
                <div className="text-xs text-gray-500">
                  Based on AI Strategy
                </div>
              </div>
              
              {/* Smart Circle */}
              <div className="relative w-16 h-16">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                  <defs>
                    <linearGradient id="aiGradient" x1="0%" y1="100%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#EF4444" /> {/* Red */}
                      <stop offset="50%" stopColor="#F59E0B" /> {/* Yellow */}
                      <stop offset="100%" stopColor="#10B981" /> {/* Green */}
                    </linearGradient>
                  </defs>
                  {/* Background Circle (with opacity) */}
                  <circle
                    className={`${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"} stroke-current opacity-20`}
                    strokeWidth="10"
                    cx="50"
                    cy="50"
                    r="40"
                    fill="transparent"
                  ></circle>
                  {/* Progress Circle */}
                  <circle
                    stroke="url(#aiGradient)"
                    strokeWidth="10"
                    strokeDasharray="251.2"
                    strokeDashoffset={251.2 - (251.2 * aiConfidence) / 100}
                    strokeLinecap="round"
                    cx="50"
                    cy="50"
                    r="40"
                    fill="transparent"
                    className="transition-all duration-500"
                  ></circle>
                </svg>
                {/* Number in center */}
                <div className={`absolute inset-0 flex items-center justify-center text-sm font-bold font-mono ${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"}`}>
                  {isLoading ? "---" : `${aiConfidence.toFixed(0)}%`}
                </div>
              </div>
            </div>

            {/* Card 4: Risk Engine */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 space-y-2 shadow-xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">🛡️ Risk Engine</span>
              </div>
              <div className="text-2xl font-bold font-mono text-success">
                ACTIVE
              </div>
              <div className="text-xs font-bold text-gray-400">
                Limits OK
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* REAL TradingView Chart with ALL features */}
            <div className="lg:col-span-2 glass-card rounded-xl p-6 border border-border/20">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h3 className="font-display font-bold text-lg text-foreground">Active Market Chart: {urlSymbol}</h3>
                  <p className="text-xs text-muted-foreground">Advanced TradingView Terminal with drawing tools and indicators</p>
                </div>
              </div>

              {/* Container for TradingView iframe */}
              <div 
                key={urlSymbol}
                id={`tradingview_chart_${urlSymbol}`} 
                className="w-full rounded-lg overflow-hidden border border-border/10 bg-[#090a0f] flex items-center justify-center" 
                style={{ height: '450px' }}
              >
                <div className="text-xs text-muted-foreground flex items-center gap-2">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  Loading TradingView Terminal...
                </div>
              </div>
            </div>

            {/* Execution Feed */}
            <div className="glass-card rounded-xl p-6 border border-border/20">
              <h3 className="font-display font-bold text-lg text-foreground mb-4">Live Execution Feed</h3>
              
              <div className="space-y-4 h-[450px] overflow-y-auto pr-2">
                {trades.length === 0 ? (
                  <div className="text-center text-sm text-muted-foreground py-10">
                    No trades recorded today.
                  </div>
                ) : (
                  trades.map((trade, i) => (
                    <div key={i} className="flex items-center justify-between border-b border-border/10 pb-3 last:border-0">
                      <div className="flex items-center gap-3">
                        <div className={`p-1.5 rounded-lg ${trade.side === "BUY" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"}`}>
                          {trade.side === "BUY" ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                        </div>
                        <div>
                          <p className="text-xs font-medium text-foreground">{trade.symbol}</p>
                          <p className="text-[10px] text-muted-foreground">{trade.time}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-mono font-bold text-foreground">₹{trade.price.toFixed(2)}</p>
                        <p className={`text-[10px] font-medium ${trade.side === "BUY" ? "text-success" : "text-destructive"}`}>
                          {trade.side}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* Live Notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        <AnimatePresence>
          {notifications.map(n => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 50 }}
              className={`p-4 rounded-lg shadow-lg flex items-center gap-2 text-white font-medium ${
                n.type === 'success' ? 'bg-emerald-600' :
                n.type === 'danger' ? 'bg-red-600' :
                n.type === 'warning' ? 'bg-amber-600' : 'bg-blue-600'
              }`}
            >
              {n.type === 'success' ? <TrendingUp className="w-5 h-5" /> :
               n.type === 'danger' ? <TrendingDown className="w-5 h-5" /> :
               n.type === 'warning' ? <Shield className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
              {n.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
