"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import CustomDatePicker from "@/components/custom-date-picker";
import { useState, useEffect, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
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
  Plus,
  X,
  Target,
  Zap as ZapIcon,
  Activity,
  User as UserIcon,
  Search as SearchIcon,
  Check,
  Edit2,
  Trash2,
  PieChart as PieChartIcon,
  TrendingUp
} from "lucide-react";

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#f43f5e'];

const journalEntries = [
  {
    id: 1,
    date: "May 09, 2026, 11:30",
    symbol: "RELIANCE",
    type: "BUY",
    pnl: "₹12,450",
    status: "success",
    emotion: "Calm",
    mistake: "None",
    notes: "Followed the plan perfectly. Waited for the 5m candle to close above the EMA 24 before entering.",
    reason: "EMA crossover + RSI breakout.",
    strategy: "EMA + RSI (Classic)",
    buyPrice: "₹2,500.00",
    sellPrice: "₹2,550.00",
    remarks: "Perfect entry.",
    timestamp: Date.now() - 1000 * 60 * 60 * 24 // 1 day ago
  },
  {
    id: 2,
    date: "May 09, 2026, 12:00",
    symbol: "NIFTY",
    type: "ADJ",
    pnl: "-₹500",
    status: "loss",
    emotion: "Neutral",
    mistake: "Manual Override",
    notes: "Manually closed position due to unexpected volatility.",
    reason: "Manual risk reduction.",
    strategy: "Institutional Momentum",
    buyPrice: "₹2,400.00",
    sellPrice: "₹2,390.00",
    remarks: "Market suddenly reversed due to global news.",
    timestamp: Date.now() - 1000 * 60 * 60 * 2 // 2 hours ago
  }
];

