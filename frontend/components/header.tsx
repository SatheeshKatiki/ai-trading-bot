"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, Search, User, BookOpen, LogOut, Settings, CreditCard } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";

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

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Search Autocomplete State
  const [searchQuery, setSearchQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const searchRef = useRef<HTMLDivElement>(null);

  // Close menus on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
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
    setSearchQuery(asset.symbol);
    setShowSuggestions(false);
    
    // Update the URL to include the selected symbol!
    const params = new URLSearchParams(window.location.search);
    params.set('symbol', asset.symbol);
    
    router.push(`${pathname}?${params.toString()}`);
  };

  // ADVANCED SEARCH: Allow user to press Enter to search for ANY symbol!
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim() !== '') {
      const sym = searchQuery.trim().toUpperCase();
      setShowSuggestions(false);
      
      const params = new URLSearchParams(window.location.search);
      params.set('symbol', sym);
      
      router.push(`${pathname}?${params.toString()}`);
    }
  };

  return (
    <header className="h-16 bg-card/30 backdrop-blur-xl border-b border-border/50 flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        {/* Institutional Level Search Box in Header */}
        {pathname !== "/strategy" && (
          <div className="relative" ref={searchRef}>
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              onFocus={() => searchQuery && handleSearchChange(searchQuery)}
              onKeyDown={handleKeyDown}
              placeholder="Search symbols (Press Enter to search)..."
              className="w-64 bg-muted/30 border border-border/50 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent transition-all duration-200"
            />

            {/* Autocomplete Suggestions */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-50 mt-2 w-72 max-h-60 bg-[#111318] border border-border/50 rounded-lg shadow-xl overflow-y-auto backdrop-blur-xl">
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
        )}
      </div>

      <div className="flex items-center gap-4">
        <button className="p-2 rounded-lg hover:bg-muted/50 transition-colors duration-200 text-muted-foreground hover:text-foreground">
          <BookOpen className="w-5 h-5" />
        </button>
        <button className="p-2 rounded-lg hover:bg-muted/50 transition-colors duration-200 text-muted-foreground hover:text-foreground relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-destructive rounded-full"></span>
        </button>
        
        <div className="h-8 w-px bg-border/50"></div>
        
        {/* User Profile Area with Dropdown */}
        <div className="relative" ref={menuRef}>
          <div 
            onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
            className="flex items-center gap-3 cursor-pointer p-1.5 rounded-lg hover:bg-muted/50 transition-colors duration-200"
          >
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center">
              <User className="w-5 h-5 text-foreground" />
            </div>
            <div className="hidden md:block">
              <p className="text-sm font-medium text-foreground">Trader X</p>
              <p className="text-xs text-muted-foreground">Pro Account</p>
            </div>
          </div>

          {/* User Dropdown Menu */}
          {isUserMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 bg-[#111318] border border-border/50 rounded-lg shadow-xl overflow-hidden z-50 backdrop-blur-xl">
              <div className="px-4 py-3 border-b border-border/50">
                <p className="text-sm font-bold text-white">Trader X</p>
                <p className="text-xs text-muted-foreground">trader@pro.com</p>
              </div>
              <div className="py-1">
                <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2">
                  <User className="w-4 h-4 text-muted-foreground" />
                  Profile
                </button>
                <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2">
                  <Settings className="w-4 h-4 text-muted-foreground" />
                  Settings
                </button>
                <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-muted-foreground" />
                  Billing
                </button>
              </div>
              <div className="border-t border-border/50 py-1">
                <button className="w-full text-left px-4 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-2">
                  <LogOut className="w-4 h-4" />
                  Log Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
