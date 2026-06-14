"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import CustomDatePicker from "@/components/custom-date-picker";
import { useState, useRef, useEffect } from "react";
import { 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  Zap, 
  Shield, 
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Search,
  Filter,
  RefreshCw,
  BarChart2,
  Calendar,
  Layers,
  Globe,
  Briefcase,
  Database,
  Package
} from "lucide-react";
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  ReferenceLine
} from "recharts";

// Institutional Level Asset Database for Autocomplete
const INDIAN_MARKET_ASSETS = [
  { symbol: "NIFTY", name: "NIFTY 50", type: "Index" },
  { symbol: "SENSEX", name: "S&P BSE SENSEX", type: "Index" },
  { symbol: "BANKNIFTY", name: "NIFTY Bank", type: "Index" },
  { symbol: "FINNIFTY", name: "NIFTY Financial Services", type: "Index" },
  { symbol: "RELIANCE", name: "Reliance Industries Ltd.", type: "Stock" },
  { symbol: "ADANIENT", name: "Adani Enterprises Ltd.", type: "Stock" },
  { symbol: "ADANIPORTS", name: "Adani Ports and SEZ Ltd.", type: "Stock" },
  { symbol: "APOLLOHOSP", name: "Apollo Hospitals Enterprise Ltd.", type: "Stock" },
  { symbol: "ASIANPAINT", name: "Asian Paints Ltd.", type: "Stock" },
  { symbol: "AXISBANK", name: "Axis Bank Ltd.", type: "Stock" },
  { symbol: "BAJAJ-AUTO", name: "Bajaj Auto Ltd.", type: "Stock" },
  { symbol: "BAJAJFINSV", name: "Bajaj Finserv Ltd.", type: "Stock" },
  { symbol: "BAJFINANCE", name: "Bajaj Finance Ltd.", type: "Stock" },
  { symbol: "BHARTIARTL", name: "Bharti Airtel Ltd.", type: "Stock" },
  { symbol: "BPCL", name: "Bharat Petroleum Corp. Ltd.", type: "Stock" },
  { symbol: "BRITANNIA", name: "Britannia Industries Ltd.", type: "Stock" },
  { symbol: "CIPLA", name: "Cipla Ltd.", type: "Stock" },
  { symbol: "COALINDIA", name: "Coal India Ltd.", type: "Stock" },
  { symbol: "DIVISLAB", name: "Divi's Laboratories Ltd.", type: "Stock" },
  { symbol: "DRREDDY", name: "Dr. Reddy's Laboratories Ltd.", type: "Stock" },
  { symbol: "EICHERMOT", name: "Eicher Motors Ltd.", type: "Stock" },
  { symbol: "GRASIM", name: "Grasim Industries Ltd.", type: "Stock" },
  { symbol: "HCLTECH", name: "HCL Technologies Ltd.", type: "Stock" },
  { symbol: "HDFCBANK", name: "HDFC Bank Ltd.", type: "Stock" },
  { symbol: "HDFCLIFE", name: "HDFC Life Insurance Co. Ltd.", type: "Stock" },
  { symbol: "HEROMOTOCO", name: "Hero MotoCorp Ltd.", type: "Stock" },
  { symbol: "HINDALCO", name: "Hindalco Industries Ltd.", type: "Stock" },
  { symbol: "HINDUNILVR", name: "Hindustan Unilever Ltd.", type: "Stock" },
  { symbol: "ICICIBANK", name: "ICICI Bank Ltd.", type: "Stock" },
  { symbol: "INDUSINDBK", name: "IndusInd Bank Ltd.", type: "Stock" },
  { symbol: "INFY", name: "Infosys Ltd.", type: "Stock" },
  { symbol: "ITC", name: "ITC Ltd.", type: "Stock" },
  { symbol: "JSWSTEEL", name: "JSW Steel Ltd.", type: "Stock" },
  { symbol: "KOTAKBANK", name: "Kotak Mahindra Bank Ltd.", type: "Stock" },
  { symbol: "LT", name: "Larsen & Toubro Ltd.", type: "Stock" },
  { symbol: "LTIM", name: "LTIMindtree Ltd.", type: "Stock" },
  { symbol: "M&M", name: "Mahindra & Mahindra Ltd.", type: "Stock" },
  { symbol: "MARUTI", name: "Maruti Suzuki India Ltd.", type: "Stock" },
  { symbol: "NESTLEIND", name: "Nestle India Ltd.", type: "Stock" },
  { symbol: "NTPC", name: "NTPC Ltd.", type: "Stock" },
  { symbol: "ONGC", name: "Oil & Natural Gas Corp. Ltd.", type: "Stock" },
  { symbol: "POWERGRID", name: "Power Grid Corp. of India Ltd.", type: "Stock" },
  { symbol: "SBILIFE", name: "SBI Life Insurance Co. Ltd.", type: "Stock" },
  { symbol: "SBIN", name: "State Bank of India", type: "Stock" },
  { symbol: "SUNPHARMA", name: "Sun Pharmaceutical Industries Ltd.", type: "Stock" },
  { symbol: "TATACONSUM", name: "Tata Consumer Products Ltd.", type: "Stock" },
  { symbol: "TATAMOTORS", name: "Tata Motors Ltd.", type: "Stock" },
  { symbol: "TATASTEEL", name: "Tata Steel Ltd.", type: "Stock" },
  { symbol: "TCS", name: "Tata Consultancy Services Ltd.", type: "Stock" },
  { symbol: "TECHM", name: "Tech Mahindra Ltd.", type: "Stock" },
  { symbol: "TITAN", name: "Titan Company Ltd.", type: "Stock" },
  { symbol: "ULTRACEMCO", name: "UltraTech Cement Ltd.", type: "Stock" },
  { symbol: "WIPRO", name: "Wipro Ltd.", type: "Stock" },
  { symbol: "JIOFIN", name: "Jio Financial Services Ltd.", type: "Stock" },
];

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

