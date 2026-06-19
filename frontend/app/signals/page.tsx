"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import {
  Brain, TrendingUp, TrendingDown, Clock, Zap, Target,
  Activity, Radar, Cpu, Crosshair, BarChart3, Fingerprint, Layers
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import { motion, AnimatePresence } from "framer-motion";

export default function Signals() {
  const [confidence, setConfidence] = useState(0);
  const [status, setStatus] = useState("Scanning...");
  const [bias, setBias] = useState("Analyzing market conditions...");
  const [trendData, setTrendData] = useState<any[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Mock Market Matrix Data
  const marketMatrix = {
    longShortRatio: 68,
    volatilityIndex: 14.2,
    liquidityScore: "High",
    activeModels: 4
  };

  useEffect(() => {
    const fetchSignals = async () => {
      try {
        const res = await fetch('/api/signals');
        const data = await res.json();

        if (data && !data.error) {
          setConfidence(data.confidence);
          setStatus(data.status);
          setBias(data.bias);
          setTrendData(data.trendData);
          setSignals(data.signals);
          setError(null);
        } else if (data && data.error) {
          setError(data.error);
        }
      } catch (error) {
        console.error("Failed to fetch signals:", error);
        setError("Connection Interrupted. Awaiting Neural Link...");
      } finally {
        setIsLoading(false);
      }
    };

    fetchSignals();
    const interval = setInterval(fetchSignals, 5000); // Faster refresh for institutional feel
    return () => clearInterval(interval);
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.05 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 15 },
    show: { opacity: 1, y: 0 }
  };

  // Generate a mock Alpha Score based on signal confidence
  const getAlphaScore = (conf: number) => ((conf / 100) * 9.9).toFixed(1);

  return (
    <div className="flex h-screen bg-[#050505] text-foreground selection:bg-primary/30">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden relative">
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none z-0"></div>
        
        <Header />

        <main className="flex-1 overflow-y-auto p-6 space-y-6 relative z-10 custom-scrollbar">
          
          {/* Header Banner */}
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-between items-end border-b border-border/20 pb-4">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <div className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-success shadow-[0_0_8px_var(--success)]"></span>
                </div>
                <h1 className="font-display font-black text-2xl tracking-tighter text-foreground uppercase">
                  Alpha Signals
                </h1>
              </div>
              <p className="text-xs font-mono text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5" /> Neural Network Active &bull; Latency: 14ms
              </p>
            </div>

            <div className="flex gap-4">
               <div className="bg-background/80 backdrop-blur-md border border-border/30 px-4 py-2 rounded-lg flex items-center gap-3 shadow-inner">
                 <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 4, ease: "linear" }}>
                    <Radar className="w-4 h-4 text-primary" />
                 </motion.div>
                 <div className="flex flex-col text-right">
                   <span className="text-[9px] uppercase tracking-widest text-muted-foreground font-bold">Scanning</span>
                   <span className="text-xs font-mono text-foreground font-bold">{signals.length} Targets</span>
                 </div>
               </div>
            </div>
          </motion.div>

          {/* Top Row: Intelligence Metrics */}
          <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* 1. Multi-Ring AI Core */}
            <motion.div variants={itemVariants} className="stat-card p-6 flex flex-col justify-between border border-border/20 relative overflow-hidden group bg-gradient-to-br from-background to-muted/10">
              <div className="absolute -top-10 -right-10 w-40 h-40 bg-primary/10 rounded-full blur-3xl pointer-events-none group-hover:bg-primary/20 transition-all duration-700"></div>
              
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-display font-bold text-xs tracking-widest uppercase text-muted-foreground">Conviction Core</h3>
                <Fingerprint className="w-4 h-4 text-primary opacity-50" />
              </div>

              <div className="flex flex-col items-center justify-center space-y-4 flex-1">
                <div className="relative w-40 h-40 group-hover:scale-105 transition-transform duration-500">
                  {/* Outer Ring (Decorative) */}
                  <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 20, ease: "linear" }} className="absolute inset-0 rounded-full border border-dashed border-border/30"></motion.div>
                  
                  {/* SVG Gauge */}
                  <svg className="absolute inset-0 w-full h-full drop-shadow-lg" viewBox="0 0 100 100">
                    <defs>
                      <mask id="progressMask">
                        <circle
                          cx="50" cy="50" r="42" fill="none"
                          stroke="#ffffff" strokeWidth="4"
                          strokeDasharray="263.89"
                          strokeDashoffset={263.89 * (1 - confidence / 100)}
                          strokeLinecap="round" transform="rotate(-90 50 50)"
                          className="transition-all duration-1000 ease-out"
                        />
                      </mask>
                      <filter id="coreGlow" x="-50%" y="-50%" width="200%" height="200%">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feComposite in="SourceGraphic" in2="blur" operator="over" />
                      </filter>
                    </defs>
                    <circle cx="50" cy="50" r="42" fill="none" className="stroke-muted/30" strokeWidth="4" />
                    
                    {/* True Circular Gradient using CSS conic-gradient masked by SVG */}
                    <foreignObject x="0" y="0" width="100" height="100" mask="url(#progressMask)">
                      <div className="w-full h-full" style={{ background: 'conic-gradient(var(--destructive) 0%, var(--warning) 50%, var(--success) 100%)' }}></div>
                    </foreignObject>
                    <circle
                      cx={50 + 42 * Math.cos((confidence * 3.6 - 90) * Math.PI / 180)}
                      cy={50 + 42 * Math.sin((confidence * 3.6 - 90) * Math.PI / 180)}
                      r="4" fill="#fff" filter="url(#coreGlow)"
                      className="transition-all duration-1000 ease-out"
                    />
                  </svg>
                  
                  {/* Core Value */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-mono font-black text-4xl tracking-tight text-foreground drop-shadow-[0_0_10px_rgba(255,255,255,0.2)]">
                      {confidence}<span className="text-xl text-muted-foreground font-normal ml-1">%</span>
                    </span>
                    <span className={`text-[9px] font-bold tracking-widest uppercase mt-1 ${confidence >= 75 ? "text-success drop-shadow-[0_0_5px_var(--success)]" : confidence >= 50 ? "text-warning" : "text-destructive"}`}>
                      {status}
                    </span>
                  </div>
                </div>
                <div className="text-center w-full">
                  <div className="h-1 w-full bg-muted/30 rounded-full overflow-hidden mb-2">
                    <div className="h-full bg-primary rounded-full w-[85%] opacity-50"></div>
                  </div>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{bias}</p>
                </div>
              </div>
            </motion.div>

            {/* 2. Trend Trajectory Area */}
            <motion.div variants={itemVariants} className="stat-card p-6 flex flex-col justify-between border border-border/20 relative overflow-hidden group bg-gradient-to-b from-background to-background">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-display font-bold text-xs tracking-widest uppercase text-muted-foreground">Trend Matrix</h3>
                <BarChart3 className="w-4 h-4 text-primary opacity-50" />
              </div>
              
              <div className="h-40 w-full mt-2 relative">
                {/* Overlay Scanning Line */}
                <motion.div 
                  initial={{ left: 0 }}
                  animate={{ left: "100%" }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                  className="absolute top-0 bottom-0 w-px bg-primary/50 shadow-[0_0_10px_var(--primary)] z-10 pointer-events-none"
                ></motion.div>
                
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="matrixGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" strokeOpacity={0.3} vertical={true} />
                    <XAxis dataKey="name" hide />
                    <YAxis hide domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#090a0f", borderColor: "var(--border)", borderRadius: "8px", fontSize: "12px", fontFamily: "monospace" }}
                      itemStyle={{ color: "var(--primary)", fontWeight: "bold" }}
                      cursor={{ stroke: 'var(--primary)', strokeWidth: 1, strokeDasharray: '4 4' }}
                    />
                    <Area
                      type="stepAfter"
                      dataKey="value"
                      stroke="var(--primary)"
                      fillOpacity={1}
                      fill="url(#matrixGradient)"
                      strokeWidth={2}
                      activeDot={{ r: 4, fill: "var(--background)", strokeWidth: 2, stroke: "var(--primary)" }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              
              <div className="flex justify-between items-center mt-4 pt-4 border-t border-border/10">
                <div className="flex flex-col">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Momentum</span>
                  <span className="text-xs font-mono font-bold text-success">+14.2%</span>
                </div>
                <div className="flex flex-col text-right">
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Velocity</span>
                  <span className="text-xs font-mono font-bold text-foreground">1.8x</span>
                </div>
              </div>
            </motion.div>

            {/* 3. Market Breadth / Liquidity Map */}
            <motion.div variants={itemVariants} className="stat-card p-6 flex flex-col justify-between border border-border/20 relative overflow-hidden group bg-gradient-to-bl from-background to-muted/10">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-xs tracking-widest uppercase text-muted-foreground">Sector Bias</h3>
                <Layers className="w-4 h-4 text-primary opacity-50" />
              </div>

              <div className="space-y-5 flex-1">
                {/* Long/Short Ratio */}
                <div>
                  <div className="flex justify-between text-[10px] font-mono font-bold uppercase mb-1.5">
                    <span className="text-success drop-shadow-[0_0_5px_var(--success)]">Longs {marketMatrix.longShortRatio}%</span>
                    <span className="text-destructive drop-shadow-[0_0_5px_var(--destructive)]">Shorts {100 - marketMatrix.longShortRatio}%</span>
                  </div>
                  <div className="h-2 w-full flex rounded-full overflow-hidden shadow-inner bg-background">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${marketMatrix.longShortRatio}%` }} transition={{ duration: 1 }} className="h-full bg-success"></motion.div>
                    <motion.div initial={{ width: 0 }} animate={{ width: `${100 - marketMatrix.longShortRatio}%` }} transition={{ duration: 1 }} className="h-full bg-destructive"></motion.div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div className="bg-muted/20 border border-border/30 rounded-lg p-3 text-center">
                    <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Vol Index</p>
                    <p className="text-sm font-mono font-bold text-foreground">{marketMatrix.volatilityIndex}</p>
                  </div>
                  <div className="bg-muted/20 border border-border/30 rounded-lg p-3 text-center">
                    <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Liquidity</p>
                    <p className="text-sm font-mono font-bold text-success">{marketMatrix.liquidityScore}</p>
                  </div>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-center gap-2 border-t border-border/10 pt-4">
                <div className="flex gap-1.5">
                  {[1,2,3,4].map(i => (
                     <div key={i} className="w-1.5 h-1.5 bg-primary rounded-full shadow-[0_0_5px_var(--primary)] animate-pulse" style={{ animationDelay: `${i * 0.2}s` }}></div>
                  ))}
                </div>
                <span className="text-[9px] uppercase tracking-widest font-mono text-muted-foreground">Engine Nodes Active</span>
              </div>
            </motion.div>

          </motion.div>

          {/* Bottom Row: High-Density Signal Feed */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mt-6">
            <div className="flex justify-between items-center mb-4 border-b border-border/10 pb-2">
              <h3 className="font-display font-bold text-sm tracking-widest uppercase text-foreground flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-warning" />
                Active Order Flow Intercepts
              </h3>
              <div className="flex gap-2">
                <span className="px-2 py-1 bg-success/10 text-success text-[10px] font-bold uppercase tracking-wider rounded border border-success/20 shadow-[inset_0_0_10px_rgba(16,185,129,0.1)]">Alpha Validated</span>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              {isLoading ? (
                <div className="p-12 stat-card rounded-xl border border-border/20 text-center flex flex-col items-center justify-center bg-background/50 backdrop-blur-sm">
                   <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4 shadow-[0_0_15px_var(--primary)]"></div>
                   <p className="text-xs font-mono font-bold text-muted-foreground uppercase tracking-widest animate-pulse">Decrypting Order Flow...</p>
                </div>
              ) : error ? (
                <div className="p-8 stat-card rounded-xl border border-destructive/30 text-center flex flex-col items-center justify-center bg-destructive/5 backdrop-blur-sm">
                  <Activity className="w-12 h-12 text-destructive mb-4 opacity-50" />
                  <p className="text-xs font-mono font-bold text-destructive uppercase tracking-widest">{error}</p>
                </div>
              ) : signals.length === 0 ? (
                <div className="p-12 stat-card rounded-xl border border-border/20 text-center flex flex-col items-center justify-center text-muted-foreground bg-background/50 backdrop-blur-sm">
                  <Target className="w-10 h-10 mb-4 opacity-20" />
                  <p className="text-xs font-mono font-bold uppercase tracking-widest">Awaiting Alpha Triggers</p>
                  <p className="text-[10px] opacity-50 mt-2 font-mono">No high-probability setups detected.</p>
                </div>
              ) : (
                <AnimatePresence>
                  {signals.map((signal, index) => (
                    <motion.div 
                      key={index} 
                      initial={{ opacity: 0, x: -20, height: 0 }}
                      animate={{ opacity: 1, x: 0, height: 'auto' }}
                      transition={{ delay: index * 0.05, type: 'spring', stiffness: 200, damping: 20 }}
                      className="group flex flex-col md:flex-row items-center justify-between p-4 rounded-xl border border-border/20 bg-card/60 backdrop-blur-md hover:bg-muted/30 hover:border-primary/40 transition-all duration-300 relative overflow-hidden"
                    >
                      {/* Left Accent Bar */}
                      <div className={`absolute left-0 top-0 bottom-0 w-1.5 ${signal.bias === "BUY" ? "bg-success" : signal.bias === "SELL" ? "bg-destructive" : "bg-muted-foreground"} opacity-70 group-hover:opacity-100 group-hover:shadow-[0_0_12px_currentColor] transition-all`}></div>

                      {/* Main Info */}
                      <div className="flex items-center gap-5 pl-3 w-full md:w-1/3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${signal.bias === "BUY" ? "bg-success/10 text-success border-success/30 shadow-[inset_0_0_15px_rgba(16,185,129,0.2)]" : signal.bias === "SELL" ? "bg-destructive/10 text-destructive border-destructive/30 shadow-[inset_0_0_15px_rgba(239,68,68,0.2)]" : "bg-muted border-border"}`}>
                          {signal.bias === "BUY" ? <TrendingUp className="w-5 h-5" /> : signal.bias === "SELL" ? <TrendingDown className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
                        </div>
                        <div className="flex flex-col">
                          <div className="flex items-center gap-2">
                            <span className="font-display font-black text-lg tracking-tight text-foreground">{signal.symbol}</span>
                            <span className="text-[9px] uppercase tracking-widest text-muted-foreground border border-border/50 px-1.5 py-0.5 rounded bg-background">{signal.type}</span>
                          </div>
                          <span className="text-[10px] font-mono text-muted-foreground flex items-center gap-1 opacity-70">
                            <Clock className="w-3 h-3" /> {signal.time}
                          </span>
                        </div>
                      </div>

                      {/* Middle: Reasoning (Ultra-Dense) */}
                      <div className="flex-1 px-5 my-3 md:my-0 border-l border-r border-border/10 hidden md:flex flex-col justify-center">
                        <div className="flex items-center gap-2 mb-1">
                          <Brain className="w-3.5 h-3.5 text-primary opacity-70" />
                          <span className="text-[9px] uppercase tracking-widest text-primary font-bold">Neural Insight</span>
                        </div>
                        <p className="text-[11px] text-muted-foreground font-medium leading-relaxed line-clamp-2 pr-4">{signal.reason}</p>
                      </div>

                      {/* Right: Quant Metrics */}
                      <div className="flex items-center gap-6 w-full md:w-auto justify-between md:justify-end pr-2">
                        {/* Alpha Score */}
                        <div className="flex flex-col text-right">
                          <span className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1">Alpha</span>
                          <span className="text-sm font-mono font-bold text-foreground bg-background px-2 py-0.5 rounded border border-border/30 shadow-inner">
                            {getAlphaScore(signal.confidence)}<span className="text-muted-foreground text-[10px]">/10</span>
                          </span>
                        </div>

                        {/* R:R Ratio */}
                        <div className="flex flex-col text-right">
                          <span className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1">R:R</span>
                          <span className="text-sm font-mono font-bold text-foreground">1:2.5</span>
                        </div>

                        {/* Conviction Bar */}
                        <div className="flex flex-col text-right w-24">
                          <div className="flex justify-between items-center mb-1">
                            <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Score</span>
                            <span className={`text-[10px] font-mono font-bold ${signal.confidence > 75 ? "text-success" : signal.confidence > 50 ? "text-warning" : "text-muted-foreground"}`}>{signal.confidence}%</span>
                          </div>
                          <div className="h-1.5 w-full bg-background rounded-full overflow-hidden border border-border/20 shadow-inner">
                            <motion.div initial={{ width: 0 }} animate={{ width: `${signal.confidence}%` }} transition={{ duration: 1, ease: "easeOut" }} className={`h-full ${signal.confidence > 75 ? "bg-success shadow-[0_0_8px_var(--success)]" : signal.confidence > 50 ? "bg-warning" : "bg-muted-foreground"}`}></motion.div>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              )}
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  );
}
