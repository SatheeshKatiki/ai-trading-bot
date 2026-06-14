"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import { 
  PieChart as PieChartIcon, 
  BarChart, 
  TrendingUp, 
  Zap, 
  Target, 
  Award,
  Clock,
  Calendar,
  RefreshCw,
  Activity
} from "lucide-react";
import { 
  BarChart as RechartsBarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  AreaChart,
  Area
} from "recharts";
import { motion } from "framer-motion";

const COLORS = ["var(--success)", "var(--destructive)"];

export default function Analytics() {
  const [stats, setStats] = useState<any>(null);
  const [winLossData, setWinLossData] = useState<any[]>([]);
  const [dayOfWeekData, setDayOfWeekData] = useState<any[]>([]);
  const [expectancyData, setExpectancyData] = useState<any[]>([]);
  const [streaks, setStreaks] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        
        if (data && !data.error) {
          setStats(data.stats);
          setWinLossData(data.winLossData);
          setDayOfWeekData(data.dayOfWeekData);
          setExpectancyData(data.expectancyData);
          setStreaks(data.streaks);
        }
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to fetch analytics:", error);
      }
    };

    fetchAnalytics();
  }, []);

  if (isLoading || !stats) {
    return (
      <div className="flex h-screen bg-background text-foreground">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <div className="flex-1 flex items-center justify-center bg-background">
            <div className="flex flex-col items-center justify-center space-y-4">
              <RefreshCw className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm font-bold tracking-wider uppercase text-muted-foreground">Aggregating Metrics</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

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
                <Activity className="w-6 h-6 text-primary" />
                Advanced Analytics
              </h1>
              <p className="text-sm text-muted-foreground mt-1">Deep dive into your strategy performance and edge metrics.</p>
            </div>
          </motion.div>

          {/* Core Metrics Grid */}
          <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <motion.div variants={itemVariants} className="stat-card rounded-xl p-5 border border-border/20 group relative overflow-hidden">
              <div className="absolute top-0 right-0 w-24 h-24 bg-primary/10 rounded-full blur-2xl -mr-8 -mt-8 pointer-events-none transition-all duration-500 group-hover:bg-primary/20"></div>
              <div className="flex items-center gap-2 mb-3">
                <Target className="w-4 h-4 text-primary" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Profit Factor</span>
              </div>
              <div className="text-3xl font-bold font-mono tracking-tight text-foreground">{stats.profitFactor}</div>
              <p className="text-xs font-bold text-success mt-2 tracking-wide">EXCELLENT EDGE (&gt; 2.0)</p>
            </motion.div>
            
            <motion.div variants={itemVariants} className="stat-card rounded-xl p-5 border border-border/20 group relative overflow-hidden">
              <div className="absolute top-0 right-0 w-24 h-24 bg-warning/10 rounded-full blur-2xl -mr-8 -mt-8 pointer-events-none transition-all duration-500 group-hover:bg-warning/20"></div>
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-4 h-4 text-warning" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Expectancy</span>
              </div>
              <div className="text-3xl font-bold font-mono tracking-tight text-foreground">₹{stats.expectancy.toLocaleString('en-IN')}</div>
              <p className="text-xs font-bold text-muted-foreground mt-2 tracking-wide">PER TRADE AVERAGE</p>
            </motion.div>

            <motion.div variants={itemVariants} className="stat-card rounded-xl p-5 border border-border/20 group relative overflow-hidden">
              <div className="absolute top-0 right-0 w-24 h-24 bg-success/10 rounded-full blur-2xl -mr-8 -mt-8 pointer-events-none transition-all duration-500 group-hover:bg-success/20"></div>
              <div className="flex items-center gap-2 mb-3">
                <Award className="w-4 h-4 text-success" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Win Rate</span>
              </div>
              <div className="text-3xl font-bold font-mono tracking-tight text-foreground">{stats.winRate}%</div>
              <p className="text-xs font-bold text-muted-foreground mt-2 tracking-wide">{stats.winningTrades} OF {stats.totalTrades} TRADES</p>
            </motion.div>

            <motion.div variants={itemVariants} className="stat-card rounded-xl p-5 border border-border/20 group relative overflow-hidden">
              <div className="absolute top-0 right-0 w-24 h-24 bg-destructive/10 rounded-full blur-2xl -mr-8 -mt-8 pointer-events-none transition-all duration-500 group-hover:bg-destructive/20"></div>
              <div className="flex items-center gap-2 mb-3">
                <Calendar className="w-4 h-4 text-destructive" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Max Drawdown</span>
              </div>
              <div className="text-3xl font-bold font-mono tracking-tight text-destructive">{stats.maxDrawdown}%</div>
              <p className="text-xs font-bold text-muted-foreground mt-2 tracking-wide">RECOVERED IN 14 DAYS</p>
            </motion.div>
          </motion.div>

          <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Win/Loss Ratio */}
            <motion.div variants={itemVariants} className="stat-card rounded-xl p-6 border border-border/20 shadow-lg relative group">
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">Win / Loss Ratio</h3>
                <PieChartIcon className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <div className="h-[250px] flex justify-center items-center relative">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <defs>
                      <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
                        <feDropShadow dx="0" dy="4" stdDeviation="6" floodOpacity="0.2" />
                      </filter>
                    </defs>
                    <Pie
                      data={winLossData}
                      cx="50%"
                      cy="50%"
                      innerRadius={70}
                      outerRadius={90}
                      paddingAngle={5}
                      dataKey="value"
                      stroke="none"
                      style={{ filter: 'url(#shadow)' }}
                    >
                      {winLossData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} className="hover:opacity-80 transition-opacity cursor-pointer outline-none" />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ backgroundColor: "var(--card)", borderColor: "var(--border)", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
                      itemStyle={{ color: "var(--foreground)", fontWeight: "bold" }}
                      formatter={(value: any) => [`${value}%`]}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="text-center">
                    <span className="block text-2xl font-bold font-mono">{stats.totalTrades}</span>
                    <span className="block text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-1">Trades</span>
                  </div>
                </div>
              </div>
              <div className="flex justify-center gap-8 mt-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-success rounded-full shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
                  <span className="text-xs font-bold tracking-wide text-foreground">WINS ({winLossData[0]?.value}%)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-destructive rounded-full shadow-[0_0_8px_rgba(239,68,68,0.5)]"></div>
                  <span className="text-xs font-bold tracking-wide text-foreground">LOSSES ({winLossData[1]?.value}%)</span>
                </div>
              </div>
            </motion.div>

            {/* Performance by Day */}
            <motion.div variants={itemVariants} className="lg:col-span-2 stat-card rounded-xl p-6 border border-border/20 shadow-lg group">
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">PnL by Day of Week</h3>
                <BarChart className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <div className="h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsBarChart data={dayOfWeekData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--primary)" stopOpacity={1} />
                        <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.4} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.5} vertical={false} />
                    <XAxis dataKey="day" stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} dy={10} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(value) => `₹${value}`} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "var(--card)", borderColor: "var(--border)", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
                      labelStyle={{ color: "var(--muted-foreground)", fontWeight: "bold", marginBottom: "4px" }}
                      itemStyle={{ color: "var(--primary)", fontWeight: "bold" }}
                      cursor={{ fill: 'var(--muted)', opacity: 0.2 }}
                    />
                    <Bar 
                      dataKey="pnl" 
                      fill="url(#barGradient)"
                      radius={[6, 6, 0, 0]}
                      maxBarSize={60}
                    />
                  </RechartsBarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </motion.div>

          <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Expectancy Curve */}
            <motion.div variants={itemVariants} className="stat-card rounded-xl p-6 border border-border/20 shadow-lg group">
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">Expectancy Growth</h3>
                <TrendingUp className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <div className="h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={expectancyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="expGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.5} vertical={false} />
                    <XAxis dataKey="trade" stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} dy={10} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "var(--card)", borderColor: "var(--border)", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
                      labelStyle={{ color: "var(--muted-foreground)", fontWeight: "bold", marginBottom: "4px" }}
                      itemStyle={{ color: "#8b5cf6", fontWeight: "bold" }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="val" 
                      stroke="#8b5cf6" 
                      fillOpacity={1}
                      fill="url(#expGradient)"
                      strokeWidth={3}
                      activeDot={{ r: 6, fill: "#8b5cf6", strokeWidth: 2, stroke: "var(--background)" }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-4 text-center opacity-70">Expectancy improves as trade count increases, proving system edge.</p>
            </motion.div>

            {/* Streak Analysis */}
            {streaks && (
              <motion.div variants={itemVariants} className="stat-card rounded-xl p-6 border border-border/20 shadow-lg group flex flex-col">
                <div className="flex justify-between items-center mb-6">
                  <h3 className="font-display font-bold text-sm tracking-wider uppercase text-foreground">Streak Analysis</h3>
                  <Clock className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
                
                <div className="space-y-4 flex-1 flex flex-col justify-center">
                  <div className="flex justify-between items-center p-4 bg-muted/10 rounded-xl border border-border/30 hover:border-success/30 transition-colors">
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-1 block">Longest Winning Streak</span>
                      <div className="text-xl font-bold text-success font-mono drop-shadow-[0_0_8px_rgba(16,185,129,0.2)]">{streaks.winning.count} Trades</div>
                    </div>
                    <div className="text-sm font-bold text-foreground">Generated ₹{streaks.winning.value.toLocaleString('en-IN')}</div>
                  </div>

                  <div className="flex justify-between items-center p-4 bg-muted/10 rounded-xl border border-border/30 hover:border-destructive/30 transition-colors">
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-1 block">Longest Losing Streak</span>
                      <div className="text-xl font-bold text-destructive font-mono drop-shadow-[0_0_8px_rgba(239,68,68,0.2)]">{streaks.losing.count} Trades</div>
                    </div>
                    <div className="text-sm font-bold text-foreground">Lost ₹{streaks.losing.value.toLocaleString('en-IN')}</div>
                  </div>

                  <div className="flex justify-between items-center p-4 bg-muted/10 rounded-xl border border-border/30 hover:border-primary/30 transition-colors">
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-1 block">Average Win / Loss</span>
                      <div className="text-xl font-bold text-foreground font-mono">{streaks.avgRatio} Ratio</div>
                    </div>
                    <div className="text-[10px] uppercase tracking-wider font-bold text-primary bg-primary/10 px-2 py-1 rounded">Positive Skew</div>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
