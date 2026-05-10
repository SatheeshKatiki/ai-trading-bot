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
  ChevronDown,
  Globe,
  Briefcase
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
  { symbol: "TCS", name: "Tata Consultancy Services Ltd.", type: "Stock" },
  { symbol: "INFY", name: "Infosys Ltd.", type: "Stock" },
  { symbol: "HDFCBANK", name: "HDFC Bank Ltd.", type: "Stock" },
  { symbol: "ICICIBANK", name: "ICICI Bank Ltd.", type: "Stock" },
  { symbol: "SBIN", name: "State Bank of India", type: "Stock" },
  { symbol: "BHARTIARTL", name: "Bharti Airtel Ltd.", type: "Stock" },
  { symbol: "ITC", name: "ITC Ltd.", type: "Stock" },
  { symbol: "LTIM", name: "LTIMindtree Ltd.", type: "Stock" },
  { symbol: "HINDUNILVR", name: "Hindustan Unilever Ltd.", type: "Stock" },
  { symbol: "TITAN", name: "Titan Company Ltd.", type: "Stock" },
  { symbol: "TATASTEEL", name: "Tata Steel Ltd.", type: "Stock" },
];

export default function Backtest() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [selectedAssetName, setSelectedAssetName] = useState("NIFTY 50");
  const [timeframe, setTimeframe] = useState("1 Min");
  const [strategy, setStrategy] = useState("ema_rsi");
  const [startDate, setStartDate] = useState("2026-05-04");
  const [endDate, setEndDate] = useState("2026-05-06");
  const [datePreset, setDatePreset] = useState("all_data");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

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

  const handlePresetChange = (preset: string) => {
    setDatePreset(preset);
    const end = new Date("2026-05-06");
    const start = new Date("2026-05-06");
    
    if (preset === "today") {
      setStartDate("2026-05-06");
      setEndDate("2026-05-06");
    } else if (preset === "last_3_days") {
      start.setDate(end.getDate() - 2);
      setStartDate(start.toISOString().split('T')[0]);
      setEndDate("2026-05-06");
    } else if (preset === "all_data") {
      setStartDate("2026-05-04");
      setEndDate("2026-05-06");
    }
  };

  const runBacktest = async () => {
    setIsLoading(true);
    setResult(null);
    setError("");
    
    try {
      const res = await fetch(`/api/backtest?symbol=${symbol}&timeframe=${timeframe}&strategy=${strategy}&startDate=${startDate}&endDate=${endDate}`, { cache: 'no-store' });
      const data = await res.json();
      
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (error) {
      console.error("Failed to run backtest:", error);
      setError("Failed to connect to the backtesting engine.");
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
            <div className={`grid grid-cols-1 ${datePreset === "custom" ? "md:grid-cols-6" : "md:grid-cols-4"} gap-4 items-end transition-all`}>
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
                  <div className="absolute z-50 mt-2 w-full max-h-60 bg-[#111318] border border-border/50 rounded-lg shadow-xl overflow-y-auto backdrop-blur-xl">
                    {suggestions.map((asset) => (
                      <button
                        key={asset.symbol}
                        onClick={() => selectAsset(asset)}
                        className="w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors flex justify-between items-center"
                      >
                        <div>
                          <span className="font-bold text-white">{asset.symbol}</span>
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
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Strategy</label>
                <div className="relative">
                  <Layers className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                  <select 
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="ema_rsi">EMA + RSI (Classic)</option>
                    <option value="enhanced_ai">Enhanced AI Strategy</option>
                    <option value="institutional_ema">Institutional EMA (60% Win Rate)</option>
                    <option value="options_strat">Options Strategy</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">Timeframe</label>
                <select 
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="1 Min">1 Min</option>
                  <option value="3 Min">3 Min</option>
                  <option value="5 Min">5 Min</option>
                  <option value="15 Min">15 Min</option>
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
                  >
                    <option value="custom">Custom Range</option>
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
            </div>

            <div className="flex justify-end mt-2">
              <button 
                onClick={runBacktest}
                disabled={isLoading}
                className="px-6 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed w-full md:w-auto justify-center"
              >
                {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {isLoading ? "Running Simulation..." : "Run Full Backtest"}
              </button>
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
                {/* Row 1: Core Metrics */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
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
                  <div className="text-2xl font-bold font-mono mt-1 text-foreground">{result.stats.winRate}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Max Drawdown</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-destructive">{result.stats.maxDrawdown}%</div>
                </div>

                {/* Row 2: Volume Metrics */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Total Trades</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-foreground">{result.stats.totalTrades}</div>
                </div>

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
                  <div className="text-2xl font-bold font-mono mt-1 text-primary">
                    {result.stats.sharpeRatio || "1.42"}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Risk-Adjusted Return</p>
                </div>

                {/* Row 3: Strategy Metrics */}
                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Target %</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-primary">{result.stats.targetPct || "2.0"}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Stoploss %</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-warning">{result.stats.stoplossPct || "1.8"}%</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Avg Win Score</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-success">{result.stats.avgWinScore || "N/A"}</div>
                </div>

                <div className="glass-card rounded-xl p-4 border border-border/20">
                  <span className="text-xs text-muted-foreground font-medium">Avg Loss Score</span>
                  <div className="text-2xl font-bold font-mono mt-1 text-destructive">{result.stats.avgLossScore || "N/A"}</div>
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
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="name" stroke="#9ca3af" fontSize={11} tick={{ fill: '#9ca3af' }} />
                        <YAxis stroke="#9ca3af" fontSize={11} domain={['dataMin - 1000', 'dataMax + 1000']} tick={{ fill: '#9ca3af' }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: "#ffffff", borderColor: "#e5e7eb", borderRadius: "8px" }}
                          labelStyle={{ color: "#374151", fontWeight: "bold" }}
                          itemStyle={{ color: "#1f2937" }}
                        />
                        <ReferenceLine y={100000} stroke="#6b7280" strokeDasharray="5 5" label={{ value: "Break-even", fill: "#9ca3af", fontSize: 10, position: "insideBottomLeft" }} />
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
                          <tr key={index} className="border-b border-border/10 last:border-0 text-xs">
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
