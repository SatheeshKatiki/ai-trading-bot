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
  RefreshCw
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
  Line
} from "recharts";

const COLORS = ["#10b981", "#ef4444"];

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
          <div>
            <h1 className="font-display font-bold text-2xl text-foreground">Advanced Analytics</h1>
            <p className="text-sm text-muted-foreground">Deep dive into your strategy performance and edge metrics.</p>
          </div>

          {/* Core Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-4 h-4 text-primary" />
                <span className="text-xs text-muted-foreground font-medium">Profit Factor</span>
              </div>
              <div className="text-2xl font-bold font-mono text-foreground">{stats.profitFactor}</div>
              <p className="text-xs text-success mt-1">Excellent edge (&gt; 2.0)</p>
            </div>
            
            <div className="glass-card rounded-xl p-4 border border-border/20">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-4 h-4 text-warning" />
                <span className="text-xs text-muted-foreground font-medium">Expectancy</span>
              </div>
              <div className="text-2xl font-bold font-mono text-foreground">₹{stats.expectancy.toLocaleString('en-IN')}</div>
              <p className="text-xs text-muted-foreground mt-1">Per trade average</p>
            </div>

            <div className="glass-card rounded-xl p-4 border border-border/20">
              <div className="flex items-center gap-2 mb-2">
                <Award className="w-4 h-4 text-success" />
                <span className="text-xs text-muted-foreground font-medium">Win Rate</span>
              </div>
              <div className="text-2xl font-bold font-mono text-foreground">{stats.winRate}%</div>
              <p className="text-xs text-muted-foreground mt-1">{stats.winningTrades} of {stats.totalTrades} trades</p>
            </div>

            <div className="glass-card rounded-xl p-4 border border-border/20">
              <div className="flex items-center gap-2 mb-2">
                <Calendar className="w-4 h-4 text-destructive" />
                <span className="text-xs text-muted-foreground font-medium">Max Drawdown</span>
              </div>
              <div className="text-2xl font-bold font-mono text-destructive">{stats.maxDrawdown}%</div>
              <p className="text-xs text-muted-foreground mt-1">Recovered in 14 days</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Win/Loss Ratio */}
            <div className="glass-card rounded-xl p-6 border border-border/20">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-lg text-foreground">Win / Loss Ratio</h3>
                <PieChartIcon className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="h-[250px] flex justify-center items-center">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={winLossData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      fill="#8884d8"
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {winLossData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ backgroundColor: "#090a0f", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex justify-center gap-6 mt-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-success rounded-full"></div>
                  <span className="text-xs text-foreground">Wins ({winLossData[0]?.value}%)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-destructive rounded-full"></div>
                  <span className="text-xs text-foreground">Losses ({winLossData[1]?.value}%)</span>
                </div>
              </div>
            </div>

            {/* Performance by Day */}
            <div className="lg:col-span-2 glass-card rounded-xl p-6 border border-border/20">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-lg text-foreground">PnL by Day of Week</h3>
                <BarChart className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsBarChart data={dayOfWeekData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="day" stroke="rgba(255,255,255,0.3)" fontSize={11} />
                    <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "#090a0f", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px" }}
                      labelStyle={{ color: "rgba(255,255,255,0.5)" }}
                    />
                    <Bar 
                      dataKey="pnl" 
                      fill="#3b82f6"
                      radius={[4, 4, 0, 0]}
                    />
                  </RechartsBarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Expectancy Curve */}
            <div className="glass-card rounded-xl p-6 border border-border/20">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-lg text-foreground">Expectancy Growth</h3>
                <TrendingUp className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={expectancyData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="trade" stroke="rgba(255,255,255,0.3)" fontSize={11} />
                    <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "#090a0f", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px" }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="val" 
                      stroke="#8b5cf6" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-muted-foreground mt-2">Expectancy improves as trade count increases, proving system edge.</p>
            </div>

            {/* Streak Analysis */}
            {streaks && (
              <div className="glass-card rounded-xl p-6 border border-border/20">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-display font-bold text-lg text-foreground">Streak Analysis</h3>
                  <Clock className="w-4 h-4 text-muted-foreground" />
                </div>
                
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-3 bg-muted/20 rounded-lg">
                    <div>
                      <span className="text-xs text-muted-foreground font-medium">Longest Winning Streak</span>
                      <div className="text-lg font-bold text-success font-mono">{streaks.winning.count} Trades</div>
                    </div>
                    <div className="text-xs text-muted-foreground">Generated ₹{streaks.winning.value.toLocaleString('en-IN')}</div>
                  </div>

                  <div className="flex justify-between items-center p-3 bg-muted/20 rounded-lg">
                    <div>
                      <span className="text-xs text-muted-foreground font-medium">Longest Losing Streak</span>
                      <div className="text-lg font-bold text-destructive font-mono">{streaks.losing.count} Trades</div>
                    </div>
                    <div className="text-xs text-muted-foreground">Lost ₹{streaks.losing.value.toLocaleString('en-IN')}</div>
                  </div>

                  <div className="flex justify-between items-center p-3 bg-muted/20 rounded-lg">
                    <div>
                      <span className="text-xs text-muted-foreground font-medium">Average Win / Loss</span>
                      <div className="text-lg font-bold text-foreground font-mono">{streaks.avgRatio} Ratio</div>
                    </div>
                    <div className="text-xs text-muted-foreground">Positive skew</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
