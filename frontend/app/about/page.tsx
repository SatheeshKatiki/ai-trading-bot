"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { motion } from "framer-motion";
import {
  Zap, Shield, Brain, TrendingUp, Activity, Target,
  Clock, Server, Code2, Database, Globe, Cpu,
  BarChart2, ArrowRight, CheckCircle2, Layers, GitBranch,
  Rocket, Award, Users, LineChart
} from "lucide-react";

const stats = [
  { label: "AI Strategies", value: "7", icon: Brain, color: "text-violet-400" },
  { label: "API Endpoints", value: "25+", icon: Server, color: "text-blue-400" },
  { label: "Avg. Signal Latency", value: "<50ms", icon: Zap, color: "text-yellow-400" },
  { label: "Risk Controls", value: "10+", icon: Shield, color: "text-emerald-400" },
];

const techStack = [
  { category: "Frontend", items: ["Next.js 16", "TypeScript", "Zustand", "Framer Motion", "Lightweight Charts", "Tailwind CSS"] },
  { category: "Backend", items: ["FastAPI", "Python 3.11", "XGBoost", "Pandas / NumPy", "SQLite", "WebSocket"] },
  { category: "Broker", items: ["Fyers API v3", "WebSocket Ticks", "OAuth 2.0", "JWT Auth"] },
  { category: "Infrastructure", items: ["Docker", "Log Rotation", "Uvicorn", "Rotating File Handler"] },
];

const coreFeatures = [
  { icon: Brain, title: "Autonomous AI Engine", desc: "7 production-grade strategies running in parallel. XGBoost ML model auto-retrains every 24 hours on live market data to stay adaptive to current market regimes." },
  { icon: Shield, title: "Institutional Risk Engine", desc: "Multi-layer protection: per-trade stoploss, trailing SL, daily loss limits, max trades per day, pyramiding controls, and emergency panic exit." },
  { icon: Zap, title: "Real-Time Execution", desc: "WebSocket-based live tick data with sub-50ms signal generation. Orders are placed directly via Fyers API with full order lifecycle tracking." },
  { icon: BarChart2, title: "Advanced Charting", desc: "Custom native charting engine built on Lightweight Charts with 10+ indicators including Smart Trend, EMA, RSI, Bollinger Bands, and VWAP." },
  { icon: Target, title: "Options Desk", desc: "Live NSE Option Chain with Greeks (Delta, Theta, Gamma, Vega), ATM detection, Max Pain, PCR analysis, and OI change tracking." },
  { icon: LineChart, title: "Backtesting Engine", desc: "Walk-forward backtesting with 70/30 train-test split, slippage simulation, and comprehensive performance metrics including Sharpe ratio, Win Rate, and drawdown." },
];

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

const stagger = {
  show: { transition: { staggerChildren: 0.08 } },
};

