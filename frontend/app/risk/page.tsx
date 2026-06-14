"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import { 
  Shield, 
  AlertTriangle, 
  Zap, 
  Lock, 
  Unlock,
  Sliders,
  PieChart as PieChartIcon,
  BarChart2,
  RefreshCw
} from "lucide-react";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from "recharts";

const COLORS = ["#3b82f6", "#8b5cf6", "#10b981"];

export default function RiskManagement() {
  const [maxDailyLoss, setMaxDailyLoss] = useState("10000");
  const [riskPerTrade, setRiskPerTrade] = useState("1.5");
  const [maxPositions, setMaxPositions] = useState("5");
  const [circuitBreaker, setCircuitBreaker] = useState(true);
  
  const [exposureData, setExposureData] = useState<any[]>([]);
  const [drawdownData, setDrawdownData] = useState<any[]>([]);
  const [correlationMatrix, setCorrelationMatrix] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchRiskData = async () => {
      try {
        const res = await fetch('/api/risk');
        const data = await res.json();
        
        if (data && !data.error) {
          setMaxDailyLoss(data.limits.maxDailyLoss.toString());
          setRiskPerTrade(data.limits.riskPerTrade.toString());
          setMaxPositions(data.limits.maxPositions.toString());
          setCircuitBreaker(data.limits.circuitBreaker);
          
          setExposureData(data.exposureData);
          setDrawdownData(data.drawdownData);
          setCorrelationMatrix(data.correlationMatrix);
        }
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch risk data:", error);
      }
    };

    fetchRiskData();
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-screen bg-background text-foreground">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <div className="flex-1 flex items-center justify-center">
            <RefreshCw className="w-8 h-8 animate-spin text-primary" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground">Risk Management</h1>
              <p className="text-sm text-muted-foreground">Define your safety guards, position sizing, and exposure limits.</p>
            </div>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
              circuitBreaker ? "bg-success/10 border-success/20 text-success" : "bg-destructive/10 border-destructive/20 text-destructive"
            }`}>
              <Shield className="w-4 h-4" />
              <span className="text-xs font-medium">{circuitBreaker ? "Shield Active" : "Shield Inactive"}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Hard Limits & Controls */}
            <div className="lg:col-span-2 space-y-6">
              {/* Hard Limits Form */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Global Risk Controls</h3>
                  <Sliders className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Max Daily Loss (₹)</label>
                    <input
                      type="number"
                      value={maxDailyLoss}
                      onChange={(e) => setMaxDailyLoss(e.target.value)}
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Risk Per Trade (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={riskPerTrade}
                      onChange={(e) => setRiskPerTrade(e.target.value)}
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Max Open Positions</label>
                    <input
                      type="number"
                      value={maxPositions}
                      onChange={(e) => setMaxPositions(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>

                  <div className="flex items-end">
                    <button 
                      onClick={() => setCircuitBreaker(!circuitBreaker)}
                      className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                        circuitBreaker 
                          ? "bg-primary text-white hover:bg-primary/90" 
                          : "bg-primary text-white hover:bg-primary/90"
                      }`}
                    >
                      {circuitBreaker ? <Lock className="w-4 h-4" /> : <Unlock className="w-4 h-4" />}
                      {circuitBreaker ? "Engage Circuit Breaker" : "Release Circuit Breaker"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Correlation Matrix */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Asset Correlation Matrix</h3>
                  <Zap className="w-4 h-4 text-warning" />
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead>
                      <tr className="text-xs uppercase text-muted-foreground border-b border-border/20">
                        <th className="pb-3 font-medium">Asset</th>
                        <th className="pb-3 font-medium text-center">Nifty 50</th>
                        <th className="pb-3 font-medium text-center">Bank Nifty</th>
                        <th className="pb-3 font-medium text-center">IT Index</th>
                      </tr>
                    </thead>
                    <tbody>
                      {correlationMatrix.map((row, i) => (
                        <tr key={i} className="border-b border-border/10 text-xs">
                          <td className="py-3 font-medium text-foreground">{row.asset}</td>
                          {row.values.map((val: number, j: number) => (
                            <td 
                              key={j} 
                              className={`py-3 text-center font-bold ${
                                val === 1.0 ? "bg-success/10 text-success" :
                                val > 0.5 ? "bg-warning/10 text-warning" : "bg-destructive/5 text-destructive/70"
                              }`}
                            >
                              {val.toFixed(2)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-muted-foreground">High correlation (&gt;0.80) detected between Nifty 50 and Bank Nifty. Bot will avoid simultaneous entries.</p>
              </div>
            </div>

            {/* Right Column: Charts & Exposure */}
            <div className="space-y-6">
              {/* Exposure Chart */}
              <div className="glass-card rounded-xl p-6 border border-border/20">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-display font-bold text-lg text-foreground">Sector Exposure</h3>
                  <PieChartIcon className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={exposureData}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={70}
                        fill="#8884d8"
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {exposureData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip 
                        contentStyle={{ backgroundColor: "#090a0f", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px" }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-4 mt-2 flex-wrap">
                  {exposureData.map((entry, index) => (
                    <div key={index} className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[index] }}></div>
                      <span className="text-xs text-muted-foreground">{entry.name} ({entry.value}%)</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Drawdown Risk */}
              <div className="glass-card rounded-xl p-6 border border-border/20">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-display font-bold text-lg text-foreground">Intraday Drawdown %</h3>
                  <BarChart2 className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="h-[150px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={drawdownData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="day" stroke="rgba(255,255,255,0.3)" fontSize={11} />
                      <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: "#090a0f", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px" }}
                      />
                      <Bar 
                        dataKey="dd" 
                        fill="#ef4444"
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Warning Box */}
              <div className="glass-card rounded-xl p-6 border border-border/20 bg-warning/5 border-warning/10 space-y-2">
                <div className="flex items-center gap-2 text-warning font-medium">
                  <AlertTriangle className="w-4 h-4" />
                  <h4 className="text-sm">Dynamic Risk Reduction</h4>
                </div>
                <p className="text-xs text-muted-foreground">
                  The AI will automatically reduce position sizing by 50% if the strategy experiences a drawdown exceeding 5% in a single day.
                </p>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