export default function Backtest() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [selectedAssetName, setSelectedAssetName] = useState("NIFTY 50");
  const [timeframe, setTimeframe] = useState("1 Min");
  const [strategy, setStrategy] = useState("ema_rsi");
  const [startDate, setStartDate] = useState("2025-05-16");
  const [endDate, setEndDate] = useState("2026-05-16");
  const [datePreset, setDatePreset] = useState("all_data");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [quantity, setQuantity] = useState<number | string>(65);
  const [stoplossPct, setStoplossPct] = useState<number | string>(1.2);
  const [targetPct, setTargetPct] = useState<number | string>(2.5);
  const [donchianPeriod, setDonchianPeriod] = useState<number | string>(10);
  const [trailingSl, setTrailingSl] = useState(true);
  const [inputMode, setInputMode] = useState<'lots' | 'qty'>('lots');
  const [trailTrigger, setTrailTrigger] = useState<number | string>(0.8);
  const [trailOffset, setTrailOffset] = useState<number | string>(0.2);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  
  // Institutional Strategy Filters
  const [enableEmaFilter, setEnableEmaFilter] = useState(true);
  const [enableVolumeFilter, setEnableVolumeFilter] = useState(true);
  const [enableAdxFilter, setEnableAdxFilter] = useState(true);
  const [enableVwapFilter, setEnableVwapFilter] = useState(true);
  const [enableRsiFilter, setEnableRsiFilter] = useState(true);

  // Search Autocomplete State
  const [searchQuery, setSearchQuery] = useState("NIFTY");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const searchRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Close suggestions on outside click
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    if (query.length > 0) {
      const filtered = INDIAN_MARKET_ASSETS.filter(asset => 
        asset.symbol.toLowerCase().includes(query.toLowerCase()) || 
        asset.name.toLowerCase().includes(query.toLowerCase())
      );
      setSuggestions(filtered);
      setShowSuggestions(true);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  const selectAsset = (asset: any) => {
    setSymbol(asset.symbol);
    setSearchQuery(asset.symbol);
    setSelectedAssetName(asset.name);
    setShowSuggestions(false);
  };

  // ADVANCED: Allow Enter key to search/lock any symbol!
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim() !== '') {
      const sym = searchQuery.trim().toUpperCase();
      const asset = INDIAN_MARKET_ASSETS.find(a => a.symbol === sym);
      
      if (asset) {
        selectAsset(asset);
      } else {
        // Fallback for custom symbol
        setSymbol(sym);
        setSearchQuery(sym);
        setSelectedAssetName(sym);
        setShowSuggestions(false);
      }
    }
  };

  // Auto-update quantity based on symbol selection
  useEffect(() => {
    setQuantity(getBaseQty(symbol));
  }, [symbol]);

  const baseQty = getBaseQty(symbol);
  const numericQuantity = Number(quantity);
  const displayValue = numericQuantity === 0 ? '' : (inputMode === 'lots' ? Number((numericQuantity / baseQty).toFixed(2)) : numericQuantity);

  const handleValueChange = (val: number) => {
    const newQty = inputMode === 'lots' ? val * baseQty : val;
    setQuantity(newQty);
  };

  const handlePresetChange = (preset: string) => {
    setDatePreset(preset);
    
    if (preset === "custom") return; // Do not overwrite user dates when clicking custom
    
    // Calculate dates dynamically based on current date
    const today = new Date();
    const endDateStr = today.toISOString().split('T')[0];
    setEndDate(endDateStr);
    
    if (preset === "today") {
      setStartDate(endDateStr);
    } else if (preset === "last_3_days") {
      const start = new Date(today);
      start.setDate(today.getDate() - 2);
      setStartDate(start.toISOString().split('T')[0]);
    } else if (preset === "all_data") {
      // Set to 1 year ago (365 days) for maximum robust backtesting
      const start = new Date(today);
      start.setDate(today.getDate() - 365);
      setStartDate(start.toISOString().split('T')[0]);
    }
  };

  // PERSISTENCE: Check if a backtest was running or had a result before refresh
  useEffect(() => {
    const wasRunning = localStorage.getItem("backtest_running") === "true";
    const lastResult = localStorage.getItem("backtest_last_result");
    const savedParams = JSON.parse(localStorage.getItem("backtest_params") || "{}");

    if (savedParams.symbol) {
      setSymbol(savedParams.symbol);
      setTimeframe(savedParams.timeframe);
      setStrategy(savedParams.strategy);
      setStartDate(savedParams.startDate);
      setEndDate(savedParams.endDate);
      setInitialCapital(savedParams.initialCapital);
      setQuantity(savedParams.quantity || 65);
      setStoplossPct(savedParams.stoploss_pct || 1.2);
      setTargetPct(savedParams.target_pct || 2.5);
      setDonchianPeriod(savedParams.donchian_period || 10);
      setTrailingSl(savedParams.trailing_sl !== undefined ? savedParams.trailing_sl : true);
      setTrailTrigger(savedParams.trail_trigger || 0.8);
      setTrailOffset(savedParams.trail_offset || 0.2);
      setSearchQuery(savedParams.symbol);
      
      if (wasRunning) {
        // Auto-run restored session if it was still loading
        setTimeout(() => runBacktestInternal(savedParams), 500);
      } else if (lastResult) {
        // Restore last result immediately
        setResult(JSON.parse(lastResult));
      }
    }

    // Cleanup: Stop "running" state if navigating away from this component
    return () => {
      localStorage.removeItem("backtest_running");
      localStorage.removeItem("backtest_last_result");
      localStorage.removeItem("backtest_params");
    };
  }, []);

  const runBacktest = () => {
    const params = { 
      symbol, timeframe, strategy, startDate, endDate, initialCapital, 
      quantity: quantity || 65,
      stoploss_pct: stoplossPct || 1.2, target_pct: targetPct || 2.5,
      enableEmaFilter, enableVolumeFilter, enableAdxFilter, enableVwapFilter, enableRsiFilter,
      donchian_period: donchianPeriod || 10,
      trailing_sl: trailingSl,
      trail_trigger: trailTrigger || 0.8,
      trail_offset: trailOffset || 0.2
    };
    localStorage.setItem("backtest_running", "true");
    localStorage.setItem("backtest_params", JSON.stringify(params));
    runBacktestInternal(params);
  };

  const runBacktestInternal = async (params: any) => {
    setIsLoading(true);
    setResult(null);
    setError("");
    
    try {
      const queryParams = new URLSearchParams({
        symbol: params.symbol,
        timeframe: params.timeframe,
        strategy: params.strategy,
        startDate: params.startDate,
        endDate: params.endDate,
        initialCapital: params.initialCapital,
        quantity: params.quantity.toString(),
        stoploss_pct: params.stoploss_pct.toString(),
        target_pct: params.target_pct.toString(),
        enable_ema_filter: params.enableEmaFilter.toString(),
        enable_volume_filter: params.enableVolumeFilter.toString(),
        enable_adx_filter: params.enableAdxFilter.toString(),
        enable_vwap_filter: params.enableVwapFilter.toString(),
        enable_rsi_filter: params.enableRsiFilter.toString(),
        donchian_period: (params.donchian_period || 10).toString(),
        trailing_sl: params.trailing_sl.toString(),
        trail_trigger: params.trail_trigger.toString(),
        trail_offset: params.trail_offset.toString()
      });

      const res = await fetch(`/api/backtest?${queryParams.toString()}`, { cache: 'no-store' });
      const data = await res.json();
      
      if (data.error) {
        setError(data.error);
        localStorage.removeItem("backtest_running");
      } else {
        setResult(data);
        localStorage.setItem("backtest_last_result", JSON.stringify(data));
      }
    } catch (error) {
      console.error("Failed to run backtest:", error);
      setError("Failed to connect to the backtesting engine.");
      localStorage.removeItem("backtest_running");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground">Backtesting Engine</h1>
              <p className="text-sm text-muted-foreground">Historical simulation terminal connected to active strategy files.</p>
            </div>
            <div className="px-4 py-2 bg-muted/30 border border-border/50 rounded-lg">
              <span className="text-xs text-muted-foreground block font-medium">Selected Asset</span>
              <span className="text-sm font-bold text-primary">{selectedAssetName} ({symbol})</span>
            </div>
          </div>

          {/* Institutional Level Controls / Search Options */}
          <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
            <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
              <Globe className="w-4 h-4 text-primary" />
              Institutional Asset Search
            </h3>
            
            {/* Dynamic grid columns based on visibility of date pickers */}
            <div className={`grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-4 items-end transition-all`}>
              {/* Institutional Level Search Box */}
              <div className="relative" ref={searchRef}>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Search Stocks & Indices</label>
                <div className="relative">
                  <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => handleSearchChange(e.target.value)}
                    onFocus={() => searchQuery && handleSearchChange(searchQuery)}
                    onKeyDown={handleKeyDown}
                    placeholder="Search NIFTY, Reliance..."
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-4 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                {/* Autocomplete Suggestions */}
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute z-50 mt-2 w-full max-h-60 bg-background border border-border/50 rounded-lg shadow-xl overflow-y-auto backdrop-blur-xl">
                    {suggestions.map((asset) => (
                      <button
                        key={asset.symbol}
                        onClick={() => selectAsset(asset)}
                        className="w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors flex justify-between items-center"
                      >
                        <div>
                          <span className="font-bold text-foreground">{asset.symbol}</span>
                          <span className="text-xs text-muted-foreground ml-2">{asset.name}</span>
                        </div>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${asset.type === 'Index' ? 'bg-primary/20 text-primary' : 'bg-success/20 text-success'}`}>
                          {asset.type}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Initial Capital</label>
                <div className="relative">
                  <Briefcase className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                  <select 
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none"
                    style={{ background: 'var(--card)', color: 'var(--foreground)' }}
                  >
                    <option value="10000">₹ 10,000</option>
                    <option value="25000">₹ 25,000</option>
                    <option value="50000">₹ 50,000</option>
                    <option value="100000">₹ 1,00,000</option>
                    <option value="500000">₹ 5,00,000</option>
                    <option value="1000000">₹ 10,00,000</option>
                  </select>
                </div>
              </div>

              {/* Dynamic Lot/Qty Selector */}
              <div className="pt-2">
                <div className="relative inline-flex items-center border border-border/50 rounded-lg bg-muted/30 h-10 w-full group focus-within:ring-1 focus-within:ring-primary focus-within:border-primary transition-all">
                  <span className="absolute -top-2.5 left-2 px-1 bg-background text-[10px] font-bold text-muted-foreground uppercase tracking-wider group-focus-within:text-primary transition-colors z-10">
                    {inputMode === 'lots' ? 'Lots' : 'Qty.'}
                  </span>
                  
                  <input 
                    type="number"
                    min="0"
                    step="1"
                    value={displayValue}
                    onChange={(e) => handleValueChange(Number(e.target.value))}
                    className="w-20 pl-3 pr-1 py-2 bg-transparent text-foreground text-sm font-bold font-mono focus:outline-none"
                  />
                  
                  <button 
                    onClick={() => setInputMode(prev => prev === 'lots' ? 'qty' : 'lots')}
                    className="flex items-center justify-center w-10 h-full border-l border-border/50 hover:bg-muted/50 transition-colors rounded-r-lg flex-shrink-0 bg-muted/20"
                    title={`Switch to ${inputMode === 'lots' ? 'Quantity' : 'Lots'}`}
                  >
                    {inputMode === 'lots' ? <Package className="w-4 h-4 text-muted-foreground" /> : <Layers className="w-4 h-4 text-muted-foreground" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5 font-mono">Target %</label>
                <div className="relative">
                  <input 
                    type="number" step="0.1" min="0.1" max="100"
                    value={targetPct}
                    onChange={(e) => setTargetPct(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-3 pr-8 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                  />
                  <span className="absolute right-3 top-1/2 transform -translate-y-1/2 text-xs font-bold text-primary font-mono">%</span>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5 font-mono">Stoploss %</label>
                <div className="relative">
                  <input 
                    type="number" step="0.1" min="0.1" max="50"
                    value={stoplossPct}
                    onChange={(e) => setStoplossPct(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-3 pr-8 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-warning font-mono"
                  />
                  <span className="absolute right-3 top-1/2 transform -translate-y-1/2 text-xs font-bold text-warning font-mono">%</span>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5 font-mono">Donchian Period</label>
                <div className="relative">
                  <input 
                    type="number" step="1" min="1" max="250"
                    value={donchianPeriod}
                    onChange={(e) => setDonchianPeriod(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-3 pr-14 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                  />
                  <span className="absolute right-3 top-1/2 transform -translate-y-1/2 text-xs font-bold text-muted-foreground font-mono">bars</span>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Strategy</label>
                <div className="relative">
                  <Layers className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                  <select 
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    style={{ background: 'var(--card)', color: 'var(--foreground)' }}
                  >
                    <option value="ema_rsi">EMA + RSI (Classic)</option>
                    <option value="enhanced_ai">Enhanced AI Strategy</option>
                    <option value="institutional_ema">Institutional EMA</option>
                    <option value="advanced_ai">Advanced AI/ML</option>
                    <option value="premium">Premium Options Alpha</option>
                    <option value="institutional_momentum">Institutional Momentum</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Timeframe</label>
                <select 
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  style={{ background: 'var(--card)', color: 'var(--foreground)' }}
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

              {/* Advanced Date Selection */}
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Quick Date Select</label>
                <div className="relative">
                  <Calendar className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                  <select 
                    value={datePreset}
                    onChange={(e) => handlePresetChange(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    style={{ background: 'var(--card)', color: 'var(--foreground)' }}
                  >
                    <option value="custom">Custom Date Range</option>
                    <option value="today">Today (Last Data Day)</option>
                    <option value="last_3_days">Last 3 Days</option>
                    <option value="all_data">All Available Data</option>
                  </select>
                </div>
              </div>

              {/* Hide start and end date calendars unless 'Custom Range' is selected */}
              {datePreset === "custom" && (
                <>
                  <CustomDatePicker
                    label="Start Date"
                    value={startDate}
                    onChange={(date) => { setStartDate(date); setDatePreset("custom"); }}
                  />

                  <CustomDatePicker
                    label="End Date"
                    value={endDate}
                    onChange={(date) => { setEndDate(date); setDatePreset("custom"); }}
                  />
                </>
              )}

              <div className="md:col-span-4 lg:col-span-3 flex justify-end items-center gap-6 h-10">
                <label className="flex items-center gap-2 cursor-pointer group whitespace-nowrap">
                  <input 
                    type="checkbox" checked={trailingSl} 
                    onChange={(e) => setTrailingSl(e.target.checked)}
                    className="w-4 h-4 rounded border-border bg-muted/30 text-primary focus:ring-primary"
                  />
                  <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">Enable Trailing SL</span>
                </label>

                <button 
                  onClick={runBacktest}
                  disabled={isLoading}
                  className="px-8 h-10 bg-gradient-to-r from-primary to-primary/80 text-primary-foreground hover:from-primary/90 hover:to-primary/70 rounded-lg text-sm font-bold transition-all duration-200 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98]"
                >
                  {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {isLoading ? "Running Simulation..." : "Run Full Backtest"}
                </button>
              </div>
              </div>
            </div>

          {error && (
            <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-sm flex items-center gap-2">
              <Shield className="w-4 h-4" />
              {error}
            </div>
          )}

          {isLoading && (
            <div className="h-[400px] flex flex-col items-center justify-center gap-4 glass-card rounded-xl border border-border/20">
              <RefreshCw className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Running historical simulation. Crunching candles for {symbol}...</p>
            </div>
          )}

          {!isLoading && !result && !error && (
            <div className="h-[400px] flex flex-col items-center justify-center gap-2 glass-card rounded-xl border border-border/20">
              <BarChart2 className="w-8 h-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Adjust your parameters and click "Run Full Backtest" to see results.</p>
            </div>
          )}

          {result && (
            <div className="space-y-6">
              {/* Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {/* Row 1: Core Performance */}
                <div className="glass-card rounded-xl p-4 border border-border/20 transition-all duration-200 hover:border-primary/30 hover:shadow-md">
                  <span className="text-xs text-muted-foreground font-medium">Net Profit</span>
                  <div className={`text-2xl font-bold font-mono mt-1 ${result.stats.netProfit >= 0 ? "text-success" : "text-destructive"}`}>
                    {result.stats.netProfit >= 0 ? "+" : ""}₹{result.stats.netProfit.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                  </div>
                </div>
                
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Profit Factor</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-foreground">{result.stats.profitFactor}</div>
                  <p className="text-xs text-muted-foreground mt-1">{result.stats.profitFactor >= 1 ? "Profitable" : "Unprofitable"}</p>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Win Rate</span>
                  <div className={`text-2xl font-bold font-mono mt-1 ${result.stats.winRate > 0 ? 'text-success' : result.stats.winRate < 0 ? 'text-destructive' : 'text-foreground'}`}>{result.stats.winRate}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Max Drawdown</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-destructive">{result.stats.maxDrawdown}%</div>
                </div>

                {/* Row 2: Execution Stats */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Total Trades</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-foreground">{result.stats.totalTrades}</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Success Trades</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-success">
                    {result.stats.successTrades !== undefined ? result.stats.successTrades : 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Profitable Executions</p>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Failed Trades</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-destructive">
                    {result.stats.failedTrades !== undefined ? result.stats.failedTrades : 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Unprofitable Executions</p>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Stoploss Triggered</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-warning">
                    {result.stats.stoplossTrades !== undefined ? result.stats.stoplossTrades : 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Exited via Stoploss</p>
                </div>

                {/* Row 3: Option Types & Risk */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">CE Trades (Calls)</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-success">{result.stats.totalCE || 0}</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">PE Trades (Puts)</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-destructive">{result.stats.totalPE || 0}</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Sharpe Ratio</span>
                  <div className={`text-2xl font-bold font-mono mt-1 ${typeof result.stats.sharpeRatio === 'number' ? (result.stats.sharpeRatio > 0 ? 'text-success' : result.stats.sharpeRatio < 0 ? 'text-destructive' : 'text-foreground') : 'text-foreground'}`}>
                    {result.stats.sharpeRatio !== undefined ? result.stats.sharpeRatio : "N/A"}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Risk-Adjusted Return</p>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Sortino Ratio</span>
                  <div className={`text-2xl font-bold font-mono mt-1 ${typeof result.stats.sortinoRatio === 'number' ? (result.stats.sortinoRatio > 0 ? 'text-success' : result.stats.sortinoRatio < 0 ? 'text-destructive' : 'text-foreground') : 'text-foreground'}`}>
                    {result.stats.sortinoRatio !== undefined ? result.stats.sortinoRatio : "N/A"}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Downside Risk Return</p>
                </div>

                {/* Row 4: Strategy Configuration */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Expectancy</span>
                  <div className={`text-2xl font-bold font-mono mt-1 ${result.stats.expectancy >= 0 ? "text-success" : "text-destructive"}`}>
                    {result.stats.expectancy >= 0 ? "+" : ""}₹{result.stats.expectancy !== undefined ? result.stats.expectancy : 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Avg PnL per Trade</p>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Target %</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-success">{result.stats.targetPct}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Stoploss %</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-warning">{result.stats.stoplossPct}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Donchian Period</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-foreground">
                    {result.stats.donchianPeriod !== undefined ? result.stats.donchianPeriod : donchianPeriod} bars
                  </div>
                </div>
              </div>

              {/* Chart */}
              <div className="glass-card rounded-xl p-6 border border-border/20">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <h3 className="font-display font-bold text-lg text-foreground">Backtest Equity Curve</h3>
                    <p className="text-xs text-muted-foreground">Simulation for {selectedAssetName} on {result.timeframe} chart</p>
                  </div>
                </div>

                <div className="h-[350px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={result.equityCurve}>
                        <defs>
                          <linearGradient id="backtestColor" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={result.stats.netProfit >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0.2}/>
                            <stop offset="95%" stopColor={result.stats.netProfit >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={11} tick={{ fill: 'hsl(var(--muted-foreground))' }} />
                        <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} domain={['dataMin - 1000', 'dataMax + 1000']} tick={{ fill: 'hsl(var(--muted-foreground))' }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                          labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 'bold' }}
                          itemStyle={{ color: 'hsl(var(--foreground))' }}
                        />
                        <ReferenceLine y={parseInt(initialCapital)} stroke="#6b7280" strokeDasharray="5 5" label={{ value: "Break-even", fill: "#9ca3af", fontSize: 10, position: "insideBottomLeft" }} />
                        <Area 
                          type="linear" 
                          dataKey="value" 
                          stroke={result.stats.netProfit >= 0 ? "#10b981" : "#ef4444"} 
                          strokeWidth={2}
                          fillOpacity={1} 
                          fill="url(#backtestColor)" 
                          dot={{ r: 3, fill: result.stats.netProfit >= 0 ? "#10b981" : "#ef4444", strokeWidth: 0 }}
                          activeDot={{ r: 5, fill: result.stats.netProfit >= 0 ? "#10b981" : "#ef4444", strokeWidth: 0 }}
                        />
                      </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Rejection Terminal (New) */}
              {result.rejectionLogs && result.rejectionLogs.length > 0 && (
                <div className="glass-card rounded-xl p-6 border border-border/20 bg-muted/20">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
                      <Database className="w-4 h-4 text-warning" />
                      Trade Rejection Terminal
                    </h3>
                    <span className="text-xs bg-warning/20 text-warning px-2 py-0.5 rounded-full">
                      {result.rejectionLogs.length} Filtered Events
                    </span>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-4 font-mono text-[11px] h-[300px] overflow-y-auto border border-border/20">
                    {result.rejectionLogs.map((log: any, idx: number) => (
                      <div key={idx} className="mb-1.5 flex gap-3 border-b border-white/5 pb-1 last:border-0">
                        <span className="text-muted-foreground">[{log.time}]</span>
                        <span className="text-warning/90">{log.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Trades Table */}
              <div className="glass-card rounded-xl p-6 border border-border/20">
                <h3 className="font-display font-bold text-lg text-foreground mb-4">Simulated Executions ({result.trades.length})</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="text-xs uppercase text-muted-foreground border-b border-border/20">
                        <th className="pb-3 font-medium">Trade ID</th>
                        <th className="pb-3 font-medium">Type</th>
                        <th className="pb-3 font-medium text-right">Entry</th>
                        <th className="pb-3 font-medium text-right">Exit</th>
                        <th className="pb-3 font-medium text-right">PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.trades.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-4 text-center text-xs text-muted-foreground">No trades executed in this period.</td>
                        </tr>
                      ) : (
                        result.trades.map((trade: any, index: number) => (
                          <tr key={index} className={`border-b border-border/10 last:border-0 text-xs transition-colors ${index % 2 === 0 ? 'bg-muted/10' : 'bg-transparent'} hover:bg-muted/20`}>
                            <td className="py-3 font-medium text-foreground">{trade.id}</td>
                            <td className={`py-3 font-bold ${trade.type === "BUY" ? "text-success" : "text-destructive"}`}>
                              {trade.type}
                            </td>
                            <td className="py-3 text-right text-foreground">₹{trade.entry.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                            <td className="py-3 text-right text-foreground">₹{trade.exit.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                            <td className={`py-3 text-right font-bold ${trade.pnl >= 0 ? "text-success" : "text-destructive"}`}>
                              {trade.pnl >= 0 ? "+" : ""}₹{trade.pnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
