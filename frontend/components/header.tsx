"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, Search, User, BookOpen, LogOut, Settings, CreditCard, Command, Activity } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";

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
            <motion.div 
              className={`absolute inset-0 rounded-lg bg-primary/20 -z-10 blur-sm transition-opacity duration-300 ${isSearchFocused ? 'opacity-100' : 'opacity-0'}`}
              layoutId="search-glow"
            />
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
            
            {/* Keyboard shortcut hint */}
            {!isSearchFocused && !searchQuery && (
              <div className="absolute right-3 top-1/2 transform -translate-y-1/2 flex items-center gap-1 opacity-50 pointer-events-none">
                <Command className="w-3 h-3" />
                <span className="text-[10px] font-bold">K</span>
              </div>
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
  );
}
