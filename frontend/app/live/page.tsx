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
  const urlSymbol = searchParams.get('symbol') || 'NIFTY';

  const [strategy, setStrategy] = useState("ema_rsi");
  const [tradingMode, setTradingMode] = useState("live"); // 'live' or 'paper'
  const [equity, setEquity] = useState(100000.00);
  const [pnl, setPnl] = useState(0.00);
  const [trades, setTrades] = useState<any[]>([]);
  const [currentPrice, setCurrentPrice] = useState(0);
  const [changePercent, setChangePercent] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [aiConfidence, setAiConfidence] = useState(0);
  const [riskStatus, setRiskStatus] = useState("ACTIVE");

  // Map our symbols to TradingView symbols
  const getTVSymbol = (sym: string) => {
    if (sym === "SENSEX") return "BSE:SENSEX";
    if (sym === "NIFTY") return "NSE:NIFTY";
    if (sym === "BANKNIFTY") return "NSE:BANKNIFTY";
    if (sym === "FINNIFTY") return "NSE:FINNIFTY";
    // Fallback to BSE to see if it bypasses blocks
    return `BSE:${sym}`;
  };

  // Fetch Settings (to get trading mode and strategy)
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('/api/settings');
        if (res.ok) {
          const data = await res.json();
          setTradingMode(data.live_trading_mode ? "live" : "paper");
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
        if (parsedPrice && parsedPrice !== 0) {
          setCurrentPrice(parsedPrice);
        }
        if (data.changePercent) {
          setChangePercent(data.changePercent);
        }
        
        // Extract AI Confidence if available
        if (data.signalsData && data.signalsData.confidence) {
          setAiConfidence(data.signalsData.confidence);
        }
        
        // Extract Risk Status / Bias if available
        if (data.signalsData && data.signalsData.status) {
          setRiskStatus(data.signalsData.status);
        }
        
        // If live mode and fundsData available, extract balance!
        if (tradingMode === 'live' && data.fundsData && data.fundsData.fund_limit) {
          const totalBalanceItem = data.fundsData.fund_limit.find((item: any) => 
            item.title === "Total Balance" || item.id === 1 || item.id === 10
          );
          if (totalBalanceItem) {
            setEquity(totalBalanceItem.equityAmount);
          } else if (data.fundsData.fund_limit.length > 0) {
            setEquity(data.fundsData.fund_limit[0].equityAmount);
          }
        }
        
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch state:", error);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 1000); // Poll every 1s
    return () => clearInterval(interval);
  }, [urlSymbol]);

  // WebSocket for real-time price streaming (Institutional Fast Stream)
  useEffect(() => {
    const ws = new WebSocket('ws://127.0.0.1:8000/ws/live');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.currentPrice && data.currentPrice !== 0) {
        setCurrentPrice(data.currentPrice);
      }
      if (data.changePercent) {
        setChangePercent(data.changePercent);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };
    
    return () => ws.close();
  }, []);


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
          "interval": "5",
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
                <span className={`${changePercent >= 0 ? 'text-success' : 'text-destructive'}`}>₹{currentPrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
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
                  <option value="options_strat">Options Strategy</option>
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
                {isLoading ? "---" : `₹${(tradingMode === 'paper' ? 100000.00 : equity).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </div>
            
            {/* Card 2: Today's PNL */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 space-y-2 shadow-xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">📊 Today's PNL</span>
              </div>
              <div className={`text-2xl font-bold font-mono ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                {isLoading ? "---" : `${pnl >= 0 ? "+" : ""}₹${pnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </div>

            {/* Card 3: AI Confidence */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-border/20 space-y-2 shadow-xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">🤖 AI Confidence</span>
              </div>
              <div className="text-2xl font-bold font-mono text-primary">
                {isLoading ? "---" : `${aiConfidence.toFixed(1)}%`}
              </div>
              <div className={`text-xs font-bold ${aiConfidence >= 75 ? "text-success" : "text-warning"}`}>
                {aiConfidence >= 75 ? "▲ High Conviction" : "▼ Scan Mode"}
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
    </div>
  );
}