function JournalContent() {
  const searchParams = useSearchParams();
  const initialSearch = searchParams.get("symbol") || "";
  
  const [entries, setEntries] = useState(journalEntries);
  const [searchQuery, setSearchQuery] = useState(initialSearch);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filterDate, setFilterDate] = useState("");
  const [isFilterPanelOpen, setIsFilterPanelOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [symbolFilter, setSymbolFilter] = useState("all");
  const [isApplying, setIsApplying] = useState(false);

  // Manual Filter Staging States
  const [tempFilterDate, setTempFilterDate] = useState("");
  const [tempEmotionFilter, setTempEmotionFilter] = useState("all");
  const [tempSymbolFilter, setTempSymbolFilter] = useState("all");

  // New Entry State
  const [newEntry, setNewEntry] = useState({
    id: 0,
    date: new Date().toLocaleString('en-US', { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }),
    symbol: "",
    type: "BUY",
    pnl: "",
    status: "success",
    emotion: "Neutral",
    mistake: "None",
    notes: "",
    reason: "Manual Entry",
    strategy: "",
    buyPrice: "",
    sellPrice: "",
    remarks: "",
    timestamp: Date.now()
  });

  // INITIAL LOAD & 365-DAY FIFO RETENTION: Sync with LocalStorage
  useEffect(() => {
    const saved = localStorage.getItem("trading_journal_entries");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const now = Date.now();
        const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;
        
        // Filter out entries older than 365 days (FIFO automatic deletion)
        const validEntries = parsed
          .map((e: any) => ({ ...e, timestamp: e.timestamp || now })) // Add timestamp to legacy entries
          .filter((e: any) => now - e.timestamp <= ONE_YEAR_MS);
          
        setEntries(validEntries);
      } catch (err) {
        console.error("Failed to parse journal entries", err);
      }
    }
  }, []);

  // PERSISTENCE: Save on change
  useEffect(() => {
    localStorage.setItem("trading_journal_entries", JSON.stringify(entries));
  }, [entries]);

  // Sync searchQuery with URL
  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setSearchQuery(symbol);
    }
  }, [searchParams]);

  const [perfFilter, setPerfFilter] = useState("all");
  const [emotionFilter, setEmotionFilter] = useState("all");
  const [mistakeFilter, setMistakeFilter] = useState("all");

  const filteredEntries = useMemo(() => {
    let result = entries;
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(entry => 
        entry.symbol.toLowerCase().includes(query) ||
        entry.notes.toLowerCase().includes(query)
      );
    }
    if (filterDate) result = result.filter(entry => entry.date.includes(filterDate));
    if (perfFilter === "wins") result = result.filter(e => e.status === "success");
    if (perfFilter === "losses") result = result.filter(e => e.status === "loss");
    if (emotionFilter !== "all") result = result.filter(e => e.emotion.toLowerCase() === emotionFilter);
    if (symbolFilter !== "all") result = result.filter(e => e.symbol.toLowerCase() === symbolFilter);
    if (mistakeFilter === "errors") result = result.filter(e => e.mistake !== "None");
    
    return result;
  }, [entries, searchQuery, filterDate, perfFilter, emotionFilter, mistakeFilter, symbolFilter]);

  const handleApplyFilters = () => {
    setIsApplying(true);
    setFilterDate(tempFilterDate);
    setEmotionFilter(tempEmotionFilter);
    setSymbolFilter(tempSymbolFilter);
    setTimeout(() => setIsApplying(false), 800);
  };

  const handleSaveEntry = () => {
    if (!newEntry.symbol || !newEntry.pnl) {
      toast.error("Symbol and PnL are required");
      return;
    }

    const pnlValue = parseFloat(newEntry.pnl.replace(/[₹,]/g, ''));
    const entryWithStatus = {
      ...newEntry,
      id: editingId || Date.now(),
      status: pnlValue >= 0 ? "success" : "loss"
    };

    if (editingId) {
      setEntries(entries.map(e => e.id === editingId ? entryWithStatus : e));
      toast.success("Entry Updated");
    } else {
      setEntries([entryWithStatus, ...entries]);
      toast.success("Entry Added");
    }
    
    setIsAddModalOpen(false);
    setEditingId(null);
    setNewEntry({
      id: 0,
      date: new Date().toLocaleString('en-US', { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }),
      symbol: "",
      type: "BUY",
      pnl: "",
      status: "success",
      emotion: "Neutral",
      mistake: "None",
      notes: "",
      reason: "Manual Entry",
      strategy: "",
      buyPrice: "",
      sellPrice: "",
      remarks: "",
      timestamp: Date.now()
    });
  };

  const handleDeleteEntry = (id: number, symbol: string) => {
    setEntries(entries.filter(e => e.id !== id));
    toast.warning(`Deleted ${symbol}`);
  };

  const startEdit = (entry: any) => {
    setNewEntry(entry);
    setEditingId(entry.id);
    setIsAddModalOpen(true);
  };

  const resetFilters = () => {
    setPerfFilter("all");
    setEmotionFilter("all");
    setMistakeFilter("all");
    setSearchQuery("");
    setFilterDate("");
    setSymbolFilter("all");
    toast.success("Filters Reset");
  };

  const formatDisplayDate = (dateStr: string) => {
    if (!dateStr) return "";
    if (/\d{4}/.test(dateStr)) return dateStr;
    const parts = dateStr.split(',');
    if (parts.length > 1) return `${parts[0]}, 2026,${parts[1]}`;
    const spaceParts = dateStr.split(' ');
    if (spaceParts.length >= 3) return `${spaceParts[0]} ${spaceParts[1]}, 2026, ${spaceParts[2]}`;
    return dateStr + ", 2026";
  };

  const exportToCSV = () => {
    if (entries.length === 0) return toast.error("No entries to export");
    const headers = ["Time", "Symbol", "Side", "Strategy", "Buy Price", "Sell Price", "PnL", "Emotion", "Remarks", "Notes"];
    const csvContent = [
      headers.join(","),
      ...entries.map(e => `"${formatDisplayDate(e.date)}","${e.symbol}","${e.type}","${e.strategy || ''}","${e.buyPrice || ''}","${e.sellPrice || ''}","${e.pnl}","${e.emotion}","${(e.remarks || '').replace(/"/g, '""')}","${e.notes.replace(/"/g, '""')}"`)
    ].join("\n");
    
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `AI_Trading_Journal_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Journal exported successfully");
  };

  // Analytics Calculations
  const totalTrades = filteredEntries.length;
  const netPnL = filteredEntries.reduce((acc, curr) => acc + (parseFloat(curr.pnl.replace(/[^\d.-]/g, '')) || 0), 0);
  const winningTrades = filteredEntries.filter(e => (parseFloat(e.pnl.replace(/[^\d.-]/g, '')) || 0) > 0).length;
  const winRate = totalTrades > 0 ? Math.round((winningTrades / totalTrades) * 100) : 0;

  const chartData = useMemo(() => {
    const reversed = [...filteredEntries].reverse();
    let cumulative = 0;
    return reversed.map((e, idx) => {
      const pnlValue = parseFloat(e.pnl.replace(/[^\d.-]/g, '')) || 0;
      cumulative += pnlValue;
      return {
        name: `T${idx + 1}`,
        equity: cumulative,
        pnl: pnlValue,
      };
    });
  }, [filteredEntries]);

  const strategyData = useMemo(() => {
    const stats: Record<string, { wins: number; losses: number; value: number }> = {};
    filteredEntries.forEach(e => {
      const s = e.strategy || 'Manual Trade';
      if (!stats[s]) stats[s] = { wins: 0, losses: 0, value: 0 };
      const pnlValue = parseFloat(e.pnl.replace(/[^\d.-]/g, '')) || 0;
      if (pnlValue >= 0) {
        stats[s].wins += 1;
      } else {
        stats[s].losses += 1;
      }
      stats[s].value += 1;
    });
    return Object.keys(stats).map(key => ({
      name: key,
      value: stats[key].value,
      wins: stats[key].wins,
      losses: stats[key].losses,
      winRate: Math.round((stats[key].wins / stats[key].value) * 100)
    })).sort((a, b) => b.value - a.value);
  }, [filteredEntries]);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl">AI Trading Journal</h1>
              <p className="text-sm text-muted-foreground">Professional trade logging & psychological audit.</p>
            </div>
            <div className="flex gap-3">
              <button onClick={exportToCSV} className="px-4 py-2 bg-muted text-foreground hover:bg-muted/80 rounded-lg text-sm transition-colors flex items-center gap-2 border border-border/50">
                <Download className="w-4 h-4" /> Export
              </button>
              <button onClick={() => setIsFilterPanelOpen(true)} className="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm transition-colors flex items-center gap-2">
                <Filter className="w-4 h-4" /> Deep Filter
              </button>
              <button onClick={() => setIsAddModalOpen(true)} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold shadow-lg flex items-center gap-2">
                <Plus className="w-4 h-4" /> Add Entry
              </button>
            </div>
          </div>

          {/* ANALYTICS DASHBOARD */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div className="glass-card rounded-2xl border border-border/20 p-6 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-1">Net PnL</p>
                <h3 className={`text-3xl font-black ${netPnL >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {netPnL >= 0 ? '+' : ''}₹{Math.abs(netPnL).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </h3>
              </div>
              <div className={`p-4 rounded-xl ${netPnL >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                {netPnL >= 0 ? <ArrowUpRight className="w-8 h-8" /> : <ArrowDownRight className="w-8 h-8" />}
              </div>
            </div>

            <div className="glass-card rounded-2xl border border-border/20 p-6 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-1">Win Rate</p>
                <h3 className="text-3xl font-black text-primary">
                  {winRate}%
                </h3>
              </div>
              <div className="p-4 rounded-xl bg-primary/10 text-primary">
                <Target className="w-8 h-8" />
              </div>
            </div>

            <div className="glass-card rounded-2xl border border-border/20 p-6 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-1">Total Trades</p>
                <h3 className="text-3xl font-black text-foreground">
                  {totalTrades}
                </h3>
              </div>
              <div className="p-4 rounded-xl bg-muted text-muted-foreground">
                <Activity className="w-8 h-8" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div className="lg:col-span-2 glass-card rounded-2xl border border-border/20 p-6">
              <h3 className="font-bold text-lg flex items-center gap-2 mb-6">
                <TrendingUp className="w-5 h-5 text-primary" /> Equity Curve
              </h3>
              <div className="h-full min-h-[250px] w-full">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                      <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val}`} />
                      <RechartsTooltip 
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', color: '#f8fafc' }}
                        itemStyle={{ color: '#10b981', fontWeight: 'bold' }}
                        formatter={(value: any) => [`₹${Number(value).toLocaleString('en-IN')}`, 'Total Equity']}
                        labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                        cursor={{ stroke: '#334155', strokeWidth: 1, strokeDasharray: '4 4' }}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="equity" 
                        stroke="#10b981" 
                        strokeWidth={3} 
                        fillOpacity={1} 
                        fill="url(#colorEquity)" 
                        activeDot={{ r: 6, fill: '#10b981', stroke: '#0f172a', strokeWidth: 2 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground text-sm">No data available</div>
                )}
              </div>
            </div>

            <div className="glass-card rounded-2xl border border-border/20 p-6 flex flex-col">
              <h3 className="font-bold text-lg flex items-center gap-2 mb-6">
                <PieChartIcon className="w-5 h-5 text-primary" /> Strategy Breakdown
              </h3>
              <div className="flex-1 min-h-[200px] w-full relative">
                {strategyData.length > 0 ? (
                  <>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={strategyData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={80}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {strategyData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip 
                          contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                          formatter={(value: any, name: any, props: any) => [`${value} Trades (${props.payload.winRate}% Win)`, name]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                      <span className="text-2xl font-bold">{filteredEntries.length}</span>
                      <span className="text-xs text-muted-foreground">Trades</span>
                    </div>
                  </>
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground text-sm">No data available</div>
                )}
              </div>
            </div>
          </div>

          <div className="glass-card rounded-2xl border border-border/20 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-muted/30 text-xs uppercase font-bold">
                  <tr>
                    <th className="px-6 py-4">Time</th>
                    <th className="px-6 py-4">Symbol</th>
                    <th className="px-6 py-4">Side</th>
                    <th className="px-6 py-4">Strategy</th>
                    <th className="px-6 py-4">Buy Price</th>
                    <th className="px-6 py-4">Sell Price</th>
                    <th className="px-6 py-4">PnL</th>
                    <th className="px-6 py-4">Remarks</th>
                    <th className="px-6 py-4">Emotion</th>
                    <th className="px-6 py-4 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {filteredEntries.map((entry) => (
                    <tr key={entry.id} className="hover:bg-primary/5 transition-colors group">
                      <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">{formatDisplayDate(entry.date)}</td>
                      <td className="px-6 py-4 font-bold text-foreground">{entry.symbol}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[10px] font-black ${entry.type === 'BUY' ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'}`}>
                          {entry.type}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-muted-foreground font-medium">{entry.strategy || "Manual"}</td>
                      <td className="px-6 py-4 text-muted-foreground">{entry.buyPrice || "-"}</td>
                      <td className="px-6 py-4 text-muted-foreground">{entry.sellPrice || "-"}</td>
                      <td className={`px-6 py-4 font-mono font-bold ${entry.status === 'success' ? 'text-success' : 'text-destructive'}`}>
                        {entry.pnl}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground max-w-[200px] truncate" title={entry.remarks || entry.notes}>{entry.remarks || "-"}</td>
                      <td className="px-6 py-4">
                        <span className="flex items-center gap-1.5">
                          {entry.emotion === 'Calm' ? <Smile className="w-4 h-4 text-success" /> : <Meh className="w-4 h-4 text-warning" />}
                          {entry.emotion}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => startEdit(entry)} className="p-1.5 hover:bg-primary/20 rounded-lg transition-all"><Edit2 className="w-4 h-4" /></button>
                          <button onClick={() => handleDeleteEntry(entry.id, entry.symbol)} className="p-1.5 hover:bg-destructive/20 rounded-lg transition-all"><Trash2 className="w-4 h-4" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredEntries.length === 0 && (
                <div className="p-20 text-center flex flex-col items-center gap-3">
                  <BookOpen className="w-12 h-12 text-muted-foreground/20" />
                  <p className="text-muted-foreground">No entries found matching your criteria.</p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {/* MODALS */}
      
      {isFilterPanelOpen && (
        <div className="fixed inset-0 z-[100] flex justify-end">
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm" onClick={() => setIsFilterPanelOpen(false)}></div>
          <div className="relative w-80 bg-card border-l border-border/20 p-6 shadow-2xl animate-in slide-in-from-right duration-300">
            <div className="flex justify-between items-center mb-8">
              <h2 className="font-bold text-xl">Deep Filter</h2>
              <button onClick={() => setIsFilterPanelOpen(false)}><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-bold text-muted-foreground uppercase">Performance</label>
                <div className="grid grid-cols-1 gap-2">
                  {['all', 'wins', 'losses'].map(f => (
                    <button key={f} onClick={() => setPerfFilter(f)} className={`text-left px-4 py-2 rounded-lg text-sm border transition-all ${perfFilter === f ? 'bg-primary border-primary text-white shadow-lg' : 'border-border/50 hover:bg-muted/50'}`}>
                      {f.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <button onClick={resetFilters} className="w-full py-2 text-xs font-bold text-primary hover:opacity-80 transition-all">RESET ALL FILTERS</button>
            </div>
          </div>
        </div>
      )}

      {isAddModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-background/80 backdrop-blur-md" onClick={() => setIsAddModalOpen(false)}></div>
          <div className="relative w-full max-w-lg glass-card border border-border/30 rounded-3xl p-8 shadow-2xl animate-in zoom-in-95 duration-200">
            <h2 className="text-2xl font-black mb-6">{editingId ? "Edit Execution" : "Log New Execution"}</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <input type="text" placeholder="SYMBOL" value={newEntry.symbol} onChange={e => setNewEntry({...newEntry, symbol: e.target.value.toUpperCase()})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm font-bold focus:ring-2 focus:ring-primary/50 outline-none transition-all" />
                <input type="text" placeholder="PnL (₹)" value={newEntry.pnl} onChange={e => setNewEntry({...newEntry, pnl: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm font-mono font-bold focus:ring-2 focus:ring-primary/50 outline-none transition-all" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <input type="text" placeholder="Buy Price (₹)" value={newEntry.buyPrice} onChange={e => setNewEntry({...newEntry, buyPrice: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/50 outline-none transition-all" />
                <input type="text" placeholder="Sell Price (₹)" value={newEntry.sellPrice} onChange={e => setNewEntry({...newEntry, sellPrice: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/50 outline-none transition-all" />
              </div>
              <select 
                value={newEntry.strategy} 
                onChange={e => setNewEntry({...newEntry, strategy: e.target.value})} 
                className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm text-foreground focus:ring-2 focus:ring-primary/50 outline-none transition-all"
              >
                <option value="" disabled>Select Strategy Used</option>
                <option value="EMA + RSI (Classic)">EMA + RSI (Classic)</option>
                <option value="Enhanced AI Strategy">Enhanced AI Strategy</option>
                <option value="Institutional EMA">Institutional EMA</option>
                <option value="Advanced AI/ML">Advanced AI/ML</option>
                <option value="Premium Options Alpha">Premium Options Alpha</option>
                <option value="Institutional Momentum">Institutional Momentum</option>
                <option value="Manual Trade">Manual Trade</option>
              </select>
              <textarea placeholder="Trade Logic & Notes" rows={2} value={newEntry.notes} onChange={e => setNewEntry({...newEntry, notes: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-primary/50 outline-none transition-all resize-none"></textarea>
              <textarea placeholder="Remarks (If loss, specify reason)" rows={2} value={newEntry.remarks} onChange={e => setNewEntry({...newEntry, remarks: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-primary/50 outline-none transition-all resize-none"></textarea>
              <div className="flex gap-4 pt-4">
                <button onClick={() => setIsAddModalOpen(false)} className="flex-1 py-3 bg-muted/50 text-foreground hover:bg-muted rounded-xl text-sm font-bold transition-all">Cancel</button>
                <button onClick={handleSaveEntry} className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-bold shadow-lg hover:bg-primary/90 transition-all">Save Log</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Journal() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        <div className="text-center space-y-4">
          <div className="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto"></div>
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Journal...</p>
        </div>
      </div>
    }>
      <JournalContent />
    </Suspense>
  );
}
