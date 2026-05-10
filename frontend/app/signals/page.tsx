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

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />

      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div>
            <h1 className="font-display font-bold text-2xl text-foreground">AI Intelligence Hub</h1>
            <p className="text-sm text-muted-foreground">Real-time signal generation and predictive analytics.</p>
          </div>

          {/* Top Row: Confidence Meter & Trend */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Confidence Meter */}
            <div className="glass-card rounded-xl p-6 space-y-6 flex flex-col justify-between border border-border/20">
              <div className="flex justify-between items-center">
                <h3 className="font-display font-bold text-lg text-foreground">AI Confidence</h3>
                <Brain className="w-5 h-5 text-primary" />
              </div>

              <div className="flex flex-col items-center justify-center space-y-2">
                <div className="relative w-40 h-40">
                  <svg className="w-full h-full" viewBox="0 0 100 100">
                    <defs>
                      <linearGradient id="gaugeColor" x1="50" y1="95" x2="50" y2="5" gradientUnits="userSpaceOnUse">
                        <stop offset="0%" stopColor="#fc0808e3" /> {/* Red at bottom */}
                        <stop offset="50%" stopColor="#f1750aff" /> {/* Yellow in middle */}
                        <stop offset="100%" stopColor="#22c55eff" /> {/* Green at top */}
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
                      stroke="hsl(var(--muted))"
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
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-display font-bold text-4xl text-foreground">{confidence}%</span>
                    <span className="text-xs font-medium text-success">{status}</span>
                  </div>
                </div>
                <p className="text-sm font-medium text-foreground mt-2">{bias}</p>
                <p className="text-xs text-muted-foreground text-center">Model confidence is above the threshold (75%) for active trading.</p>
              </div>
            </div>

            {/* Trend Visualization */}
            <div className="lg:col-span-2 glass-card rounded-xl p-6 space-y-4 border border-border/20">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-display font-bold text-lg text-foreground">Trend Strength Trajectory</h3>
                  <p className="text-xs text-muted-foreground">AI scoring of market trend conviction over the day.</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Scale: 0-100</span>
                </div>
              </div>

              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "hsl(var(--background))", borderColor: "hsl(var(--border))", borderRadius: "8px" }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#ff4d4d"
                      strokeWidth={3}
                      dot={{ r: 4, fill: "#ff4d4d", strokeWidth: 0 }}
                      activeDot={{ r: 6, fill: "#ff4d4d", strokeWidth: 0 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2">
                <p className="text-xs text-muted-foreground">[ Identifies trend continuations and potential reversals. Helps in timing entries and exits based on conviction. ]</p>
              </div>
            </div>
          </div>

          {/* Signals Grid */}
          <div>
            <h3 className="font-display font-bold text-lg text-foreground mb-4">Live Generation Feed</h3>

            <div className="grid grid-cols-1 gap-6">
              {isLoading ? (
                <div className="p-6 glass-card rounded-xl border border-border/20 text-center text-muted-foreground">
                  Loading active signals...
                </div>
              ) : error ? (
                <div className="p-6 glass-card rounded-xl border border-destructive/20 text-center text-destructive">
                  {error}
                </div>
              ) : signals.length === 0 ? (
                <div className="p-6 glass-card rounded-xl border border-border/20 text-center text-muted-foreground">
                  No active signals generated yet.
                </div>
              ) : (
                signals.map((signal, index) => (
                  <div key={index} className="glass-card rounded-xl p-6 border border-border/20 hover:border-primary/30 transition-colors duration-200">
                    <div className="flex flex-col md:flex-row justify-between gap-4">
                      {/* Signal Badge & Symbol */}
                      <div className="flex items-start gap-4">
                        <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${signal.bias === "BUY" ? "bg-success/10 text-success" :
                          signal.bias === "SELL" ? "bg-destructive/10 text-destructive" : "bg-muted/50 text-muted-foreground"
                          }`}>
                          {signal.bias === "BUY" ? <TrendingUp className="w-6 h-6" /> :
                            signal.bias === "SELL" ? <TrendingDown className="w-6 h-6" /> : <Clock className="w-6 h-6" />}
                        </div>

                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="font-display font-bold text-lg text-foreground">{signal.symbol}</h4>
                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${signal.bias === "BUY" ? "bg-success/10 text-success" :
                              signal.bias === "SELL" ? "bg-destructive/10 text-destructive" : "bg-muted/50 text-muted-foreground"
                              }`}>
                              {signal.type}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">Bias: {signal.bias} | Strength: {signal.strength}</p>
                          <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                            <Clock className="w-3 h-3" /> {signal.time}
                          </p>
                        </div>
                      </div>

                      {/* Confidence Meter */}
                      <div className="flex flex-col items-end gap-1">
                        <span className="text-xs text-muted-foreground font-medium">AI Confidence</span>
                        <div className="flex items-center gap-2">
                          <div className="w-32 bg-muted/30 h-2 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${signal.confidence > 75 ? "bg-success" :
                                signal.confidence > 50 ? "bg-warning" : "bg-muted-foreground"
                                }`}
                              style={{ width: `${signal.confidence}%` }}
                            ></div>
                          </div>
                          <span className="text-xs font-bold text-foreground">{signal.confidence}%</span>
                        </div>
                      </div>
                    </div>

                    {/* Reasoning */}
                    <div className="mt-4 pt-4 border-t border-border/10">
                      <p className="text-xs font-medium text-muted-foreground mb-1">AI Reasoning:</p>
                      <p className="text-sm text-foreground">{signal.reason}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
