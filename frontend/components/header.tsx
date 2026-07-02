"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, Search, User, BookOpen, LogOut, Settings, CreditCard, Command, Activity, ShieldAlert, XCircle } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { toast } from "sonner";

// Institutional Level Asset Database for Autocomplete
const INDIAN_MARKET_ASSETS = [
  { symbol: "NIFTY", name: "NIFTY Index", type: "Index" },
  { symbol: "BANKNIFTY", name: "BANKNIFTY Index", type: "Index" },
  { symbol: "FINNIFTY", name: "FINNIFTY Index", type: "Index" },
  { symbol: "MIDCPNIFTY", name: "MIDCPNIFTY Index", type: "Index" },
  { symbol: "SENSEX", name: "SENSEX Index", type: "Index" },
  { symbol: "AARTIIND", name: "AARTIIND", type: "Stock" },
  { symbol: "ABB", name: "ABB", type: "Stock" },
  { symbol: "ABBOTINDIA", name: "ABBOTINDIA", type: "Stock" },
  { symbol: "ABCAPITAL", name: "ABCAPITAL", type: "Stock" },
  { symbol: "ABFRL", name: "ABFRL", type: "Stock" },
  { symbol: "ACC", name: "ACC", type: "Stock" },
  { symbol: "ADANIENT", name: "ADANIENT", type: "Stock" },
  { symbol: "ADANIPORTS", name: "ADANIPORTS", type: "Stock" },
  { symbol: "ALKEM", name: "ALKEM", type: "Stock" },
  { symbol: "AMBUJACEM", name: "AMBUJACEM", type: "Stock" },
  { symbol: "APOLLOHOSP", name: "APOLLOHOSP", type: "Stock" },
  { symbol: "APOLLOTYRE", name: "APOLLOTYRE", type: "Stock" },
  { symbol: "ASHOKLEY", name: "ASHOKLEY", type: "Stock" },
  { symbol: "ASIANPAINT", name: "ASIANPAINT", type: "Stock" },
  { symbol: "ASTRAL", name: "ASTRAL", type: "Stock" },
  { symbol: "ATUL", name: "ATUL", type: "Stock" },
  { symbol: "AUBANK", name: "AUBANK", type: "Stock" },
  { symbol: "AUROPHARMA", name: "AUROPHARMA", type: "Stock" },
  { symbol: "AXISBANK", name: "AXISBANK", type: "Stock" },
  { symbol: "BAJAJ-AUTO", name: "BAJAJ-AUTO", type: "Stock" },
  { symbol: "BAJAJFINSV", name: "BAJAJFINSV", type: "Stock" },
  { symbol: "BAJFINANCE", name: "BAJFINANCE", type: "Stock" },
  { symbol: "BALKRISIND", name: "BALKRISIND", type: "Stock" },
  { symbol: "BALRAMCHIN", name: "BALRAMCHIN", type: "Stock" },
  { symbol: "BANDHANBNK", name: "BANDHANBNK", type: "Stock" },
  { symbol: "BANKBARODA", name: "BANKBARODA", type: "Stock" },
  { symbol: "BATAINDIA", name: "BATAINDIA", type: "Stock" },
  { symbol: "BEL", name: "BEL", type: "Stock" },
  { symbol: "BERGEPAINT", name: "BERGEPAINT", type: "Stock" },
  { symbol: "BHARATFORG", name: "BHARATFORG", type: "Stock" },
  { symbol: "BHARTIARTL", name: "BHARTIARTL", type: "Stock" },
  { symbol: "BHEL", name: "BHEL", type: "Stock" },
  { symbol: "BIOCON", name: "BIOCON", type: "Stock" },
  { symbol: "BOSCHLTD", name: "BOSCHLTD", type: "Stock" },
  { symbol: "BPCL", name: "BPCL", type: "Stock" },
  { symbol: "BRITANNIA", name: "BRITANNIA", type: "Stock" },
  { symbol: "BSOFT", name: "BSOFT", type: "Stock" },
  { symbol: "CANBK", name: "CANBK", type: "Stock" },
  { symbol: "CANFINHOME", name: "CANFINHOME", type: "Stock" },
  { symbol: "CHAMBLFERT", name: "CHAMBLFERT", type: "Stock" },
  { symbol: "CHOLAFIN", name: "CHOLAFIN", type: "Stock" },
  { symbol: "CIPLA", name: "CIPLA", type: "Stock" },
  { symbol: "COALINDIA", name: "COALINDIA", type: "Stock" },
  { symbol: "COFORGE", name: "COFORGE", type: "Stock" },
  { symbol: "COLPAL", name: "COLPAL", type: "Stock" },
  { symbol: "CONCOR", name: "CONCOR", type: "Stock" },
  { symbol: "COROMANDEL", name: "COROMANDEL", type: "Stock" },
  { symbol: "CROMPTON", name: "CROMPTON", type: "Stock" },
  { symbol: "CUB", name: "CUB", type: "Stock" },
  { symbol: "CUMMINSIND", name: "CUMMINSIND", type: "Stock" },
  { symbol: "DABUR", name: "DABUR", type: "Stock" },
  { symbol: "DALBHARAT", name: "DALBHARAT", type: "Stock" },
  { symbol: "DEEPAKNTR", name: "DEEPAKNTR", type: "Stock" },
  { symbol: "DIVISLAB", name: "DIVISLAB", type: "Stock" },
  { symbol: "DIXON", name: "DIXON", type: "Stock" },
  { symbol: "DLF", name: "DLF", type: "Stock" },
  { symbol: "DRREDDY", name: "DRREDDY", type: "Stock" },
  { symbol: "EICHERMOT", name: "EICHERMOT", type: "Stock" },
  { symbol: "ESCORTS", name: "ESCORTS", type: "Stock" },
  { symbol: "EXIDEIND", name: "EXIDEIND", type: "Stock" },
  { symbol: "FEDERALBNK", name: "FEDERALBNK", type: "Stock" },
  { symbol: "GAIL", name: "GAIL", type: "Stock" },
  { symbol: "GLENMARK", name: "GLENMARK", type: "Stock" },
  { symbol: "GMRINFRA", name: "GMRINFRA", type: "Stock" },
  { symbol: "GNFC", name: "GNFC", type: "Stock" },
  { symbol: "GODREJCP", name: "GODREJCP", type: "Stock" },
  { symbol: "GODREJPROP", name: "GODREJPROP", type: "Stock" },
  { symbol: "GRANULES", name: "GRANULES", type: "Stock" },
  { symbol: "GRASIM", name: "GRASIM", type: "Stock" },
  { symbol: "GUJGASLTD", name: "GUJGASLTD", type: "Stock" },
  { symbol: "HAL", name: "HAL", type: "Stock" },
  { symbol: "HAVELLS", name: "HAVELLS", type: "Stock" },
  { symbol: "HCLTECH", name: "HCLTECH", type: "Stock" },
  { symbol: "HDFCAMC", name: "HDFCAMC", type: "Stock" },
  { symbol: "HDFCBANK", name: "HDFCBANK", type: "Stock" },
  { symbol: "HDFCLIFE", name: "HDFCLIFE", type: "Stock" },
  { symbol: "HEROMOTOCO", name: "HEROMOTOCO", type: "Stock" },
  { symbol: "HINDALCO", name: "HINDALCO", type: "Stock" },
  { symbol: "HINDCOPPER", name: "HINDCOPPER", type: "Stock" },
  { symbol: "HINDPETRO", name: "HINDPETRO", type: "Stock" },
  { symbol: "HINDUNILVR", name: "HINDUNILVR", type: "Stock" },
  { symbol: "ICICIBANK", name: "ICICIBANK", type: "Stock" },
  { symbol: "ICICIGI", name: "ICICIGI", type: "Stock" },
  { symbol: "ICICIPRULI", name: "ICICIPRULI", type: "Stock" },
  { symbol: "IDEA", name: "IDEA", type: "Stock" },
  { symbol: "IDFC", name: "IDFC", type: "Stock" },
  { symbol: "IDFCFIRSTB", name: "IDFCFIRSTB", type: "Stock" },
  { symbol: "IEX", name: "IEX", type: "Stock" },
  { symbol: "IGL", name: "IGL", type: "Stock" },
  { symbol: "INDHOTEL", name: "INDHOTEL", type: "Stock" },
  { symbol: "INDIACEM", name: "INDIACEM", type: "Stock" },
  { symbol: "INDIAMART", name: "INDIAMART", type: "Stock" },
  { symbol: "INDIGO", name: "INDIGO", type: "Stock" },
  { symbol: "INDUSINDBK", name: "INDUSINDBK", type: "Stock" },
  { symbol: "INDUSTOWER", name: "INDUSTOWER", type: "Stock" },
  { symbol: "INFY", name: "INFY", type: "Stock" },
  { symbol: "IOC", name: "IOC", type: "Stock" },
  { symbol: "IPCALAB", name: "IPCALAB", type: "Stock" },
  { symbol: "IRCTC", name: "IRCTC", type: "Stock" },
  { symbol: "ITC", name: "ITC", type: "Stock" },
  { symbol: "JINDALSTEL", name: "JINDALSTEL", type: "Stock" },
  { symbol: "JKCEMENT", name: "JKCEMENT", type: "Stock" },
  { symbol: "JSWSTEEL", name: "JSWSTEEL", type: "Stock" },
  { symbol: "JUBLFOOD", name: "JUBLFOOD", type: "Stock" },
  { symbol: "KOTAKBANK", name: "KOTAKBANK", type: "Stock" },
  { symbol: "L&TFH", name: "L&TFH", type: "Stock" },
  { symbol: "LALPATHLAB", name: "LALPATHLAB", type: "Stock" },
  { symbol: "LAURUSLABS", name: "LAURUSLABS", type: "Stock" },
  { symbol: "LICHSGFIN", name: "LICHSGFIN", type: "Stock" },
  { symbol: "LT", name: "LT", type: "Stock" },
  { symbol: "LTIM", name: "LTIM", type: "Stock" },
  { symbol: "LTTS", name: "LTTS", type: "Stock" },
  { symbol: "LUPIN", name: "LUPIN", type: "Stock" },
  { symbol: "M&M", name: "M&M", type: "Stock" },
  { symbol: "M&MFIN", name: "M&MFIN", type: "Stock" },
  { symbol: "MANAPPURAM", name: "MANAPPURAM", type: "Stock" },
  { symbol: "MARICO", name: "MARICO", type: "Stock" },
  { symbol: "MARUTI", name: "MARUTI", type: "Stock" },
  { symbol: "MCDOWELL-N", name: "MCDOWELL-N", type: "Stock" },
  { symbol: "MCX", name: "MCX", type: "Stock" },
  { symbol: "METROPOLIS", name: "METROPOLIS", type: "Stock" },
  { symbol: "MFSL", name: "MFSL", type: "Stock" },
  { symbol: "MGL", name: "MGL", type: "Stock" },
  { symbol: "MOTHERSON", name: "MOTHERSON", type: "Stock" },
  { symbol: "MPHASIS", name: "MPHASIS", type: "Stock" },
  { symbol: "MRF", name: "MRF", type: "Stock" },
  { symbol: "MUTHOOTFIN", name: "MUTHOOTFIN", type: "Stock" },
  { symbol: "NATIONALUM", name: "NATIONALUM", type: "Stock" },
  { symbol: "NAUKRI", name: "NAUKRI", type: "Stock" },
  { symbol: "NAVINFLUOR", name: "NAVINFLUOR", type: "Stock" },
  { symbol: "NESTLEIND", name: "NESTLEIND", type: "Stock" },
  { symbol: "NMDC", name: "NMDC", type: "Stock" },
  { symbol: "NTPC", name: "NTPC", type: "Stock" },
  { symbol: "OBEROIRLTY", name: "OBEROIRLTY", type: "Stock" },
  { symbol: "OFSS", name: "OFSS", type: "Stock" },
  { symbol: "ONGC", name: "ONGC", type: "Stock" },
  { symbol: "PAGEIND", name: "PAGEIND", type: "Stock" },
  { symbol: "PEL", name: "PEL", type: "Stock" },
  { symbol: "PERSISTENT", name: "PERSISTENT", type: "Stock" },
  { symbol: "PETRONET", name: "PETRONET", type: "Stock" },
  { symbol: "PFC", name: "PFC", type: "Stock" },
  { symbol: "PIDILITIND", name: "PIDILITIND", type: "Stock" },
  { symbol: "PIIND", name: "PIIND", type: "Stock" },
  { symbol: "PNB", name: "PNB", type: "Stock" },
  { symbol: "POLYCAB", name: "POLYCAB", type: "Stock" },
  { symbol: "POWERGRID", name: "POWERGRID", type: "Stock" },
  { symbol: "PVRINOX", name: "PVRINOX", type: "Stock" },
  { symbol: "RAMCOCEM", name: "RAMCOCEM", type: "Stock" },
  { symbol: "RBLBANK", name: "RBLBANK", type: "Stock" },
  { symbol: "RECLTD", name: "RECLTD", type: "Stock" },
  { symbol: "RELIANCE", name: "RELIANCE", type: "Stock" },
  { symbol: "SAIL", name: "SAIL", type: "Stock" },
  { symbol: "SBICARD", name: "SBICARD", type: "Stock" },
  { symbol: "SBILIFE", name: "SBILIFE", type: "Stock" },
  { symbol: "SBIN", name: "SBIN", type: "Stock" },
  { symbol: "SHREECEM", name: "SHREECEM", type: "Stock" },
  { symbol: "SHRIRAMFIN", name: "SHRIRAMFIN", type: "Stock" },
  { symbol: "SIEMENS", name: "SIEMENS", type: "Stock" },
  { symbol: "SRF", name: "SRF", type: "Stock" },
  { symbol: "SUNTV", name: "SUNTV", type: "Stock" },
  { symbol: "SUNPHARMA", name: "SUNPHARMA", type: "Stock" },
  { symbol: "SYNGENE", name: "SYNGENE", type: "Stock" },
  { symbol: "TATACHEM", name: "TATACHEM", type: "Stock" },
  { symbol: "TATACOMM", name: "TATACOMM", type: "Stock" },
  { symbol: "TATACONSUM", name: "TATACONSUM", type: "Stock" },
  { symbol: "TATAMOTORS", name: "TATAMOTORS", type: "Stock" },
  { symbol: "TATAPOWER", name: "TATAPOWER", type: "Stock" },
  { symbol: "TATASTEEL", name: "TATASTEEL", type: "Stock" },
  { symbol: "TCS", name: "TCS", type: "Stock" },
  { symbol: "TECHM", name: "TECHM", type: "Stock" },
  { symbol: "TITAN", name: "TITAN", type: "Stock" },
  { symbol: "TORNTPHARM", name: "TORNTPHARM", type: "Stock" },
  { symbol: "TRENT", name: "TRENT", type: "Stock" },
  { symbol: "TVSMOTOR", name: "TVSMOTOR", type: "Stock" },
  { symbol: "UBL", name: "UBL", type: "Stock" },
  { symbol: "ULTRACEMCO", name: "ULTRACEMCO", type: "Stock" },
  { symbol: "UPL", name: "UPL", type: "Stock" },
  { symbol: "VEDL", name: "VEDL", type: "Stock" },
  { symbol: "VOLTAS", name: "VOLTAS", type: "Stock" },
  { symbol: "WIPRO", name: "WIPRO", type: "Stock" },
  { symbol: "ZEEL", name: "ZEEL", type: "Stock" },
  { symbol: "ZYDUSLIFE", name: "ZYDUSLIFE", type: "Stock" },
];

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Search Autocomplete State
  const [searchQuery, setSearchQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<typeof INDIAN_MARKET_ASSETS>([]);
  const searchRef = useRef<HTMLDivElement>(null);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [hasNotification, setHasNotification] = useState(true);
  const [isMarketOpen, setIsMarketOpen] = useState(false);

  // Kill Switch State
  const [isKillSwitchModalOpen, setIsKillSwitchModalOpen] = useState(false);
  const [isSystemHalted, setIsSystemHalted] = useState(false);

  const handleKillSwitch = () => {
    setIsSystemHalted(true);
    setIsKillSwitchModalOpen(false);
    toast.error("SYSTEM HALTED. All open positions closed.");
    localStorage.setItem("kill_switch_active", "true");
  };

  useEffect(() => {
    if (localStorage.getItem("kill_switch_active") === "true") {
      setIsSystemHalted(true);
    }
  }, []);

  const resumeTrading = () => {
    setIsSystemHalted(false);
    toast.success("SYSTEM RESUMED. Trading engine re-activated.");
    localStorage.removeItem("kill_switch_active");
  };

  // Check Market Status (IST 9:15 to 15:30 weekdays)
  useEffect(() => {
    const checkMarketStatus = () => {
      const now = new Date();
      const options = { timeZone: 'Asia/Kolkata' };
      const istTime = new Date(now.toLocaleString('en-US', options));
      const day = istTime.getDay();
      const hours = istTime.getHours();
      const minutes = istTime.getMinutes();
      const timeInMinutes = hours * 60 + minutes;
      
      const isOpen = day >= 1 && day <= 5 && timeInMinutes >= (9 * 60 + 15) && timeInMinutes <= (15 * 60 + 30);
      setIsMarketOpen(isOpen);
    };
    
    checkMarketStatus();
    const interval = setInterval(checkMarketStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcut for search
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => document.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  // Close menus on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
        setIsSearchFocused(false);
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

  const selectAsset = (asset: typeof INDIAN_MARKET_ASSETS[0]) => {
    setSearchQuery(asset.symbol);
    setShowSuggestions(false);
    setIsSearchFocused(false);
    
    // Update the URL to include the selected symbol
    const params = new URLSearchParams(window.location.search);
    params.set('symbol', asset.symbol);
    
    router.push(`${pathname}?${params.toString()}`);
  };

  // ADVANCED SEARCH: Allow user to press Enter to search for ANY symbol!
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim() !== '') {
      const sym = searchQuery.trim().toUpperCase();
      setShowSuggestions(false);
      setIsSearchFocused(false);
      
      const params = new URLSearchParams(window.location.search);
      params.set('symbol', sym);
      
      router.push(`${pathname}?${params.toString()}`);
    }
    if (e.key === 'Escape') {
      setShowSuggestions(false);
      setIsSearchFocused(false);
      searchInputRef.current?.blur();
    }
  };

  return (
    <>
      <header className="h-[var(--header-height)] bg-card/60 backdrop-blur-xl border-b border-border/50 flex items-center justify-between px-6 sticky top-0 z-50 shadow-sm transition-colors duration-300">
      <div className="flex items-center gap-6">
        {/* Market Status Indicator */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/30 border border-border/50">
          <div className="relative flex h-2 w-2">
            {isMarketOpen && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
            )}
            <span className={`relative inline-flex rounded-full h-2 w-2 transition-colors duration-300 ${isMarketOpen ? 'bg-success shadow-[0_0_8px_var(--success)]' : 'bg-muted-foreground'}`}></span>
          </div>
          <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">
            {isMarketOpen ? 'Market Open' : 'Market Closed'}
          </span>
        </div>

        {/* Institutional Level Search Box in Header */}
        {pathname !== "/strategy" && (
          <div className="relative" ref={searchRef}>

            <Search className={`w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 transition-colors duration-300 ${isSearchFocused ? 'text-primary' : 'text-muted-foreground'}`} />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              onFocus={() => {
                setIsSearchFocused(true);
                if (searchQuery) handleSearchChange(searchQuery);
              }}
              onKeyDown={handleKeyDown}
              placeholder="Search symbols..."
              className="w-72 bg-muted/30 border border-border/50 rounded-lg pl-10 pr-12 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent transition-all duration-300 hover:bg-muted/50 text-foreground"
            />
            
            {/* Clear Search Button */}
            {searchQuery && (
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setSearchQuery("");
                  setShowSuggestions(false);
                  setTimeout(() => searchInputRef.current?.focus(), 0);
                }}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors z-20 cursor-pointer"
              >
                <XCircle className="w-4 h-4" />
              </button>
            )}

            {/* Autocomplete Suggestions with Framer Motion */}
            <AnimatePresence>
              {showSuggestions && suggestions.length > 0 && (
                <motion.div 
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  className="absolute z-50 mt-2 w-full max-h-[400px] bg-card border border-border/50 rounded-xl shadow-2xl overflow-y-auto backdrop-blur-2xl"
                >
                  <div className="p-2 space-y-1">
                    {suggestions.map((asset) => (
                      <button
                        key={asset.symbol}
                        onClick={() => selectAsset(asset)}
                        className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-muted/80 transition-colors flex justify-between items-center group"
                      >
                        <div className="flex flex-col">
                          <span className="font-bold text-foreground group-hover:text-primary transition-colors">{asset.symbol}</span>
                          <span className="text-[11px] text-muted-foreground">{asset.name}</span>
                        </div>
                        <span className={`text-[10px] px-2 py-1 rounded-md font-bold uppercase tracking-wider ${asset.type === 'Index' ? 'bg-primary/10 text-primary' : 'bg-success/10 text-success'}`}>
                          {asset.type}
                        </span>
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Quick Actions */}
        <div className="flex items-center gap-2 mr-2">
          {/* KILL SWITCH */}
          {isSystemHalted ? (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={resumeTrading}
              className="flex items-center gap-2 px-4 py-1.5 bg-muted border border-success/50 text-success rounded-lg text-xs font-bold mr-2 hover:bg-success/10 transition-colors shadow-[0_0_10px_rgba(16,185,129,0.2)]"
            >
              <Activity className="w-4 h-4" /> RESUME TRADING
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setIsKillSwitchModalOpen(true)}
              className="flex items-center gap-2 px-4 py-1.5 bg-destructive/10 border border-destructive/50 text-destructive rounded-lg text-xs font-bold mr-2 hover:bg-destructive hover:text-white transition-colors animate-pulse hover:animate-none shadow-[0_0_10px_rgba(239,68,68,0.3)]"
            >
              <ShieldAlert className="w-4 h-4" /> KILL SWITCH
            </motion.button>
          )}

          <Link href="/analytics">
            <motion.button 
              whileHover={{ scale: 1.1, rotate: 5 }}
              whileTap={{ scale: 0.95 }}
              title="Analytics" 
              className="p-2 rounded-lg hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
            >
              <Activity className="w-5 h-5" />
            </motion.button>
          </Link>
          <Link href="/journal">
            <motion.button 
              whileHover={{ scale: 1.1, rotate: 12 }}
              whileTap={{ scale: 0.95 }}
              title="Trading Journal" 
              className="p-2 rounded-lg hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
            >
              <BookOpen className="w-5 h-5" />
            </motion.button>
          </Link>
          <motion.button 
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setHasNotification(!hasNotification)}
            className="p-2 rounded-lg hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors relative"
          >
            <motion.div animate={hasNotification ? { rotate: [0, -10, 10, -10, 10, 0] } : {}} transition={{ duration: 0.5, repeat: hasNotification ? Infinity : 0, repeatDelay: 3 }}>
              <Bell className="w-5 h-5" />
            </motion.div>
            {hasNotification && (
              <span className="absolute top-2 right-2 w-2 h-2 bg-destructive rounded-full shadow-[0_0_8px_var(--destructive)]"></span>
            )}
          </motion.button>
        </div>
        
        <div className="h-8 w-px bg-border/50"></div>
        
        {/* User Profile Area with Dropdown */}
        <div className="relative" ref={menuRef}>
          <motion.div 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
            className="flex items-center gap-3 cursor-pointer p-1.5 rounded-lg hover:bg-muted/50 transition-colors duration-200"
          >
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center border border-border shadow-sm">
              <User className="w-5 h-5 text-white" />
            </div>
            <div className="hidden md:block">
              <p className="text-sm font-bold text-foreground leading-none mb-1">Trader X</p>
              <p className="text-[10px] uppercase tracking-wider text-primary font-bold">Ultra Pro</p>
            </div>
          </motion.div>

          {/* User Dropdown Menu with Framer Motion */}
          <AnimatePresence>
            {isUserMenuOpen && (
              <motion.div 
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className="absolute right-0 mt-2 w-56 bg-card border border-border/50 rounded-xl shadow-2xl overflow-hidden z-50 backdrop-blur-2xl"
              >
                <div className="px-4 py-4 border-b border-border/50 bg-muted/10">
                  <p className="text-sm font-bold text-foreground">Trader X</p>
                  <p className="text-xs text-muted-foreground mt-0.5">quant.trader@ai.bot</p>
                </div>
                <div className="py-2">
                  <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-3">
                    <User className="w-4 h-4 text-muted-foreground" />
                    Profile
                  </button>
                  <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-3">
                    <Settings className="w-4 h-4 text-muted-foreground" />
                    Settings
                  </button>
                  <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-3">
                    <CreditCard className="w-4 h-4 text-muted-foreground" />
                    Billing
                  </button>
                </div>
                <div className="border-t border-border/50 py-2">
                  <button className="w-full text-left px-4 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-3 font-medium">
                    <LogOut className="w-4 h-4" />
                    Log Out
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      </header>

      {/* KILL SWITCH MODAL */}
      <AnimatePresence>
        {isKillSwitchModalOpen && (
          <div className="fixed inset-0 z-[100]">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-black/20"
              onClick={() => setIsKillSwitchModalOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              className="absolute top-[80px] right-[220px] w-[350px] bg-card border border-destructive/30 rounded-2xl p-6 shadow-2xl flex flex-col items-center text-center origin-top-right"
            >
              <div className="w-16 h-16 bg-destructive/20 rounded-full flex items-center justify-center mb-4">
                <ShieldAlert className="w-8 h-8 text-destructive" />
              </div>
              <h2 className="text-xl font-black text-destructive uppercase tracking-wider mb-2">Emergency Halt</h2>
              <p className="text-sm text-muted-foreground mb-6">
                Are you sure you want to trigger the Kill Switch? This will instantly flatten all open positions at market price and halt all algorithmic trading.
              </p>
              <div className="flex gap-3 w-full">
                <button 
                  onClick={() => setIsKillSwitchModalOpen(false)} 
                  className="flex-1 py-3 bg-muted hover:bg-muted/80 rounded-xl text-sm font-bold transition-colors"
                >
                  CANCEL
                </button>
                <button 
                  onClick={handleKillSwitch}
                  className="flex-1 py-3 bg-destructive hover:bg-destructive/90 text-white rounded-xl text-sm font-bold transition-colors shadow-lg shadow-destructive/20 flex items-center justify-center gap-2"
                >
                  <XCircle className="w-4 h-4" /> EXECUTE HALT
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
