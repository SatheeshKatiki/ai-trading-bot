"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import { Search, ChevronDown, Sparkles, Check, Lock, Zap } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface OptionSymbolSelectorProps {
  baseSymbol: string;
  currentSymbol: string;
  spotPrice?: number;
  dualSyncMode: boolean;
  onSelectSymbol: (symbol: string) => void;
  onResetAiSync: () => void;
}

interface ContractItem {
  symbol: string;
  strike: number;
  type: "CE" | "PE";
  status: "ITM" | "ATM" | "OTM";
}

export function OptionSymbolSelector({
  baseSymbol,
  currentSymbol,
  spotPrice = 0,
  dualSyncMode,
  onSelectSymbol,
  onResetAiSync,
}: OptionSymbolSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<"ALL" | "CE" | "PE" | "ATM">("ALL");
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Generate available strikes around current spot price
  const contracts = useMemo(() => {
    const sym = baseSymbol.toUpperCase();
    // No spot, no strike ladder. This used to fall back to 52000 / 80000 /
    // 24350, so with the feed down it offered strikes centred on an invented
    // ATM -- with NIFTY near 23431 that is roughly 920 points wrong, and this
    // component picks the contract for a MANUAL order.
    if (!spotPrice || spotPrice <= 0) return [];
    const rawSpot = spotPrice;
    const step = sym.includes("BANK") || sym.includes("SENSEX") ? 100 : 50;
    const atmStrike = Math.round(rawSpot / step) * step;

    const list: ContractItem[] = [];
    const range = 15; // ±15 strikes

    for (let i = -range; i <= range; i++) {
      const strike = atmStrike + i * step;

      // Determine CE status
      let ceStatus: "ITM" | "ATM" | "OTM" = "OTM";
      if (Math.abs(strike - rawSpot) <= step / 2) ceStatus = "ATM";
      else if (strike < rawSpot) ceStatus = "ITM";

      list.push({
        symbol: `${sym} ${strike} CE`,
        strike,
        type: "CE",
        status: ceStatus,
      });

      // Determine PE status
      let peStatus: "ITM" | "ATM" | "OTM" = "OTM";
      if (Math.abs(strike - rawSpot) <= step / 2) peStatus = "ATM";
      else if (strike > rawSpot) peStatus = "ITM";

      list.push({
        symbol: `${sym} ${strike} PE`,
        strike,
        type: "PE",
        status: peStatus,
      });
    }

    return list.sort((a, b) => b.strike - a.strike);
  }, [baseSymbol, spotPrice]);

  // Filtered contracts
  const filteredContracts = useMemo(() => {
    return contracts.filter((c) => {
      const matchesSearch =
        c.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.strike.toString().includes(searchQuery);

      if (!matchesSearch) return false;

      if (filterType === "CE") return c.type === "CE";
      if (filterType === "PE") return c.type === "PE";
      if (filterType === "ATM") return c.status === "ATM";

      return true;
    });
  }, [contracts, searchQuery, filterType]);

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`cursor-pointer px-3 py-1.5 rounded-lg border text-xs font-bold font-mono transition-all flex items-center gap-2 shadow-sm ${
          dualSyncMode
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20"
            : "bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
        }`}
        title="Click to search and select Option Contract"
      >
        <span className="flex items-center gap-1.5">
          {dualSyncMode ? (
            <Sparkles className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
          ) : (
            <Lock className="w-3.5 h-3.5 text-amber-400" />
          )}
          <span className="tracking-tight">{currentSymbol}</span>
        </span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {/* Popover Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 top-full mt-2 w-80 bg-background/95 backdrop-blur-xl border border-border/80 rounded-xl shadow-2xl z-[300] overflow-hidden flex flex-col"
          >
            {/* Header / Search Input */}
            <div className="p-3 border-b border-border/50 bg-muted/20 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <Zap className="w-3 h-3 text-primary" /> Option Strike Selector
                </span>
                <span className="text-[10px] font-mono text-muted-foreground">
                  Spot: <strong className="text-foreground">{spotPrice ? spotPrice.toFixed(1) : "—"}</strong>
                </span>
              </div>

              {/* Search Bar */}
              <div className="relative flex items-center">
                <Search className="w-3.5 h-3.5 absolute left-2.5 text-muted-foreground" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search strike (e.g. 24400, PE, CE)..."
                  className="w-full bg-muted/40 border border-border/50 rounded-lg pl-8 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary font-mono"
                  autoFocus
                />
              </div>

              {/* Quick Reset to AI Sync Button */}
              <button
                onClick={() => {
                  onResetAiSync();
                  setIsOpen(false);
                }}
                className={`w-full py-1.5 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                  dualSyncMode
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                    : "bg-muted hover:bg-emerald-500/10 text-muted-foreground hover:text-emerald-400 border border-border/40 hover:border-emerald-500/30"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                <span>{dualSyncMode ? "✓ Auto AI Sync Active" : "Reset to AI Active Premium"}</span>
              </button>

              {/* Category Filter Tabs */}
              <div className="flex items-center gap-1 pt-1">
                {(["ALL", "CE", "PE", "ATM"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setFilterType(tab)}
                    className={`flex-1 py-1 text-[10px] font-bold rounded-md transition-all ${
                      filterType === tab
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    }`}
                  >
                    {tab === "CE" ? "CALLS" : tab === "PE" ? "PUTS" : tab}
                  </button>
                ))}
              </div>
            </div>

            {/* Strike Contracts List */}
            <div className="max-h-64 overflow-y-auto divide-y divide-border/20 custom-scrollbar p-1">
              {filteredContracts.length === 0 ? (
                <div className="p-4 text-center text-xs text-muted-foreground font-mono">
                  No option contracts match &quot;{searchQuery}&quot;
                </div>
              ) : (
                filteredContracts.map((contract) => {
                  const isSelected = currentSymbol === contract.symbol;
                  return (
                    <button
                      key={contract.symbol}
                      onClick={() => {
                        onSelectSymbol(contract.symbol);
                        setIsOpen(false);
                      }}
                      className={`w-full px-3 py-2 text-xs font-mono flex items-center justify-between transition-colors rounded-lg ${
                        isSelected
                          ? "bg-primary/20 text-primary font-bold"
                          : "hover:bg-muted/50 text-foreground"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-black ${
                            contract.type === "CE"
                              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                              : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                          }`}
                        >
                          {contract.type}
                        </span>
                        <span className="font-semibold">{contract.symbol}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold tracking-wider ${
                            contract.status === "ATM"
                              ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                              : contract.status === "ITM"
                              ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                              : "text-muted-foreground/60"
                          }`}
                        >
                          {contract.status}
                        </span>

                        {isSelected && <Check className="w-3.5 h-3.5 text-primary" />}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
