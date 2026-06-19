"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import NewsTicker from "@/components/news-ticker";
import { NumberInput } from "@/components/number-input";
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
  ChevronDown,
  Star,
  Brain,
  Package
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
  qty?: number;
}

interface Notification {
  id: number;
  message: string;
  type: 'success' | 'danger' | 'warning' | 'info';
}

import NativeChart from "@/components/native-chart";

function formatTradeDisplay(symbol: string, price: number, side: string, qty?: number) {
  // Parse options symbol like "NSE:NIFTY26DEC2424000CE"
  const match = symbol.match(/^(NSE|BSE):([A-Z0-9]+?)(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$/i);
  if (match) {
    const [_, exchange, inst, expiry, strike, optType] = match;
    const instName = inst.toUpperCase().startsWith('NIFTY') ? (inst.toUpperCase() === 'NIFTY' ? 'NIFTY50' : inst.toUpperCase()) : inst.toUpperCase();
    const exchName = exchange.toUpperCase() === 'NSE' ? 'NSC' : exchange.toUpperCase();
    
    // lot calculation
    // Since LOT_SIZES might not be hoisted, we can just safely search it manually or use the robust method
    const baseInst = inst.toUpperCase();
    let baseQty = 1;
    for (const [key, value] of Object.entries(LOT_SIZES)) {
      if (baseInst.includes(key)) {
        baseQty = value;
        break;
      }
    }
    const lotQty = qty ? Math.round(qty / baseQty) : 1;
    
    // User requested ultra-professional format: NSC: NIFTY50 26DEC24 ATM 24000 120 CE BUY (Lot Qty: xx)
    return `${exchName}: ${instName} ${expiry} ATM ${strike} ${price} ${optType} ${side} (Lot Qty: ${lotQty})`;
  }
  return `${symbol}`;
}

// Helper to check if Indian market is open
function isMarketOpen() {
  const now = new Date();
  const options = { timeZone: 'Asia/Kolkata', hour12: false, hour: 'numeric', minute: 'numeric', weekday: 'short' } as const;
  const formatter = new Intl.DateTimeFormat('en-US', options);
  const parts = formatter.formatToParts(now);
  
  const hourStr = parts.find(p => p.type === 'hour')?.value || '0';
  const minStr = parts.find(p => p.type === 'minute')?.value || '0';
  const weekday = parts.find(p => p.type === 'weekday')?.value || '';
  
  if (weekday === 'Sat' || weekday === 'Sun') return false;
  
  const hour = parseInt(hourStr, 10);
  const minute = parseInt(minStr, 10);
  
  const currentMins = hour * 60 + minute;
  return currentMins >= 555 && currentMins < 930; // 09:15 AM to 03:30 PM IST
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
  "BANKNIFTY": 15,
  "FINNIFTY": 40,
  "MIDCPNIFTY": 50,
  "SENSEX": 20,
  "AARTIIND": 1000,
  "ABB": 250,
  "ABBOTINDIA": 40,
  "ABCAPITAL": 5400,
  "ABFRL": 2600,
  "ACC": 300,
  "ADANIENT": 300,
  "ADANIPORTS": 400,
  "ALKEM": 200,
  "AMBUJACEM": 1800,
  "APOLLOHOSP": 125,
  "APOLLOTYRE": 1700,
  "ASHOKLEY": 5000,
  "ASIANPAINT": 200,
  "ASTRAL": 348,
  "ATUL": 75,
  "AUBANK": 1000,
  "AUROPHARMA": 1050,
  "AXISBANK": 625,
  "BAJAJ-AUTO": 125,
  "BAJAJFINSV": 500,
  "BAJFINANCE": 125,
  "BALKRISIND": 300,
  "BALRAMCHIN": 1600,
  "BANDHANBNK": 2500,
  "BANKBARODA": 5850,
  "BATAINDIA": 375,
  "BEL": 5700,
  "BERGEPAINT": 1100,
  "BHARATFORG": 500,
  "BHARTIARTL": 950,
  "BHEL": 5250,
  "BIOCON": 2500,
  "BOSCHLTD": 50,
  "BPCL": 1800,
  "BRITANNIA": 200,
  "BSOFT": 1000,
  "CANBK": 2700,
  "CANFINHOME": 975,
  "CHAMBLFERT": 1900,
  "CHOLAFIN": 1250,
  "CIPLA": 650,
  "COALINDIA": 2100,
  "COFORGE": 150,
  "COLPAL": 350,
  "CONCOR": 1000,
  "COROMANDEL": 700,
  "CROMPTON": 1800,
  "CUB": 5000,
  "CUMMINSIND": 300,
  "DABUR": 1250,
  "DALBHARAT": 250,
  "DEEPAKNTR": 300,
  "DIVISLAB": 200,
  "DIXON": 100,
  "DLF": 1650,
  "DRREDDY": 125,
  "EICHERMOT": 175,
  "ESCORTS": 275,
  "EXIDEIND": 3600,
  "FEDERALBNK": 5000,
  "GAIL": 4050,
  "GLENMARK": 700,
  "GMRINFRA": 11250,
  "GNFC": 1300,
  "GODREJCP": 500,
  "GODREJPROP": 175,
  "GRANULES": 2000,
  "GRASIM": 250,
  "GUJGASLTD": 1250,
  "HAL": 300,
  "HAVELLS": 500,
  "HCLTECH": 700,
  "HDFCAMC": 150,
  "HDFCBANK": 550,
  "HDFCLIFE": 1100,
  "HEROMOTOCO": 300,
  "HINDALCO": 1400,
  "HINDCOPPER": 4300,
  "HINDPETRO": 2700,
  "HINDUNILVR": 300,
  "ICICIBANK": 700,
  "ICICIGI": 500,
  "ICICIPRULI": 1500,
  "IDEA": 80000,
  "IDFC": 10000,
  "IDFCFIRSTB": 15000,
  "IEX": 3750,
  "IGL": 1375,
  "INDHOTEL": 2000,
  "INDIACEM": 2900,
  "INDIAMART": 150,
  "INDIGO": 300,
  "INDUSINDBK": 500,
  "INDUSTOWER": 3400,
  "INFY": 400,
  "IOC": 9750,
  "IPCALAB": 650,
  "IRCTC": 875,
  "ITC": 1600,
  "JINDALSTEL": 1250,
  "JKCEMENT": 250,
  "JSWSTEEL": 675,
  "JUBLFOOD": 1250,
  "KOTAKBANK": 400,
  "L&TFH": 4462,
  "LALPATHLAB": 250,
  "LAURUSLABS": 1700,
  "LICHSGFIN": 2000,
  "LT": 300,
  "LTIM": 150,
  "LTTS": 200,
  "LUPIN": 850,
  "M&M": 350,
  "M&MFIN": 2000,
  "MANAPPURAM": 3000,
  "MARICO": 1200,
  "MARUTI": 50,
  "MCDOWELL-N": 700,
  "MCX": 200,
  "METROPOLIS": 400,
  "MFSL": 800,
  "MGL": 800,
  "MOTHERSON": 7100,
  "MPHASIS": 275,
  "MRF": 10,
  "MUTHOOTFIN": 550,
  "NATIONALUM": 7500,
  "NAUKRI": 150,
  "NAVINFLUOR": 150,
  "NESTLEIND": 400,
  "NMDC": 4500,
  "NTPC": 3000,
  "OBEROIRLTY": 700,
  "OFSS": 100,
  "ONGC": 3850,
  "PAGEIND": 15,
  "PEL": 750,
  "PERSISTENT": 200,
  "PETRONET": 3000,
  "PFC": 3875,
  "PIDILITIND": 250,
  "PIIND": 250,
  "PNB": 8000,
  "POLYCAB": 100,
  "POWERGRID": 3600,
  "PVRINOX": 407,
  "RAMCOCEM": 850,
  "RBLBANK": 2500,
  "RECLTD": 2000,
  "RELIANCE": 250,
  "SAIL": 8000,
  "SBICARD": 800,
  "SBILIFE": 750,
  "SBIN": 750,
  "SHREECEM": 25,
  "SHRIRAMFIN": 300,
  "SIEMENS": 125,
  "SRF": 375,
  "SUNTV": 1500,
  "SUNPHARMA": 700,
  "SYNGENE": 1000,
  "TATACHEM": 550,
  "TATACOMM": 500,
  "TATACONSUM": 900,
  "TATAMOTORS": 1425,
  "TATAPOWER": 3375,
  "TATASTEEL": 5500,
  "TCS": 175,
  "TECHM": 600,
  "TITAN": 175,
  "TORNTPHARM": 500,
  "TRENT": 400,
  "TVSMOTOR": 700,
  "UBL": 400,
  "ULTRACEMCO": 100,
  "UPL": 1300,
  "VEDL": 3150,
  "VOLTAS": 600,
  "WIPRO": 1500,
  "ZEEL": 3000,
  "ZYDUSLIFE": 900,
};

export const getBaseQty = (sym: string): number => {
  const upperSym = sym.toUpperCase();
  for (const [key, value] of Object.entries(LOT_SIZES)) {
    if (upperSym.includes(key)) return value;
  }
  return 1;
};

const ALL_TIMEFRAMES = ["1 Min", "3 Min", "5 Min", "15 Min", "30 Min", "1 Hour", "1 Week", "1 Month"];

function LiveTradingContent() {
  const searchParams = useSearchParams();
  const urlSymbol = searchParams.get('symbol') || 'SENSEX';
  const defaultBaseQty = getBaseQty(urlSymbol);

  const [favoriteTimeframes, setFavoriteTimeframes] = useState<string[]>(['1 Min', '5 Min', '15 Min']);
  const [showAllTimeframes, setShowAllTimeframes] = useState(false);

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
  const [filters, setFilters] = useState({
    enable_squeeze_filter: false,
    enable_extension_filter: false,
    enable_cpr_filter: false,
    enable_aggression_filter: false
  });
  const prevTradesRef = useRef<Trade[]>([]);
  const isInitialFetch = useRef<boolean>(true);

  const addNotification = (message: string, type: 'success' | 'danger' | 'warning' | 'info') => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  };

  // Detect new trades and trigger notifications
  useEffect(() => {
    if (isInitialFetch.current && trades.length > 0) {
      isInitialFetch.current = false;
      prevTradesRef.current = trades;
      return;
    }

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

  // Deprecated: Advanced TradingView Widget is no longer used due to exchange restrictions.
  // We use our custom NativeChart component instead.

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
          setFilters({
            enable_squeeze_filter: data.enable_squeeze_filter || false,
            enable_extension_filter: data.enable_extension_filter || false,
            enable_cpr_filter: data.enable_cpr_filter || false,
            enable_aggression_filter: data.enable_aggression_filter || false
          });
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

  const handleFilterChange = async (key: string, value: boolean) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      });
    } catch (error) {
      console.error(`Error saving filter ${key}:`, error);
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
    let isMounted = true;
    let timeoutId: NodeJS.Timeout;

    const fetchState = async () => {
      try {
        const res = await fetch(`/api/state?symbol=${urlSymbol}&live=${tradingMode === 'live'}`, { cache: 'no-store' });
        if (!isMounted) return;
        const data = await res.json();
        
        setEquity(data.equity);
        setPnl(data.pnl);
        setTrades(data.trades || []);
        const parsedPrice = Number(data.currentPrice);
        // Optimization: If WebSocket is connected, let it handle live price updates.
        // If WebSocket is disconnected or price is 0 (initial load), update from polling!
        if (!isWsConnected || currentPrice === 0) {
          if (parsedPrice && parsedPrice !== 0) {
            setCurrentPrice(prev => (isMarketOpen() || prev === 0) ? parsedPrice : prev);
          }
          if (data.changePercent) {
            setChangePercent(prev => (isMarketOpen() || prev === 0) ? data.changePercent : prev);
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
        // Suppress "Failed to fetch" console.errors during background polling 
        // to prevent Next.js Dev Overlay from popping up during HMR or restarts
        if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            // Silently ignore transient network drops
        } else {
            console.warn("State polling issue:", error);
        }
        if (isMounted) setIsLoading(false); // Ensure loading stops on error
      } finally {
        if (isMounted) {
          timeoutId = setTimeout(fetchState, 1000); // Poll recursively every 1s
        }
      }
    };

    fetchState();
    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [urlSymbol]);

  // WebSocket for real-time price streaming (Institutional Fast Stream)
  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: NodeJS.Timeout;
    let reconnectDelay = 1000;
    const maxDelay = 10000;

    const connect = () => {
      const hostname = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
      ws = new WebSocket(`ws://${hostname}:8000/ws/live`);
      
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
      let lastWsUpdate = 0;
      ws.onmessage = (event) => {
        // Stop processing live ticks if market is closed (freezes price updates everywhere)
        if (!isMarketOpen()) return;

        const data = JSON.parse(event.data);
        if (data.NIFTY) {
          const now = Date.now();
          // Reduced throttle to 50ms to allow 100ms updates to pass through instantly for ultra-fast UI
          if (now - lastWsUpdate > 50) {
            lastWsUpdate = now;
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


  // Removed TradingView initialization

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
              <div className="relative group">
                <span className="absolute -top-2.5 left-2 px-1 bg-[#09090b] text-[10px] font-bold text-muted-foreground uppercase tracking-wider group-focus-within:text-primary transition-colors z-20">
                  {inputMode === 'lots' ? 'Lots' : 'Qty.'}
                </span>
                <NumberInput
                  value={displayValue}
                  onChange={(val) => handleValueChange(Number(val))}
                  min={0}
                  step={1}
                  containerClassName="w-24 h-10 rounded-xl"
                  appendContent={
                    <button 
                      onClick={() => setInputMode(prev => prev === 'lots' ? 'qty' : 'lots')}
                      className="flex items-center justify-center w-10 h-full border border-l-0 border-border bg-muted/20 hover:bg-muted/50 hover:text-primary transition-colors rounded-r-xl flex-shrink-0 z-10"
                      title={`Switch to ${inputMode === 'lots' ? 'Quantity' : 'Lots'}`}
                    >
                      {inputMode === 'lots' ? <Package className="w-4 h-4" /> : <Layers className="w-4 h-4" />}
                    </button>
                  }
                />
              </div>

              {/* Stoploss Selector */}
              <div className="relative group">
                <span className="absolute -top-2.5 left-2 px-1 bg-[#09090b] text-[10px] font-bold text-destructive/80 uppercase tracking-wider group-focus-within:text-destructive transition-colors z-20">
                  SL %
                </span>
                <NumberInput
                  value={stoploss}
                  onChange={(val) => handleStoplossChange(String(val))}
                  min={0.1}
                  step={0.1}
                  suffix="%"
                  ringColor="destructive"
                  containerClassName="w-24 h-10 rounded-xl"
                />
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

            {/* Institutional Filters Row */}
            <div className="flex flex-wrap items-center gap-6 px-4 py-3 bg-muted/5 border border-border/40 rounded-xl shadow-sm backdrop-blur-sm w-full">
              <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 border-r border-border/50 pr-4">
                <Shield className="w-3.5 h-3.5" />
                Institutional Filters:
              </div>
              
              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  id="squeeze_filter" 
                  checked={filters.enable_squeeze_filter}
                  onChange={(e) => handleFilterChange("enable_squeeze_filter", e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                />
                <label htmlFor="squeeze_filter" className={`text-xs font-medium cursor-pointer transition-colors ${filters.enable_squeeze_filter ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                  Squeeze Filter
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  id="extension_filter" 
                  checked={filters.enable_extension_filter}
                  onChange={(e) => handleFilterChange("enable_extension_filter", e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                />
                <label htmlFor="extension_filter" className={`text-xs font-medium cursor-pointer transition-colors ${filters.enable_extension_filter ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                  EMA Extension
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  id="cpr_filter" 
                  checked={filters.enable_cpr_filter}
                  onChange={(e) => handleFilterChange("enable_cpr_filter", e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                />
                <label htmlFor="cpr_filter" className={`text-xs font-medium cursor-pointer transition-colors ${filters.enable_cpr_filter ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                  CPR Rejection
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  id="aggression_filter" 
                  checked={filters.enable_aggression_filter}
                  onChange={(e) => handleFilterChange("enable_aggression_filter", e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                />
                <label htmlFor="aggression_filter" className={`text-xs font-medium cursor-pointer transition-colors ${filters.enable_aggression_filter ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                  Candle Aggression
                </label>
              </div>
            </div>
          </div>
          
          <div className="mb-4">
            <NewsTicker />
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
              className="stat-card p-4 flex flex-col justify-between relative overflow-hidden"
            >
              <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-primary to-blue-600 rounded-l-lg"></div>
              
              <div className="flex items-center justify-between w-full mb-3">
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
                <div className="relative w-14 h-14 group">
                  <svg className="absolute inset-0 w-full h-full drop-shadow-md" viewBox="0 0 100 100">
                    <defs>
                      <mask id="liveProgressMask">
                        <circle
                          cx="50" cy="50" r="42" fill="none"
                          stroke="#ffffff" strokeWidth="8"
                          strokeDasharray="263.89"
                          strokeDashoffset={263.89 - (263.89 * aiConfidence) / 100}
                          strokeLinecap="round" transform="rotate(-90 50 50)"
                          className="transition-all duration-1000 ease-out"
                        />
                      </mask>
                    </defs>
                    <circle cx="50" cy="50" r="42" fill="none" className="stroke-muted/30" strokeWidth="8" />
                    
                    <foreignObject x="0" y="0" width="100" height="100" mask="url(#liveProgressMask)">
                      <div className="w-full h-full" style={{ background: 'conic-gradient(var(--destructive) 0%, var(--warning) 50%, var(--success) 100%)' }}></div>
                    </foreignObject>
                  </svg>
                  <div className={`absolute inset-0 flex items-center justify-center text-xs font-bold font-mono group-hover:scale-110 transition-transform ${aiConfidence >= 75 ? "text-success" : aiConfidence >= 50 ? "text-warning" : "text-destructive"}`}>
                    {isLoading ? "---" : `${aiConfidence.toFixed(0)}%`}
                  </div>
                </div>
              </div>

              {/* Added Sub-metrics */}
              <div className="grid grid-cols-2 gap-2 pl-2 w-full text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                <div className="flex flex-col bg-muted/20 p-1.5 rounded-md text-center">
                  <span className="opacity-70 mb-0.5">Vol Sentiment</span>
                  <span className={`text-foreground ${riskStatus === "High Risk" ? "text-destructive" : "text-success"}`}>{riskStatus === "High Risk" ? "BEARISH" : "BULLISH"}</span>
                </div>
                <div className="flex flex-col bg-muted/20 p-1.5 rounded-md text-center">
                  <span className="opacity-70 mb-0.5">Trend Strength</span>
                  <span className={`text-foreground ${aiConfidence > 50 ? "text-success" : "text-destructive"}`}>{aiConfidence > 50 ? "STRONG" : "WEAK"}</span>
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
            {/* Native Custom Chart built with Lightweight-Charts */}
            <div className="lg:col-span-2 glass-card rounded-xl p-6 border border-border/20">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                <div>
                  <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse"></span>
                    Active Market Chart: {urlSymbol}
                  </h3>
                  <p className="text-xs text-muted-foreground">Native Institutional Candlestick Chart (Live Feed)</p>
                </div>

                {/* Timeframe Selector (TradingView Style) */}
                <div className="flex items-center bg-muted/30 rounded-lg p-1 border border-border/50 relative">
                  {/* Starred Timeframes */}
                  <div className="flex items-center">
                    {ALL_TIMEFRAMES.filter(tf => favoriteTimeframes.includes(tf) || tf === timeframe).map((tf) => (
                      <button
                        key={`fav-${tf}`}
                        onClick={() => setTimeframe(tf)}
                        className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${
                          timeframe === tf 
                            ? "bg-primary text-primary-foreground shadow-sm" 
                            : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                        }`}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>
                  
                  {/* Dropdown Toggle */}
                  <div className="relative border-l border-border/50 ml-1 pl-1">
                    <button
                      onClick={() => setShowAllTimeframes(!showAllTimeframes)}
                      className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors flex items-center justify-center"
                    >
                      <ChevronDown className="w-4 h-4" />
                    </button>
                    
                    {/* Dropdown Menu */}
                    <AnimatePresence>
                      {showAllTimeframes && (
                        <motion.div
                          initial={{ opacity: 0, y: 10, scale: 0.95 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: 10, scale: 0.95 }}
                          transition={{ duration: 0.15 }}
                          className="absolute right-0 top-full mt-2 w-48 bg-card border border-border/50 rounded-xl shadow-2xl overflow-hidden z-50 backdrop-blur-2xl"
                        >
                          <div className="p-2 space-y-1">
                            {ALL_TIMEFRAMES.map((tf) => (
                              <div key={`all-${tf}`} className="flex items-center justify-between group">
                                <button
                                  onClick={() => { setTimeframe(tf); setShowAllTimeframes(false); }}
                                  className={`flex-1 text-left px-3 py-2 text-sm rounded-lg transition-colors ${
                                    timeframe === tf ? "bg-primary/20 text-primary font-bold" : "text-foreground hover:bg-muted/80"
                                  }`}
                                >
                                  {tf}
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (favoriteTimeframes.includes(tf)) {
                                      setFavoriteTimeframes(prev => prev.filter(t => t !== tf));
                                    } else {
                                      setFavoriteTimeframes(prev => [...prev, tf]);
                                    }
                                  }}
                                  className="p-2 opacity-50 group-hover:opacity-100 hover:text-warning transition-all"
                                >
                                  <Star className={`w-4 h-4 ${favoriteTimeframes.includes(tf) ? "fill-warning text-warning" : ""}`} />
                                </button>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </div>

              {/* Container for Native Chart */}
              <div 
                key={`${urlSymbol}-${timeframe}`}
                className="w-full rounded-lg overflow-hidden border border-border/10 bg-[#090a0f]" 
              >
                <NativeChart symbol={urlSymbol} livePrice={currentPrice} timeframe={timeframe} />
              </div>
            </div>

            {/* Right Column: Execution Feed */}
            <div className="flex flex-col gap-6 h-[530px]">
              {/* Execution Feed */}
              <div className="glass-card rounded-xl p-6 border border-border/20 flex flex-col flex-1 h-full min-h-0">
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
                        animate={{ 
                          opacity: 1, 
                          x: 0, 
                          height: 'auto',
                          backgroundColor: trade.side === "BUY" 
                            ? ['rgba(16, 185, 129, 0.2)', 'rgba(16, 185, 129, 0)'] 
                            : ['rgba(239, 68, 68, 0.2)', 'rgba(239, 68, 68, 0)']
                        }}
                        exit={{ opacity: 0, x: 20, height: 0 }}
                        transition={{ 
                          type: "spring", stiffness: 500, damping: 30,
                          backgroundColor: { duration: 1.5, ease: "easeOut" }
                        }}
                        className={`flex items-center justify-between p-3 rounded-lg border-l-4 bg-muted/10 hover:bg-muted/30 transition-colors ${trade.side === "BUY" ? "border-l-success" : "border-l-destructive"}`}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg shadow-inner ${trade.side === "BUY" ? "bg-success/10 text-success shadow-[inset_0_0_8px_rgba(16,185,129,0.2)]" : "bg-destructive/10 text-destructive shadow-[inset_0_0_8px_rgba(239,68,68,0.2)]"}`}>
                            {trade.side === "BUY" ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-foreground tracking-tight">{formatTradeDisplay(trade.symbol, trade.price, trade.side, trade.qty)}</p>
                            <p className="text-[10px] font-mono tabular-nums text-muted-foreground">{trade.time}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-mono tabular-nums font-bold text-foreground">₹{trade.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
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
