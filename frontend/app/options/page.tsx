"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { Brain, ShieldAlert, LineChart, TrendingUp, TrendingDown, Info, Zap } from "lucide-react";

export default function OptionsDesk() {
  const [loading, setLoading] = useState(true);
  const [chainData, setChainData] = useState<any>(null);
  const [symbol, setSymbol] = useState("NSE:BANKNIFTY-INDEX");

  useEffect(() => {
    fetchOptions();
  }, [symbol]);

  const fetchOptions = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/option-chain?symbol=${symbol}`);
      const data = await res.json();
      setChainData(data);
    } catch (error) {
      console.error(error);
    }
    setLoading(false);
  };

  // Generate Payoff Graph Data (Simulated Straddle Payoff)
  const getPayoffData = () => {
    if (!chainData) return [];
    const underlying = chainData.underlying_price;
    const data = [];
    const range = 1000;
    
    // Simulate Straddle (Buy ATM Call + Buy ATM Put)
    const atmStrike = chainData.chain.reduce((prev: any, curr: any) => 
      Math.abs(curr.strike - underlying) < Math.abs(prev.strike - underlying) ? curr : prev
    );
    
    const premiumPaid = atmStrike.call.ltp + atmStrike.put.ltp;
    
    for (let price = underlying - range; price <= underlying + range; price += 50) {
      // Call Payoff = Max(0, Price - Strike) - Premium
      const callPayoff = Math.max(0, price - atmStrike.strike) - atmStrike.call.ltp;
      // Put Payoff = Max(0, Strike - Price) - Premium
      const putPayoff = Math.max(0, atmStrike.strike - price) - atmStrike.put.ltp;
      
      const totalPayoff = callPayoff + putPayoff;
      data.push({
        price: Math.round(price),
        payoff: Math.round(totalPayoff),
        premium: premiumPaid
      });
    }
    return data;
  };

  const payoffData = getPayoffData();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <div className="flex-1 overflow-y-auto p-4 md:p-8 bg-background relative z-10 w-full">
      <div className="w-full space-y-6">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 text-xs font-bold uppercase tracking-widest mb-4">
              <Zap className="w-3.5 h-3.5" /> Options Analytics
            </div>
            <h1 className="text-4xl font-display font-black tracking-tight text-foreground">
              Options Desk
            </h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-lg">
              Live Greeks, chain visualization, and multi-leg strategy payoff modeling.
            </p>
          </div>
          
          <select 
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-card border border-border/50 rounded-lg px-4 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="NSE:BANKNIFTY-INDEX">BANKNIFTY</option>
            <option value="NSE:NIFTY50-INDEX">NIFTY 50</option>
            <option value="NSE:RELIANCE-EQ">RELIANCE</option>
          </select>
        </div>

        {loading ? (
          <div className="h-[400px] flex items-center justify-center glass-card rounded-2xl">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : (
          <>
            {/* Payoff Graph */}
            <div className="glass-card rounded-2xl p-6 border border-border/50">
              <div className="flex items-center gap-2 mb-6">
                <LineChart className="w-5 h-5 text-primary" />
                <h2 className="text-xl font-bold">ATM Long Straddle Payoff</h2>
              </div>
              
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={payoffData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorPayoff" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                        <stop offset="50%" stopColor="#10b981" stopOpacity={0}/>
                        <stop offset="100%" stopColor="#ef4444" stopOpacity={0.3}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                    <XAxis dataKey="price" stroke="#666" tick={{ fill: '#888' }} />
                    <YAxis stroke="#666" tick={{ fill: '#888' }} />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                      formatter={(value: number) => [`₹${value}`, 'PnL']}
                    />
                    <ReferenceLine y={0} stroke="#666" />
                    <ReferenceLine x={Math.round(chainData?.underlying_price)} stroke="#3b82f6" strokeDasharray="3 3" label={{ position: 'top', value: 'Current Price', fill: '#3b82f6' }} />
                    <Area 
                      type="monotone" 
                      dataKey="payoff" 
                      stroke="#10b981" 
                      fillOpacity={1} 
                      fill="url(#colorPayoff)" 
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Options Chain DataGrid */}
            <div className="glass-card rounded-2xl overflow-hidden border border-border/50">
              <div className="p-6 border-b border-border/50 flex justify-between items-center bg-muted/20">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Brain className="w-5 h-5 text-primary" /> Option Chain (Exp: {chainData?.expiry})
                </h2>
                <div className="text-sm font-mono text-muted-foreground">
                  Underlying: <span className="text-foreground font-bold">{chainData?.underlying_price.toFixed(2)}</span>
                </div>
              </div>
              
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-center">
                  <thead className="bg-muted/30 border-b border-border/50">
                    <tr>
                      <th colSpan={4} className="py-3 px-2 border-r border-border/50 text-success">CALLS (CE)</th>
                      <th className="py-3 px-2 bg-muted/50 w-24">STRIKE</th>
                      <th colSpan={4} className="py-3 px-2 border-l border-border/50 text-destructive">PUTS (PE)</th>
                    </tr>
                    <tr className="text-xs text-muted-foreground border-b border-border/50">
                      <th className="py-2 px-2">Delta</th>
                      <th className="py-2 px-2">Theta</th>
                      <th className="py-2 px-2">OI</th>
                      <th className="py-2 px-2 border-r border-border/50 font-bold text-foreground">LTP</th>
                      <th className="py-2 px-2 bg-muted/50">Price</th>
                      <th className="py-2 px-2 border-l border-border/50 font-bold text-foreground">LTP</th>
                      <th className="py-2 px-2">OI</th>
                      <th className="py-2 px-2">Theta</th>
                      <th className="py-2 px-2">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chainData?.chain.map((row: any, i: number) => {
                      const isITMCall = row.strike < chainData.underlying_price;
                      const isITMPut = row.strike > chainData.underlying_price;
                      
                      return (
                        <tr key={i} className="border-b border-border/20 hover:bg-muted/10 transition-colors">
                          <td className={`py-3 px-2 ${isITMCall ? 'bg-success/5' : ''}`}>{row.call.delta}</td>
                          <td className={`py-3 px-2 ${isITMCall ? 'bg-success/5' : ''}`}>{row.call.theta}</td>
                          <td className={`py-3 px-2 ${isITMCall ? 'bg-success/5' : ''}`}>{row.call.oi}</td>
                          <td className={`py-3 px-2 border-r border-border/50 font-bold text-success ${isITMCall ? 'bg-success/5' : ''}`}>₹{row.call.ltp}</td>
                          
                          <td className="py-3 px-2 bg-muted/30 font-bold text-foreground">{row.strike}</td>
                          
                          <td className={`py-3 px-2 border-l border-border/50 font-bold text-destructive ${isITMPut ? 'bg-destructive/5' : ''}`}>₹{row.put.ltp}</td>
                          <td className={`py-3 px-2 ${isITMPut ? 'bg-destructive/5' : ''}`}>{row.put.oi}</td>
                          <td className={`py-3 px-2 ${isITMPut ? 'bg-destructive/5' : ''}`}>{row.put.theta}</td>
                          <td className={`py-3 px-2 ${isITMPut ? 'bg-destructive/5' : ''}`}>{row.put.delta}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        </div>
      </div>
    </div>
    </div>
  );
}
