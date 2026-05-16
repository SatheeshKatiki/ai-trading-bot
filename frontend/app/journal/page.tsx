"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import CustomDatePicker from "@/components/custom-date-picker";
import { useState, useEffect, useMemo } from "react";
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
  Trash2
} from "lucide-react";

const journalEntries = [
  {
    id: 1,
    date: "May 09, 11:30",
    symbol: "RELIANCE",
    type: "BUY",
    pnl: "₹12,450",
    status: "success",
    emotion: "Calm",
    mistake: "None",
    notes: "Followed the plan perfectly. Waited for the 5m candle to close above the EMA 24 before entering.",
    reason: "EMA crossover + RSI breakout."
  },
  {
    id: 2,
    date: "May 09, 12:00",
    symbol: "NIFTY",
    type: "ADJ",
    pnl: "-₹500",
    status: "loss",
    emotion: "Neutral",
    mistake: "Manual Override",
    notes: "Manually closed position due to unexpected volatility.",
    reason: "Manual risk reduction."
  }
];

export default function Journal() {
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
    date: new Date().toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(',', ''),
    symbol: "",
    type: "BUY",
    pnl: "",
    status: "success",
    emotion: "Neutral",
    mistake: "None",
    notes: "",
    reason: "Manual Entry"
  });

  // INITIAL LOAD: Sync with LocalStorage
  useEffect(() => {
    const saved = localStorage.getItem("trading_journal_entries");
    if (saved) {
      setEntries(JSON.parse(saved));
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
      date: new Date().toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(',', ''),
      symbol: "",
      type: "BUY",
      pnl: "",
      status: "success",
      emotion: "Neutral",
      mistake: "None",
      notes: "",
      reason: "Manual Entry"
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
              <button onClick={() => setIsFilterPanelOpen(true)} className="px-4 py-2 bg-muted/50 rounded-lg text-sm border border-border/50 flex items-center gap-2">
                <Filter className="w-4 h-4" /> Deep Filter
              </button>
              <button onClick={() => setIsAddModalOpen(true)} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold shadow-lg flex items-center gap-2">
                <Plus className="w-4 h-4" /> Add Entry
              </button>
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
                    <th className="px-6 py-4">PnL</th>
                    <th className="px-6 py-4">Emotion</th>
                    <th className="px-6 py-4 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {filteredEntries.map((entry) => (
                    <tr key={entry.id} className="hover:bg-primary/5 transition-colors group">
                      <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">{entry.date}</td>
                      <td className="px-6 py-4 font-bold text-foreground">{entry.symbol}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[10px] font-black ${entry.type === 'BUY' ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'}`}>
                          {entry.type}
                        </span>
                      </td>
                      <td className={`px-6 py-4 font-mono font-bold ${entry.status === 'success' ? 'text-success' : 'text-destructive'}`}>
                        {entry.pnl}
                      </td>
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
      <Toaster position="top-right" richColors closeButton />
      
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
              <button onClick={resetFilters} className="w-full py-2 text-xs font-bold text-muted-foreground hover:text-foreground transition-all">RESET ALL FILTERS</button>
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
              <textarea placeholder="Trade Logic & Notes" rows={4} value={newEntry.notes} onChange={e => setNewEntry({...newEntry, notes: e.target.value})} className="w-full bg-muted/30 border border-border/50 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-primary/50 outline-none transition-all resize-none"></textarea>
              <div className="flex gap-4 pt-4">
                <button onClick={() => setIsAddModalOpen(false)} className="flex-1 py-3 bg-muted/50 rounded-xl text-sm font-bold hover:bg-muted transition-all">Cancel</button>
                <button onClick={handleSaveEntry} className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-bold shadow-lg hover:bg-primary/90 transition-all">Save Log</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
