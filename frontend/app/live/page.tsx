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
  Briefcase,
  Package,
  ChevronDown
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

declare global {
  interface Window {
    // TradingView is a third-party browser global injected via script tag — must stay as any
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    TradingView: any;
  }
}

// --- Type Definitions ---
interface Trade {
  id?: string | number;
  symbol: string;
  side: 'BUY' | 'SELL';
  price: number;
  time: string;
  status?: string;
}

interface Notification {
  id: number;
  message: string;
  type: 'success' | 'danger' | 'warning' | 'info';
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

const LOT_SIZES: Record<string, number> = {
  "NIFTY": 65,
  "BANKNIFTY": 30,
  "SENSEX": 20,
  "FINNIFTY": 40,
  "MIDCPNIFTY": 50,
  "ADANIENT": 309,
  "ADANIPORTS": 475,
  "APOLLOHOSP": 125,
  "ASIANPAINT": 250,
  "AXISBANK": 625,
  "BAJAJ-AUTO": 75,
  "BAJAJFINSV": 250,
  "BAJFINANCE": 750,
  "BHARTIARTL": 475,
  "BPCL": 1975,
  "BRITANNIA": 125,
  "CIPLA": 375,
  "COALINDIA": 1350,
  "DIVISLAB": 150,
  "DRREDDY": 125,
  "EICHERMOT": 175,
  "GRASIM": 250,
  "HCLTECH": 350,
  "HDFCBANK": 275,
  "HDFCLIFE": 1100,
  "HEROMOTOCO": 150,
  "HINDALCO": 1400,
  "HINDUNILVR": 300,
  "ICICIBANK": 350,
  "INDUSINDBK": 500,
  "INFY": 400,
  "ITC": 1600,
  "JSWSTEEL": 675,
  "KOTAKBANK": 400,
  "LT": 150,
  "LTIM": 150,
  "M&M": 150,
  "MARUTI": 50,
  "NESTLEIND": 400,
  "NTPC": 1500,
  "ONGC": 3850,
  "POWERGRID": 3600,
  "RELIANCE": 250,
  "SBILIFE": 375,
  "SBIN": 750,
  "SUNPHARMA": 350,
  "TATACONSUM": 550,
  "TATAMOTORS": 1425,
  "TATASTEEL": 5500,
  "TCS": 175,
  "TECHM": 600,
  "TITAN": 175,
  "ULTRACEMCO": 100,
  "WIPRO": 1500,
  "JIOFIN": 2000
};

export const getBaseQty = (sym: string): number => {
  const upperSym = sym.toUpperCase();
  for (const [key, value] of Object.entries(LOT_SIZES)) {
    if (upperSym.includes(key)) return value;
  }
  return 1;
};

function LiveTradingContent() {
  const searchParams = useSearchParams();
  const urlSymbol = searchParams.get('symbol') || 'SENSEX';
  const defaultBaseQty = getBaseQty(urlSymbol);

  const [strategy, setStrategy] = useState("institutional_momentum");
  const [timeframe, setTimeframe] = useState("5 Min");
  const [stoploss, setStoploss] = useState(1.0);
  const [tradingMode, setTradingMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('tradingMode');
      return saved || "paper"; // Default to paper (safer!)
    }
    return "paper";
  });
  const [equity, setEquity] = useState(100000.00);
  const [quantity, setQuantity] = useState(defaultBaseQty);
  const [inputMode, setInputMode] = useState<'lots' | 'qty'>('lots');
  const [tickerData, setTickerData] = useState({
    NIFTY: { lp: 23820.35, chp: -1.49 },
    SENSEX: { lp: 76015.28, chp: -1.70 },
    BANKNIFTY: { lp: 51000.00, chp: 0.0 }
  });
  const [pnl, setPnl] = useState(0.00);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [currentPrice, setCurrentPrice] = useState(0);
  const [changePercent, setChangePercent] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [aiConfidence, setAiConfidence] = useState(0);
  const [riskStatus, setRiskStatus] = useState("ACTIVE");
  const [isWsConnected, setIsWsConnected] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const prevTradesRef = useRef<Trade[]>([]);

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
          setStrategy(data.active_strategy || "institutional_momentum");
          if (data.stoploss !== undefined) {
            setStoploss(data.stoploss);
          }
          // Initialize from settings ONLY if it's a multiple of our baseQty (to avoid 65/20 = 3.25 lots)
          if (data.quantity && data.quantity % defaultBaseQty === 0) {
            setQuantity(data.quantity);
          }
        }
      } catch (error) {
        console.error("Failed to fetch settings:", error);
      }
    };
    fetchSettings();
  }, [defaultBaseQty]);

  // Reset to 1 Lot when the symbol changes
  useEffect(() => {
    setQuantity(defaultBaseQty);
  }, [urlSymbol, defaultBaseQty]);

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

  // Handle Stoploss Change
  const handleStoplossChange = async (val: string) => {
    // Prevent multiple leading zeros (e.g. '00.5' -> '0.5')
    let cleanVal = val.replace(/^0+(?=\d)/, '');
    
    // Update UI immediately for smooth typing
    setStoploss(cleanVal as any);
    
    const newSl = parseFloat(cleanVal);
    if (!isNaN(newSl)) {
      try {
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stoploss: newSl })
        });
      } catch (error) {
        console.error("Failed to update stoploss:", error);
      }
    }
  };

  // Handle Quantity Change
  const baseQty = getBaseQty(urlSymbol);
  const displayValue = quantity === 0 ? '' : (inputMode === 'lots' ? Number((quantity / baseQty).toFixed(2)) : quantity);

  const handleValueChange = (val: number) => {
    const newQty = inputMode === 'lots' ? val * baseQty : val;
    handleQuantityChange(newQty);
  };

  const handleQuantityChange = async (newQty: number) => {
    setQuantity(newQty);
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: newQty })
      });
    } catch (error) {
      console.error("Failed to update quantity:", error);
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
    let ws: WebSocket;
    let reconnectTimeout: NodeJS.Timeout;
    let reconnectDelay = 1000;
    const maxDelay = 10000;

    const connect = () => {
      ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/live`);
      
      ws.onopen = () => {
        console.log("WebSocket Connected");
        setIsWsConnected(true);
        reconnectDelay = 1000; // Reset delay on successful connection
      };
      
      ws.onclose = () => {
        console.log(`WebSocket Disconnected. Reconnecting in ${reconnectDelay}ms...`);
        setIsWsConnected(false);
        reconnectTimeout = setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, maxDelay); // Exponential backoff
      };
      
      ws.onerror = (err) => {
        // Use console.warn instead of console.error to prevent Next.js dev overlay popups when backend is offline
        console.warn("WebSocket Connection Error - Backend might be offline");
        ws.close(); // Force onclose to trigger reconnect
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
    };

    // Initial connection
    connect();
    
    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
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
            {/* Ticker Tape - Glassmorphism Marquee */}
            <div className="flex-1 flex items-center px-4 py-2 bg-muted/20 border border-border/50 rounded-xl overflow-hidden relative shadow-inner">
              <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none"></div>
              <div className="flex items-center gap-2 z-20 mr-4 border-r border-border/50 pr-4">
                {/* WS Connection Indicator */}
                <div className="relative flex items-center justify-center w-3 h-3 group">
                  {isWsConnected ? (
                    <>
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-success shadow-[0_0_8px_var(--success)]"></span>
                    </>
                  ) : (
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-destructive shadow-[0_0_8px_var(--destructive)]"></span>
                  )}
                  {/* Tooltip on hover */}
                  <div className="absolute -top-8 bg-black/80 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                    {isWsConnected ? "LIVE DATA FEED" : "DATA FEED OFFLINE"}
                  </div>
                </div>
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider hidden sm:inline-block">Indices</span>
              </div>

              {/* Marquee Content */}
              <div className="flex-1 overflow-hidden">
                <div className="flex items-center gap-8 animate-marquee whitespace-nowrap text-sm font-mono font-bold">
                  {/* NIFTY */}
                  <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                    <span className="text-foreground group-hover:text-primary transition-colors">NIFTY</span>
                    <span className={`transition-colors ${tickerData.NIFTY.chp >= 0 ? 'text-success drop-shadow-[0_0_4px_rgba(16,185,129,0.5)]' : 'text-destructive drop-shadow-[0_0_4px_rgba(239,68,68,0.5)]'}`}>
                      ₹{(tickerData.NIFTY.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${tickerData.NIFTY.chp >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                      {tickerData.NIFTY.chp >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {Math.abs(tickerData.NIFTY.chp).toFixed(2)}%
                    </span>
                  </div>
                  
                  {/* SENSEX */}
                  <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                    <span className="text-foreground group-hover:text-primary transition-colors">SENSEX</span>
                    <span className={`transition-colors ${tickerData.SENSEX.chp >= 0 ? 'text-success drop-shadow-[0_0_4px_rgba(16,185,129,0.5)]' : 'text-destructive drop-shadow-[0_0_4px_rgba(239,68,68,0.5)]'}`}>
                      ₹{(tickerData.SENSEX.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${tickerData.SENSEX.chp >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                      {tickerData.SENSEX.chp >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {Math.abs(tickerData.SENSEX.chp).toFixed(2)}%
                    </span>
                  </div>
                  
                  {/* BANKNIFTY */}
                  <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                    <span className="text-foreground group-hover:text-primary transition-colors">BANKNIFTY</span>
                    <span className={`transition-colors ${tickerData.BANKNIFTY.chp >= 0 ? 'text-success drop-shadow-[0_0_4px_rgba(16,185,129,0.5)]' : 'text-destructive drop-shadow-[0_0_4px_rgba(239,68,68,0.5)]'}`}>
                      ₹{(tickerData.BANKNIFTY.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${tickerData.BANKNIFTY.chp >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                      {tickerData.BANKNIFTY.chp >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {Math.abs(tickerData.BANKNIFTY.chp).toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
              <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none"></div>
            </div>
          </div>

          {/* Header & Controls Section */}
          <div className="flex flex-col gap-5 w-full">
            {/* Title Row & Toggle Switch */}
            <div className="flex justify-between items-start shrink-0 w-full">
              <div>
                <h1 className="font-display font-bold text-3xl text-foreground tracking-tight">Live Trading Terminal</h1>
                <p className="text-sm text-muted-foreground mt-1">Monitor real-time executions and account equity.</p>
              </div>

              {/* Premium Animated Toggle Switch */}
              <div className="flex items-center gap-3 bg-muted/20 px-4 py-2 rounded-xl border border-border/10 shadow-inner">
                <span className={`text-[10px] font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${tradingMode === 'live' ? 'text-primary drop-shadow-[0_0_8px_var(--glow-primary)]' : 'text-muted-foreground/40'}`}>
                  <Globe className="w-3.5 h-3.5" />
                  Live
                </span>
                
                <button
                  onClick={toggleTradingMode}
                  className={`relative w-12 h-6 rounded-full transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background ${tradingMode === 'live' ? 'bg-primary shadow-[0_0_12px_var(--glow-primary)]' : 'bg-primary/60 shadow-[0_0_12px_var(--glow-primary)]'}`}
                >
                  <motion.div 
                    className="absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow-md flex items-center justify-center"
                    animate={{ x: tradingMode === 'paper' ? 24 : 0 }}
                    transition={{ type: "spring", stiffness: 500, damping: 30 }}
                  >
                    <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white to-gray-200"></div>
                  </motion.div>
                </button>
                
                <span className={`text-[10px] font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${tradingMode === 'paper' ? 'text-primary drop-shadow-[0_0_8px_var(--glow-primary)]' : 'text-muted-foreground/40'}`}>
                  <Briefcase className="w-3.5 h-3.5" />
                  Paper
                </span>
              </div>
            </div>
            
            {/* Control Bar - Glass Container */}
            <div className="flex flex-wrap lg:flex-nowrap items-center gap-4 w-full bg-muted/5 p-3 border border-border/40 rounded-2xl shadow-sm backdrop-blur-sm overflow-x-auto hide-scrollbar">
              {/* Prominent Symbol, Price & Percentage Display */}
              <div className="flex items-center gap-3 px-4 py-2 bg-gradient-to-r from-muted/40 to-muted/10 border border-border/50 rounded-xl text-sm font-bold font-mono shadow-sm hover:shadow-[0_0_12px_rgba(var(--primary-rgb),0.1)] transition-shadow">
                <span className="text-primary bg-primary/10 px-2 py-0.5 rounded-md drop-shadow-[0_0_4px_rgba(var(--primary-rgb),0.5)]">{urlSymbol}</span>
                <span className="text-muted-foreground/30">|</span>
                <span className={`text-lg tracking-tight ${changePercent >= 0 ? 'text-success drop-shadow-[0_0_4px_rgba(16,185,129,0.5)]' : 'text-destructive drop-shadow-[0_0_4px_rgba(239,68,68,0.5)]'}`}>
                  ₹{(currentPrice ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[11px] ${changePercent >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                  {changePercent >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                  {Math.abs(changePercent).toFixed(2)}%
                </span>
              </div>

              {/* Strategy Selector */}
              <div className="relative group">
                <Layers className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2 group-focus-within:text-primary transition-colors pointer-events-none z-10" />
                <select 
                  value={strategy}
                  onChange={(e) => handleStrategyChange(e.target.value)}
                  className="select-field pl-10 pr-10 h-10 min-w-[200px] text-ellipsis overflow-hidden whitespace-nowrap appearance-none"
                >
                  <option value="ema_rsi">EMA + RSI (Classic)</option>
                  <option value="enhanced_ai">Enhanced AI Strategy</option>
                  <option value="institutional_ema">Institutional EMA</option>
                  <option value="advanced_ai">Advanced AI/ML</option>
                  <option value="premium">Premium Options Alpha</option>
                  <option value="institutional_momentum">Institutional Momentum</option>
                </select>
                <ChevronDown className="w-4 h-4 text-muted-foreground absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none z-10 group-focus-within:text-primary transition-colors" />
              </div>

              {/* Dynamic Lot/Qty Selector */}
              <div className="relative inline-flex items-center h-10 group rounded-xl">
                <span className="absolute -top-2.5 left-2 px-1 bg-background text-[10px] font-bold text-muted-foreground uppercase tracking-wider group-focus-within:text-primary transition-colors z-20">
                  {inputMode === 'lots' ? 'Lots' : 'Qty.'}
                </span>
                
                <input 
                  type="number"
                  min="0"
                  step="1"
                  value={displayValue}
                  onChange={(e) => handleValueChange(Number(e.target.value))}
                  className="input-field w-20 pl-3 pr-1 py-2 font-mono rounded-r-none h-full z-10"
                />
                
                <button 
                  onClick={() => setInputMode(prev => prev === 'lots' ? 'qty' : 'lots')}
                  className="flex items-center justify-center w-10 h-full border border-l-0 border-border bg-muted/20 hover:bg-muted/50 hover:text-primary transition-colors rounded-r-xl flex-shrink-0 z-10"
                  title={`Switch to ${inputMode === 'lots' ? 'Quantity' : 'Lots'}`}
                >
                  {inputMode === 'lots' ? <Package className="w-4 h-4" /> : <Layers className="w-4 h-4" />}
                </button>
              </div>

              {/* Stoploss Selector */}
              <div className="relative inline-flex items-center h-10 group rounded-xl">
                <span className="absolute -top-2.5 left-2 px-1 bg-background text-[10px] font-bold text-destructive/80 uppercase tracking-wider group-focus-within:text-destructive transition-colors z-20">
                  SL %
                </span>
                <input 
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={stoploss}
                  onChange={(e) => handleStoplossChange(e.target.value)}
                  className="input-field w-16 pl-3 pr-1 py-2 font-mono rounded-r-none h-full focus:!border-destructive focus:!ring-destructive/20 z-10"
                />
                <div className="flex items-center justify-center w-8 h-full border border-l-0 border-border bg-destructive/10 text-destructive rounded-r-xl text-xs font-bold z-10">
                  %
                </div>
              </div>
              
              {/* Timeframe Selector */}
              <div className="relative group">
                <Clock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2 group-focus-within:text-primary transition-colors pointer-events-none z-10" />
                <select 
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="select-field pl-10 pr-10 h-10 min-w-[110px] appearance-none"
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
                <ChevronDown className="w-4 h-4 text-muted-foreground absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none z-10 group-focus-within:text-primary transition-colors" />
              </div>

            </div>
          </div>

          {/* TradingView & Orders Row */}
          <motion.div 
            className="grid grid-cols-1 md:grid-cols-4 gap-6"
            initial="hidden"
            animate="show"
            variants={{
              hidden: { opacity: 0 },
              show: {
                opacity: 1,
                transition: { staggerChildren: 0.1 }
              }
            }}
          >
            {/* Card 1: Current Equity */}
            <motion.div 
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="stat-card p-6 relative overflow-hidden group"
            >
              <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-warning to-amber-600 rounded-l-lg group-hover:shadow-[0_0_12px_var(--warning)] transition-shadow"></div>
              <div className="flex items-center gap-2 mb-2 pl-2">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">💰 Current Equity</span>
              </div>
              <div className="text-3xl font-bold font-mono text-foreground pl-2 tracking-tight">
                {isLoading ? "---" : `₹${(equity || 100000.00).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </motion.div>
            
            {/* Card 2: Today's PNL */}
            <motion.div 
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="stat-card p-6 relative overflow-hidden group"
            >
              <div className={`absolute left-0 top-0 w-1 h-full rounded-l-lg transition-shadow ${pnl >= 0 ? 'bg-gradient-to-b from-success to-emerald-600 group-hover:shadow-[0_0_12px_var(--success)]' : 'bg-gradient-to-b from-destructive to-rose-600 group-hover:shadow-[0_0_12px_var(--destructive)]'}`}></div>
              <div className="flex items-center gap-2 mb-2 pl-2">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">📊 Today's PNL</span>
              </div>
              <div className={`text-3xl font-bold font-mono pl-2 tracking-tight flex items-center gap-2 ${pnl >= 0 ? "text-success" : "text-destructive"}`}>
                {pnl >= 0 ? <TrendingUp className="w-6 h-6 animate-pulse" /> : <TrendingDown className="w-6 h-6 animate-pulse" />}
                {isLoading ? "---" : `${pnl >= 0 ? "+" : ""}₹${(pnl ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
              </div>
            </motion.div>

            {/* Card 3: AI Confidence */}
            <motion.div 
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="stat-card p-6 flex items-center justify-between relative overflow-hidden"
            >
              <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-primary to-blue-600 rounded-l-lg"></div>
              <div className="space-y-1 pl-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">🤖 AI Confidence</span>
                </div>
                <div className={`text-sm font-bold uppercase tracking-wider ${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"}`}>
                  {aiConfidence >= 75 ? "High Conviction" : aiConfidence >= 50 ? "Mild Bias" : "Scan Mode"}
                </div>
                <div className="text-[10px] text-muted-foreground font-mono">
                  Based on {strategy.replace('_', ' ').toUpperCase()}
                </div>
              </div>
              
              {/* Smart Circle */}
              <div className="relative w-16 h-16 group">
                <svg className="w-full h-full transform -rotate-90 drop-shadow-md" viewBox="0 0 100 100">
                  <defs>
                    <linearGradient id="aiGradient" x1="0%" y1="100%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="var(--destructive)" />
                      <stop offset="50%" stopColor="var(--warning)" />
                      <stop offset="100%" stopColor="var(--success)" />
                    </linearGradient>
                  </defs>
                  {/* Background Circle */}
                  <circle
                    className="text-border stroke-current opacity-20"
                    strokeWidth="8"
                    cx="50"
                    cy="50"
                    r="42"
                    fill="transparent"
                  ></circle>
                  {/* Progress Circle */}
                  <circle
                    stroke="url(#aiGradient)"
                    strokeWidth="8"
                    strokeDasharray="263.89"
                    strokeDashoffset={263.89 - (263.89 * aiConfidence) / 100}
                    strokeLinecap="round"
                    cx="50"
                    cy="50"
                    r="42"
                    fill="transparent"
                    className="transition-all duration-1000 ease-out drop-shadow-[0_0_8px_var(--primary)]"
                  ></circle>
                </svg>
                {/* Number in center */}
                <div className={`absolute inset-0 flex items-center justify-center text-sm font-bold font-mono group-hover:scale-110 transition-transform ${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"}`}>
                  {isLoading ? "---" : `${aiConfidence.toFixed(0)}%`}
                </div>
              </div>
            </motion.div>

            {/* Card 4: Risk Engine */}
            <motion.div 
              variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
              className="stat-card p-6 relative overflow-hidden group"
            >
              <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-purple-500 to-indigo-600 rounded-l-lg group-hover:shadow-[0_0_12px_var(--primary)] transition-shadow"></div>
              <div className="flex items-center gap-2 mb-2 pl-2">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">🛡️ Risk Engine</span>
              </div>
              <div className="text-2xl font-bold font-mono text-success pl-2 flex items-center gap-3">
                ACTIVE
                <div className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-success"></span>
                </div>
              </div>
              <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider pl-2 mt-1">
                Limits OK &bull; SL {stoploss}%
              </div>
            </motion.div>
          </motion.div>

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
            <div className="glass-card rounded-xl p-6 border border-border/20 flex flex-col h-[530px]">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
                  <Zap className="w-5 h-5 text-warning" />
                  Live Execution Feed
                </h3>
                <span className="text-xs font-bold px-2 py-1 bg-muted/50 rounded-md text-muted-foreground">{trades.length} Trades</span>
              </div>
              
              <div className="flex-1 overflow-y-auto pr-2 space-y-3 custom-scrollbar">
                <AnimatePresence mode="popLayout">
                  {trades.length === 0 ? (
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
                    trades.map((trade, i) => (
                      <motion.div 
                        key={trade.id || i} 
                        initial={{ opacity: 0, x: -20, height: 0 }}
                        animate={{ opacity: 1, x: 0, height: 'auto' }}
                        exit={{ opacity: 0, x: 20, height: 0 }}
                        transition={{ type: "spring", stiffness: 500, damping: 30 }}
                        className={`flex items-center justify-between p-3 rounded-lg border-l-4 bg-muted/10 hover:bg-muted/30 transition-colors ${trade.side === "BUY" ? "border-l-success" : "border-l-destructive"}`}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg shadow-inner ${trade.side === "BUY" ? "bg-success/10 text-success shadow-[inset_0_0_8px_rgba(16,185,129,0.2)]" : "bg-destructive/10 text-destructive shadow-[inset_0_0_8px_rgba(239,68,68,0.2)]"}`}>
                            {trade.side === "BUY" ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-foreground">{trade.symbol}</p>
                            <p className="text-[10px] font-mono text-muted-foreground">{trade.time}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-mono font-bold text-foreground">₹{trade.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
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
          </div>
        </main>
      </div>

      {/* Live Notifications */}
      <div className="fixed top-20 right-6 z-50 space-y-3 pointer-events-none">
        <AnimatePresence>
          {notifications.map(n => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95, filter: "blur(4px)" }}
              transition={{ type: "spring", stiffness: 500, damping: 30 }}
              className={`p-4 rounded-xl shadow-2xl flex items-start gap-3 text-white font-medium backdrop-blur-md border ${
                n.type === 'success' ? 'bg-emerald-600/90 border-emerald-500/50 shadow-[0_4px_24px_rgba(16,185,129,0.3)]' :
                n.type === 'danger' ? 'bg-rose-600/90 border-rose-500/50 shadow-[0_4px_24px_rgba(244,63,94,0.3)]' :
                n.type === 'warning' ? 'bg-amber-600/90 border-amber-500/50 shadow-[0_4px_24px_rgba(245,158,11,0.3)]' : 'bg-blue-600/90 border-blue-500/50 shadow-[0_4px_24px_rgba(59,130,246,0.3)]'
              }`}
            >
              <div className="mt-0.5 opacity-90">
                {n.type === 'success' ? <TrendingUp className="w-5 h-5" /> :
                 n.type === 'danger' ? <TrendingDown className="w-5 h-5" /> :
                 n.type === 'warning' ? <Shield className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
              </div>
              <div className="flex-1">
                <p className="text-sm leading-tight drop-shadow-md">{n.message}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
