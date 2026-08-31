"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { Brain, Zap, RefreshCw, Layers, ShieldCheck } from "lucide-react";

interface OptionLeg {
  ltp: number;
  volume: number;
  oi: number;
  oichg: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}
interface OptionChainRow {
  strike: number;
  ce: OptionLeg;
  pe: OptionLeg;
}
interface OptionChainResponse {
  error?: string;
  symbol: string;
  underlying_price?: number;
  atm: number;
  maxPain: number;
  pcr: number;
  expiry: string;
  chain: OptionChainRow[];
}

export default function OptionsDesk() {
  const [loading, setLoading] = useState(true);
  const [chainData, setChainData] = useState<OptionChainResponse | null>(null);
  const [symbol, setSymbol] = useState("NSE:NIFTY50-INDEX");

  useEffect(() => {
    fetchOptions();
  }, [symbol]);

  const fetchOptions = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/option-chain?symbol=${symbol}`);
      const data: OptionChainResponse = await res.json();
      setChainData(data);
    } catch (error) {
      console.error(error);
    }
    setLoading(false);
  };

  const underlying = chainData?.underlying_price ?? 0;

  return (
    <div data-testid="options-page" className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 bg-background relative z-10 w-full">
          <div className="w-full space-y-6">
            
            {/* Header Banner */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2 border-b border-border/40 w-full">
              <div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 text-xs font-bold uppercase tracking-wider mb-2">
                  <Zap className="w-3.5 h-3.5" /> Live Option Chain & Greeks
                </div>
                <h1 className="text-3xl md:text-4xl font-display font-black tracking-tight text-foreground">
                  Options Desk
                </h1>
                <p className="text-muted-foreground mt-1 max-w-2xl text-sm md:text-base">
                  Real-time Open Interest (OI), Option Greeks (Delta, Theta, Gamma), and Strike Matrix.
                </p>
              </div>
              
              <div className="flex items-center gap-3">
                <select 
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="bg-card border border-border/60 rounded-xl px-4 py-2 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
                >
                  <option value="NSE:NIFTY50-INDEX">NIFTY 50</option>
                  <option value="NSE:BANKNIFTY-INDEX">BANKNIFTY</option>
                  <option value="NSE:RELIANCE-EQ">RELIANCE</option>
                </select>

                <button
                  onClick={fetchOptions}
                  disabled={loading}
                  className="p-2 bg-card border border-border/60 hover:bg-muted/50 rounded-xl text-foreground transition-all shadow-sm disabled:opacity-50"
                  title="Refresh Chain"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-primary' : ''}`} />
                </button>
              </div>
            </div>

            {/* Quick Metrics Bar */}
            {chainData && !loading && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
                <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Spot Price</span>
                  <div className="text-2xl font-black font-mono mt-1.5 text-foreground">
                    {underlying.toFixed(2)}
                  </div>
                </div>

                <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">ATM Strike</span>
                  <div className="text-2xl font-black font-mono mt-1.5 text-primary">
                    {chainData.atm || "-"}
                  </div>
                </div>

                <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">PCR Ratio</span>
                  <div className={`text-2xl font-black font-mono mt-1.5 ${chainData.pcr >= 1 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {chainData.pcr ? chainData.pcr.toFixed(2) : "-"}
                  </div>
                </div>

                <div className="bg-card/70 border border-border/60 rounded-2xl p-4 shadow-sm">
                  <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">Max Pain</span>
                  <div className="text-2xl font-black font-mono mt-1.5 text-amber-500">
                    {chainData.maxPain || "-"}
                  </div>
                </div>
              </div>
            )}

            {/* Loading State */}
            {loading ? (
              <div className="h-[400px] flex items-center justify-center bg-card/70 border border-border/50 rounded-2xl shadow-sm">
                <div className="flex flex-col items-center gap-3">
                  <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs text-muted-foreground font-semibold">Loading live options data...</span>
                </div>
              </div>
            ) : (
              /* Options Chain Full-Width DataGrid */
              <div className="bg-card/80 border border-border/60 rounded-2xl overflow-hidden shadow-md w-full">
                <div className="p-5 border-b border-border/60 flex flex-col md:flex-row justify-between items-start md:items-center gap-2 bg-muted/20">
                  <div className="flex items-center gap-2">
                    <Brain className="w-5 h-5 text-primary" />
                    <h2 className="text-lg font-bold text-foreground">
                      Option Chain Matrix <span className="text-xs font-mono font-normal text-muted-foreground">(Expiry: {chainData?.expiry || "Current Weekly"})</span>
                    </h2>
                  </div>
                  <div className="text-xs font-mono text-muted-foreground flex items-center gap-3">
                    <span>Spot: <strong className="text-foreground font-bold">{underlying.toFixed(2)}</strong></span>
                    <span className="text-border">|</span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> ITM Calls
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span> ITM Puts
                    </span>
                  </div>
                </div>
                
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-sm text-center border-collapse">
                    <thead>
                      <tr className="bg-muted/40 border-b border-border/60 text-xs uppercase tracking-wider font-bold">
                        <th colSpan={4} className="py-3 px-4 border-r border-border/60 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5">
                          CALLS (CE)
                        </th>
                        <th className="py-3 px-4 bg-muted/60 text-foreground w-28">
                          STRIKE
                        </th>
                        <th colSpan={4} className="py-3 px-4 border-l border-border/60 text-indigo-600 dark:text-indigo-400 bg-indigo-500/5">
                          PUTS (PE)
                        </th>
                      </tr>
                      <tr className="text-[11px] text-muted-foreground border-b border-border/60 font-semibold bg-muted/20">
                        <th className="py-2.5 px-3">Delta</th>
                        <th className="py-2.5 px-3">Theta</th>
                        <th className="py-2.5 px-3">OI</th>
                        <th className="py-2.5 px-4 border-r border-border/60 font-bold text-foreground">LTP (₹)</th>
                        <th className="py-2.5 px-3 bg-muted/40 font-bold text-foreground">Strike</th>
                        <th className="py-2.5 px-4 border-l border-border/60 font-bold text-foreground">LTP (₹)</th>
                        <th className="py-2.5 px-3">OI</th>
                        <th className="py-2.5 px-3">Theta</th>
                        <th className="py-2.5 px-3">Delta</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40 text-xs font-mono">
                      {chainData?.chain?.map((row, i) => {
                        const isITMCall = underlying > 0 && row.strike < underlying;
                        const isITMPut = underlying > 0 && row.strike > underlying;
                        const isATM = chainData.atm === row.strike;

                        return (
                          <tr 
                            key={i} 
                            className={`border-b border-border/30 hover:bg-muted/30 transition-colors ${
                              isATM ? 'bg-primary/5 font-bold' : ''
                            }`}
                          >
                            {/* CE Greeks & LTP */}
                            <td className={`py-3 px-3 ${isITMCall ? 'bg-emerald-500/10 font-semibold text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                              {(row.ce?.delta ?? 0).toFixed(2)}
                            </td>
                            <td className={`py-3 px-3 ${isITMCall ? 'bg-emerald-500/10 text-muted-foreground' : 'text-muted-foreground/80'}`}>
                              {(row.ce?.theta ?? 0).toFixed(2)}
                            </td>
                            <td className={`py-3 px-3 ${isITMCall ? 'bg-emerald-500/10' : ''}`}>
                              {(row.ce?.oi ?? 0).toLocaleString('en-IN')}
                            </td>
                            <td className={`py-3 px-4 border-r border-border/60 font-bold text-emerald-600 dark:text-emerald-400 text-sm ${isITMCall ? 'bg-emerald-500/15' : ''}`}>
                              ₹{(row.ce?.ltp ?? 0).toFixed(2)}
                            </td>

                            {/* STRIKE Center Column */}
                            <td className={`py-3 px-4 font-bold text-sm bg-muted/30 ${
                              isATM ? 'text-primary ring-1 ring-primary/40 bg-primary/10' : 'text-foreground'
                            }`}>
                              {row.strike}
                              {isATM && (
                                <span className="ml-1.5 text-[9px] px-1 py-0.2 rounded bg-primary text-primary-foreground uppercase">
                                  ATM
                                </span>
                              )}
                            </td>

                            {/* PE Greeks & LTP */}
                            <td className={`py-3 px-4 border-l border-border/60 font-bold text-indigo-600 dark:text-indigo-400 text-sm ${isITMPut ? 'bg-indigo-500/15' : ''}`}>
                              ₹{(row.pe?.ltp ?? 0).toFixed(2)}
                            </td>
                            <td className={`py-3 px-3 ${isITMPut ? 'bg-indigo-500/10' : ''}`}>
                              {(row.pe?.oi ?? 0).toLocaleString('en-IN')}
                            </td>
                            <td className={`py-3 px-3 ${isITMPut ? 'bg-indigo-500/10 text-muted-foreground' : 'text-muted-foreground/80'}`}>
                              {(row.pe?.theta ?? 0).toFixed(2)}
                            </td>
                            <td className={`py-3 px-3 ${isITMPut ? 'bg-indigo-500/10 font-semibold text-indigo-600 dark:text-indigo-400' : 'text-muted-foreground'}`}>
                              {(row.pe?.delta ?? 0).toFixed(2)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
