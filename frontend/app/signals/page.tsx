"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import {
  Brain,
  TrendingUp,
  TrendingDown,
  Clock,
  Zap,
  Shield,
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  BarChart2
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line
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
        setError("Failed to connect to the Python Bridge. Please ensure the backend is running.");
      } finally {
        setIsLoading(false);
      }
    };

    fetchSignals();
    const interval = setInterval(fetchSignals, 10000); // Refresh every 10 seconds

    return () => clearInterval(interval);
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />

      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-between items-center">
            <div>
              <h1 className="font-display font-bold text-2xl text-foreground flex items-center gap-2">
                <Brain className="w-6 h-6 text-primary animate-pulse-ring" />
                AI Intelligence Hub
              </h1>
              <p className="text-sm text-muted-foreground">Real-time signal generation and predictive analytics.</p>
            </div>
          </motion.div>

          {/* Top Row: Confidence Meter & Trend */}
          <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Confidence Meter */}
            <motion.div variants={itemVariants} className="stat-card p-6 flex flex-col justify-between border border-border/20 relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none transition-all duration-500 group-hover:bg-primary/10"></div>
              
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">AI Confidence</h3>
                <Activity className="w-5 h-5 text-primary" />
              </div>

              <div className="flex flex-col items-center justify-center space-y-2 flex-1">
                <div className="relative w-40 h-40">
                  <svg className="w-full h-full drop-shadow-md" viewBox="0 0 100 100">
                    <defs>
                      <linearGradient id="gaugeColor" x1="50" y1="95" x2="50" y2="5" gradientUnits="userSpaceOnUse">
                        <stop offset="0%" stopColor="var(--destructive)" />
                        <stop offset="50%" stopColor="var(--warning)" />
                        <stop offset="100%" stopColor="var(--success)" />
                      </linearGradient>
                      <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feComposite in="SourceGraphic" in2="blur" operator="over" />
                      </filter>
                    </defs>
                    {/* Background circle */}
                    <circle
                      cx="50"
                      cy="50"
                      r="45"
                      fill="none"
                      className="stroke-muted"
                      strokeWidth="6"
                    />

                    {/* Active Gauge (Continuous with full gradient) */}
                    <circle
                      cx="50"
                      cy="50"
                      r="45"
                      fill="none"
                      stroke="url(#gaugeColor)"
                      strokeWidth="6"
                      strokeDasharray="282.74"
                      strokeDashoffset={282.74 * (1 - confidence / 100)}
                      strokeLinecap="round"
                      transform="rotate(-90 50 50)"
                      className="transition-all duration-1000 ease-in-out"
                    />

                    {/* Glowing Pointer Dot at the end */}
                    <circle
                      cx={50 + 45 * Math.cos((confidence * 3.6 - 90) * Math.PI / 180)}
                      cy={50 + 45 * Math.sin((confidence * 3.6 - 90) * Math.PI / 180)}
                      r="5"
                      fill="#fff"
                      filter="url(#glow)"
                      className="transition-all duration-1000 ease-in-out"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center group-hover:scale-110 transition-transform duration-300">
                    <span className="font-display font-bold text-4xl tracking-tight text-foreground">{confidence}%</span>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-success mt-1">{status}</span>
                  </div>
                </div>
                <p className="text-sm font-bold text-foreground mt-2">{bias}</p>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground text-center max-w-[80%]">Model confidence is above the threshold (75%) for active trading.</p>
              </div>
            </motion.div>

            {/* Trend Visualization */}
            <motion.div variants={itemVariants} className="lg:col-span-2 stat-card rounded-xl p-6 space-y-4 border border-border/20 relative overflow-hidden group">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">Trend Strength Trajectory</h3>
                  <p className="text-xs text-muted-foreground">AI scoring of market trend conviction over the day.</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="badge badge-info bg-blue-500/10 text-blue-500 border border-blue-500/20 px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider">Scale: 0-100</span>
                </div>
              </div>

              <div className="h-56 w-full mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="colorTrend" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.5} vertical={false} />
                    <XAxis dataKey="name" stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={11} domain={[0, 100]} tickLine={false} axisLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "var(--card)", borderColor: "var(--border)", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
                      labelStyle={{ color: "var(--foreground)", fontWeight: "bold", marginBottom: "4px" }}
                      itemStyle={{ color: "var(--primary)" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="var(--primary)"
                      fillOpacity={1}
                      fill="url(#colorTrend)"
                      strokeWidth={3}
                      activeDot={{ r: 6, fill: "var(--primary)", strokeWidth: 2, stroke: "var(--background)" }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium opacity-70">Identifies trend continuations &bull; Timed execution signals</p>
              </div>
            </motion.div>
          </motion.div>

          {/* Signals Grid */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground mb-4 flex items-center gap-2">
              <Zap className="w-4 h-4 text-warning" />
              Live Generation Feed
            </h3>

            <div className="grid grid-cols-1 gap-4">
              {isLoading ? (
                <div className="p-8 stat-card rounded-xl border border-border/20 text-center flex flex-col items-center justify-center">
                   <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4"></div>
                   <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Intercepting signals...</p>
                </div>
              ) : error ? (
                <div className="p-8 stat-card rounded-xl border border-destructive/30 text-center flex flex-col items-center justify-center bg-destructive/5">
                  <Shield className="w-12 h-12 text-destructive mb-4 opacity-50" />
                  <p className="text-sm font-bold text-destructive">{error}</p>
                </div>
              ) : signals.length === 0 ? (
                <div className="p-8 stat-card rounded-xl border border-border/20 text-center flex flex-col items-center justify-center text-muted-foreground">
                  <Target className="w-12 h-12 mb-4 opacity-20" />
                  <p className="text-sm font-medium uppercase tracking-wider">Awaiting valid signals</p>
                  <p className="text-xs opacity-50 mt-1">Conditions not met for execution.</p>
                </div>
              ) : (
                <AnimatePresence>
                  {signals.map((signal, index) => (
                    <motion.div 
                      key={index} 
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      className="stat-card rounded-xl p-5 border border-border/20 hover:border-primary/50 transition-all duration-300 group hover:-translate-y-1 relative overflow-hidden"
                    >
                      <div className={`absolute top-0 left-0 w-1 h-full ${signal.bias === "BUY" ? "bg-gradient-to-b from-success to-emerald-600" : signal.bias === "SELL" ? "bg-gradient-to-b from-destructive to-rose-600" : "bg-gradient-to-b from-muted to-muted-foreground"}`}></div>
                      
                      <div className="flex flex-col md:flex-row justify-between gap-6 pl-2">
                        {/* Signal Badge & Symbol */}
                        <div className="flex items-start gap-4">
                          <div className={`w-12 h-12 rounded-xl flex items-center justify-center shadow-inner ${signal.bias === "BUY" ? "bg-success/10 text-success shadow-[inset_0_0_12px_rgba(16,185,129,0.2)]" :
                            signal.bias === "SELL" ? "bg-destructive/10 text-destructive shadow-[inset_0_0_12px_rgba(239,68,68,0.2)]" : "bg-muted/50 text-muted-foreground"
                            }`}>
                            {signal.bias === "BUY" ? <TrendingUp className="w-6 h-6" /> :
                              signal.bias === "SELL" ? <TrendingDown className="w-6 h-6" /> : <Clock className="w-6 h-6" />}
                          </div>
  
                          <div>
                            <div className="flex items-center gap-3">
                              <h4 className="font-display font-bold text-xl text-foreground tracking-tight">{signal.symbol}</h4>
                              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${signal.bias === "BUY" ? "bg-success/10 text-success border-success/20" :
                                signal.bias === "SELL" ? "bg-destructive/10 text-destructive border-destructive/20" : "bg-muted text-muted-foreground border-border"
                                }`}>
                                {signal.type}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 mt-1.5 text-xs">
                              <p className="font-medium text-foreground">Bias: <span className={signal.bias === 'BUY' ? 'text-success font-bold' : signal.bias === 'SELL' ? 'text-destructive font-bold' : ''}>{signal.bias}</span></p>
                              <span className="text-muted-foreground/30">•</span>
                              <p className="text-muted-foreground font-medium">Strength: {signal.strength}</p>
                            </div>
                            <p className="text-[10px] font-mono text-muted-foreground flex items-center gap-1.5 mt-2 opacity-70">
                              <Clock className="w-3 h-3" /> {signal.time}
                            </p>
                          </div>
                        </div>
  
                        {/* Confidence Meter */}
                        <div className="flex flex-col items-end gap-1.5 justify-center md:pr-4">
                          <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Conviction</span>
                          <div className="flex items-center gap-3">
                            <div className="w-32 bg-muted/50 h-2.5 rounded-full overflow-hidden shadow-inner">
                              <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${signal.confidence}%` }}
                                transition={{ duration: 1, ease: "easeOut" }}
                                className={`h-full rounded-full relative ${signal.confidence > 75 ? "bg-success" :
                                  signal.confidence > 50 ? "bg-warning" : "bg-muted-foreground"
                                  }`}
                              >
                                <div className="absolute inset-0 bg-white/20"></div>
                              </motion.div>
                            </div>
                            <span className={`text-sm font-bold font-mono ${signal.confidence > 75 ? "text-success drop-shadow-[0_0_4px_rgba(16,185,129,0.5)]" : signal.confidence > 50 ? "text-warning" : "text-muted-foreground"}`}>{signal.confidence}%</span>
                          </div>
                        </div>
                      </div>
  
                      {/* Reasoning */}
                      <div className="mt-5 pt-4 border-t border-border/10 pl-2 bg-muted/5 rounded-b-xl -mx-5 -mb-5 px-5 pb-5">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-primary mb-2 flex items-center gap-1">
                          <Brain className="w-3 h-3" /> Neural Insight
                        </p>
                        <p className="text-sm text-foreground/90 leading-relaxed font-medium">{signal.reason}</p>
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