export default function AboutPage() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto">

          {/* ─── Hero ─── */}
          <section className="relative px-8 py-20 overflow-hidden border-b border-border/30">
            {/* Background glow blobs */}
            <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl -translate-y-1/2 pointer-events-none" />
            <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-violet-500/8 rounded-full blur-3xl translate-y-1/2 pointer-events-none" />

            <motion.div
              className="relative z-10 max-w-4xl mx-auto text-center"
              variants={stagger}
              initial="hidden"
              animate="show"
            >
              <motion.div variants={fadeUp} className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-bold uppercase tracking-widest mb-6">
                <Rocket className="w-3.5 h-3.5" />
                v2.0 ULTRA — Production Ready
              </motion.div>

              <motion.h1 variants={fadeUp} className="font-display font-bold text-5xl md:text-6xl text-foreground tracking-tight leading-tight mb-6">
                Mana AI Trading
                <span className="block bg-gradient-to-r from-primary via-violet-400 to-blue-400 bg-clip-text text-transparent">
                  Platform
                </span>
              </motion.h1>

              <motion.p variants={fadeUp} className="text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed mb-10">
                An institutional-grade, fully autonomous AI trading system built for the Indian derivatives market.
                Powered by 7 production-ready strategies, real-time WebSocket execution, and a multi-layer risk engine —
                designed to operate 24/7 without manual intervention.
              </motion.p>

              <motion.div variants={fadeUp} className="flex items-center justify-center gap-4 flex-wrap">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  NSE Options & Equity
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  Fyers API Integrated
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  Paper &amp; Live Trading
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  XGBoost ML Model
                </div>
              </motion.div>
            </motion.div>
          </section>

          {/* ─── Stats ─── */}
          <section className="px-8 py-12 border-b border-border/30">
            <motion.div
              className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4"
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
            >
              {stats.map((s) => (
                <motion.div
                  key={s.label}
                  variants={fadeUp}
                  className="glass-card p-6 rounded-xl border border-border/20 text-center hover:border-primary/30 transition-colors"
                >
                  <s.icon className={`w-6 h-6 mx-auto mb-3 ${s.color}`} />
                  <div className="font-display font-bold text-3xl text-foreground mb-1">{s.value}</div>
                  <div className="text-xs text-muted-foreground">{s.label}</div>
                </motion.div>
              ))}
            </motion.div>
          </section>

          {/* ─── Mission ─── */}
          <section className="px-8 py-16 border-b border-border/30 bg-muted/10">
            <motion.div
              className="max-w-5xl mx-auto"
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
            >
              <motion.h2 variants={fadeUp} className="font-display font-bold text-3xl text-foreground mb-4">
                Our Mission
              </motion.h2>
              <motion.p variants={fadeUp} className="text-muted-foreground text-lg leading-relaxed max-w-3xl mb-8">
                To democratize institutional-grade algorithmic trading for individual traders in the Indian market.
                Every architectural decision in this platform — from the recursive polling strategy to the
                walk-forward backtesting split — is made from the perspective of a 20+ year options trading veteran
                combined with enterprise software engineering discipline.
              </motion.p>
              <motion.div variants={fadeUp} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { icon: Award, title: "World-Class Quality", desc: "Every module is built to institutional standards — not a prototype, a production system." },
                  { icon: Users, title: "Trader-First Design", desc: "Built by traders, for traders. Every UI decision reflects real intraday trading workflows." },
                  { icon: GitBranch, title: "Continuously Evolving", desc: "The AI model retrains daily. New strategies and features are added on a continuous basis." },
                ].map((item) => (
                  <div key={item.title} className="p-5 rounded-xl border border-border/20 bg-card hover:border-primary/20 transition-colors">
                    <item.icon className="w-5 h-5 text-primary mb-3" />
                    <h3 className="font-semibold text-foreground mb-2">{item.title}</h3>
                    <p className="text-sm text-muted-foreground">{item.desc}</p>
                  </div>
                ))}
              </motion.div>
            </motion.div>
          </section>

          {/* ─── Core Features ─── */}
          <section className="px-8 py-16 border-b border-border/30">
            <motion.div
              className="max-w-5xl mx-auto"
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
            >
              <motion.h2 variants={fadeUp} className="font-display font-bold text-3xl text-foreground mb-2">
                Core Capabilities
              </motion.h2>
              <motion.p variants={fadeUp} className="text-muted-foreground mb-10">
                Everything you need to run a professional automated trading operation.
              </motion.p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {coreFeatures.map((f, i) => (
                  <motion.div
                    key={f.title}
                    variants={fadeUp}
                    className="p-5 rounded-xl border border-border/20 bg-card hover:border-primary/30 hover:shadow-[0_0_20px_rgba(var(--primary-rgb),0.08)] transition-all group"
                  >
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                      <f.icon className="w-5 h-5 text-primary" />
                    </div>
                    <h3 className="font-semibold text-foreground mb-2">{f.title}</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </section>

          {/* ─── Tech Stack ─── */}
          <section className="px-8 py-16 border-b border-border/30 bg-muted/10">
            <motion.div
              className="max-w-5xl mx-auto"
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
            >
              <motion.h2 variants={fadeUp} className="font-display font-bold text-3xl text-foreground mb-2">
                Technology Stack
              </motion.h2>
              <motion.p variants={fadeUp} className="text-muted-foreground mb-10">
                Battle-tested, production-grade technologies chosen for speed, reliability, and scalability.
              </motion.p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                {techStack.map((stack) => (
                  <motion.div
                    key={stack.category}
                    variants={fadeUp}
                    className="p-5 rounded-xl border border-border/20 bg-card"
                  >
                    <div className="flex items-center gap-2 mb-4">
                      <Layers className="w-4 h-4 text-primary" />
                      <h3 className="font-bold text-sm text-foreground">{stack.category}</h3>
                    </div>
                    <ul className="space-y-2">
                      {stack.items.map((item) => (
                        <li key={item} className="flex items-center gap-2 text-sm text-muted-foreground">
                          <ArrowRight className="w-3 h-3 text-primary/60 flex-shrink-0" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </section>

          {/* ─── Footer ─── */}
          <section className="px-8 py-12">
            <div className="max-w-5xl mx-auto text-center">
              <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-card border border-border/30 text-sm text-muted-foreground">
                <Cpu className="w-4 h-4 text-primary" />
                Mana AI Trading Platform — v2.0 ULTRA
                <span className="mx-2 text-border">|</span>
                <Clock className="w-4 h-4" />
                Built for NSE Options &amp; Equity Markets
              </div>
              <p className="text-xs text-muted-foreground/50 mt-4">
                This platform is for educational and personal trading purposes. Always trade responsibly.
              </p>
            </div>
          </section>

        </main>
      </div>
    </div>
  );
}
