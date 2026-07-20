"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import {
  Layers, Server, Zap, Shield, Brain, Database, Globe,
  GitBranch, Settings, AlertTriangle, Rocket, FileText,
  ArrowRight, ChevronRight, Terminal, Cpu, Lock,
  BarChart2, Activity, TrendingUp, BookOpen, RefreshCw,
  Wrench, Lightbulb, TestTube, HardDrive, Monitor, Users,
  LineChart, Filter, Moon, Map, BookMarked, Workflow
} from "lucide-react";

const tabs = [
  { id: "architecture",    label: "System Architecture",    icon: Layers },
  { id: "business",        label: "Business Requirements",  icon: BookOpen },
  { id: "requirements",    label: "Functional Reqs",        icon: BarChart2 },
  { id: "frontend",        label: "Frontend Architecture",  icon: Monitor },
  { id: "trading-engine",  label: "Trading Engine",         icon: Zap },
  { id: "strategies",      label: "Strategy Engine",        icon: Brain },
  { id: "risk",            label: "Risk Management",        icon: Shield },
  { id: "order-flow",      label: "Order Execution Flow",   icon: TrendingUp },
  { id: "api",             label: "API Reference",           icon: Server },
  { id: "websocket",       label: "WebSocket",              icon: Globe },
  { id: "broker",          label: "Broker Integration",     icon: GitBranch },
  { id: "auth",            label: "Auth & Security",        icon: Lock },
  { id: "database",        label: "Database Design",        icon: Database },
  { id: "config",          label: "Configuration",          icon: Settings },
  { id: "errors",          label: "Error Handling",         icon: AlertTriangle },
  { id: "logging",         label: "Logging & Monitoring",   icon: Activity },
  { id: "performance",     label: "Performance",            icon: Cpu },
  { id: "scalability",     label: "Scalability & HA",       icon: Layers },
  { id: "deployment",      label: "Deployment",             icon: Rocket },
  { id: "testing",         label: "Testing Strategy",       icon: TestTube },
  { id: "disaster",        label: "Disaster Recovery",      icon: HardDrive },
  { id: "maintenance",     label: "Maintenance & Ops",      icon: Wrench },
  { id: "ai-models",       label: "AI / ML Models",         icon: Brain },
  { id: "roadmap",         label: "Future Roadmap",         icon: Lightbulb },
  { id: "backend-arch",    label: "Backend Architecture",   icon: Server },
  { id: "chart-indicators",label: "Chart & Indicators",     icon: LineChart },
  { id: "inst-filters",    label: "Institutional Filters",  icon: Filter },
  { id: "btst",            label: "BTST Predictor",         icon: Moon },
  { id: "ux-workflows",    label: "UI/UX Workflows",        icon: Workflow },
  { id: "glossary",        label: "Trading Glossary",       icon: BookMarked },
];

// ─── Helper Components ────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h2 className="font-display font-bold text-xl text-foreground mb-4 flex items-center gap-2">
        <ChevronRight className="w-5 h-5 text-primary flex-shrink-0" />
        {title}
      </h2>
      {children}
    </div>
  );
}

function CodeBlock({ children, language }: { children: string; language: string }) {
  return (
    <div className="rounded-xl border border-border/30 overflow-hidden mb-4">
      <div className="px-4 py-2 bg-muted/30 border-b border-border/30 flex items-center gap-2">
        <Terminal className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-[11px] text-muted-foreground font-mono">{language}</span>
      </div>
      <pre className="p-4 text-sm font-mono text-muted-foreground overflow-x-auto bg-muted/10 leading-relaxed whitespace-pre">
        {children}
      </pre>
    </div>
  );
}

function Table({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border/20 mb-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/30 border-b border-border/20">
            {headers.map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-bold text-muted-foreground uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function TR({ cells }: { cells: string[] }) {
  return (
    <tr className="border-b border-border/10 hover:bg-muted/20 transition-colors">
      {cells.map((c, i) => (
        <td key={i} className={`px-4 py-3 text-muted-foreground ${i === 0 ? "font-medium text-foreground" : ""}`}>
          {i === 0 ? <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{c}</code> : c}
        </td>
      ))}
    </tr>
  );
}

function UL({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2 mb-4">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
          <ChevronRight className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
          {item}
        </li>
      ))}
    </ul>
  );
}

// ─── Content ─────────────────────────────────────────────────────
const content: Record<string, React.ReactNode> = {

  architecture: (
    <div>
      <Section title="Overview">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The Mana AI Trading Platform is a full-stack, event-driven autonomous trading system. It follows a layered architecture where the Next.js frontend communicates with a FastAPI backend via REST and WebSocket. The AI trading engine runs as a persistent background process.
        </p>
      </Section>
      <Section title="Architecture Diagram">
        <CodeBlock language="text">{`
┌─────────────────────────────────────────────────────────────┐
│              Next.js Frontend  (Port 3000)                  │
│  Dashboard │ Live │ Backtest │ Options │ Signals │ Docs     │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           FastAPI Backend  api_bridge.py  (Port 8000)       │
│                                                             │
│  Strategy API │ State API │ Backtest API │ Auth API         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Autonomous Trading Engine  (main.py)        │   │
│  │  Signal Engine → Risk Engine → Order Executor        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────┐   ┌────────────────────────────┐  │
│  │  Fyers WebSocket     │   │  SQLite  state.db          │  │
│  │  (Live tick data)    │   │  (Trade history + state)   │  │
│  └──────────────────────┘   └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Fyers API  (NSE)     │
              │  Orders / Positions    │
              └────────────────────────┘`}
        </CodeBlock>
      </Section>
      <Section title="Technology Stack">
        <Table headers={["Layer", "Technology", "Purpose"]}>
          <TR cells={["Frontend", "Next.js 16 + TypeScript", "SSR/CSR dashboard UI"]} />
          <TR cells={["State Management", "Zustand", "Reactive client-side state"]} />
          <TR cells={["Charting", "Lightweight Charts (Custom)", "Real-time OHLCV charts"]} />
          <TR cells={["Animation", "Framer Motion", "Micro-animations & page transitions"]} />
          <TR cells={["Backend", "FastAPI + Uvicorn", "REST API + WebSocket server"]} />
          <TR cells={["Trading Engine", "Python 3.11", "Autonomous signal & order pipeline"]} />
          <TR cells={["ML Model", "XGBoost (XGBClassifier)", "Directional market prediction"]} />
          <TR cells={["Data Processing", "Pandas + NumPy", "OHLCV data manipulation"]} />
          <TR cells={["Broker API", "Fyers API v3", "Market data + order execution"]} />
          <TR cells={["Database", "SQLite (state.db)", "Trade history & state persistence"]} />
          <TR cells={["Logging", "RotatingFileHandler (5 MB × 3)", "Capped log files"]} />
        </Table>
      </Section>
      <Section title="Data Flow (End-to-End)">
        <ol className="space-y-3">
          {["Fyers WebSocket → pushes live ticks to the Trading Engine",
            "Trading Engine → fetches OHLCV candle history via Fyers REST API",
            "Signal Engine → runs active strategy → BUY / SELL / HOLD signal",
            "Risk Engine → validates signal against all risk rules",
            "Order Executor → places order via Fyers API, records to state.db",
            "API Bridge → exposes full system state via /api/state",
            "Frontend → polls /api/state every 1.5s + receives WebSocket ticks",
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
              <span className="mt-0.5 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center flex-shrink-0">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      </Section>
    </div>
  ),

  business: (
    <div>
      <Section title="Business Context">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The Mana AI Trading Platform is designed to solve the problem of emotional, inconsistent, and manual option trading in the Indian NSE derivatives market. Individual retail traders consistently underperform due to lack of discipline, speed, and systematic risk management — problems this platform solves through full automation.
        </p>
      </Section>
      <Section title="Business Objectives">
        <UL items={[
          "Automate intraday options buying strategy execution with zero manual intervention",
          "Enforce strict risk controls to prevent catastrophic daily losses",
          "Provide institutional-grade analytics and transparency into AI decision-making",
          "Enable paper trading mode for strategy validation before going live",
          "Deliver a world-class user experience comparable to professional trading terminals",
        ]} />
      </Section>
      <Section title="Target Users">
        <Table headers={["User Type", "Usage Pattern"]}>
          <TR cells={["Primary Trader", "Monitors AI positions, configures risk, reviews P&L daily"]} />
          <TR cells={["Strategy Researcher", "Uses backtesting engine to validate new strategies"]} />
          <TR cells={["DevOps Engineer", "Manages deployment, monitors logs, handles infra"]} />
          <TR cells={["Future Team Member", "Uses this documentation to onboard independently"]} />
        </Table>
      </Section>
      <Section title="Success Metrics">
        <UL items={[
          "Win rate > 50% on live trades over a rolling 30-day period",
          "Max daily loss never exceeds configured daily loss limit",
          "System uptime > 99% during market hours (9:15 AM – 3:30 PM IST)",
          "Signal latency < 100ms from candle close to order placement",
          "Zero double-order incidents (idempotent order placement logic)",
        ]} />
      </Section>
    </div>
  ),

  requirements: (
    <div>
      <Section title="Functional Requirements">
        <Table headers={["ID", "Requirement", "Priority"]}>
          <TR cells={["FR-01", "System shall autonomously generate BUY/SELL signals using configured strategy", "Critical"]} />
          <TR cells={["FR-02", "System shall place orders via Fyers API without manual input", "Critical"]} />
          <TR cells={["FR-03", "System shall enforce per-trade stoploss and trailing SL", "Critical"]} />
          <TR cells={["FR-04", "System shall square off all positions before 3:20 PM IST", "Critical"]} />
          <TR cells={["FR-05", "System shall support paper trading mode (no real orders)", "High"]} />
          <TR cells={["FR-06", "System shall provide real-time P&L tracking on dashboard", "High"]} />
          <TR cells={["FR-07", "System shall allow strategy switching without restart", "High"]} />
          <TR cells={["FR-08", "System shall support backtesting any strategy on historical data", "High"]} />
          <TR cells={["FR-09", "System shall display live option chain with Greeks", "Medium"]} />
          <TR cells={["FR-10", "System shall support emergency panic exit (close all positions)", "Critical"]} />
          <TR cells={["FR-11", "System shall log all trades to persistent SQLite database", "High"]} />
          <TR cells={["FR-12", "System shall authenticate user via password before access", "High"]} />
        </Table>
      </Section>
      <Section title="Non-Functional Requirements">
        <Table headers={["ID", "Requirement", "Target"]}>
          <TR cells={["NFR-01", "Signal-to-order latency", "< 100ms"]} />
          <TR cells={["NFR-02", "Frontend state refresh rate", "1.5 seconds"]} />
          <TR cells={["NFR-03", "System uptime during market hours", "> 99%"]} />
          <TR cells={["NFR-04", "Max log file size", "5 MB × 3 rotations"]} />
          <TR cells={["NFR-05", "XGBoost model retraining frequency", "Every 24 hours"]} />
          <TR cells={["NFR-06", "WebSocket reconnection time", "< 10 seconds"]} />
          <TR cells={["NFR-07", "Build size (frontend bundle)", "< 5 MB gzipped"]} />
          <TR cells={["NFR-08", "Password lockout after failed attempts", "5 attempts → lockout"]} />
          <TR cells={["NFR-09", "Chart rendering FPS", "60 FPS target"]} />
          <TR cells={["NFR-10", "Concurrent API request handling", "FastAPI async (non-blocking)"]} />
        </Table>
      </Section>
    </div>
  ),

  frontend: (
    <div>
      <Section title="Frontend Architecture Overview">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The frontend is a Next.js 16 application using the App Router. All pages are Client Components (due to heavy real-time state) wrapped in a consistent layout with Sidebar + Header.
        </p>
      </Section>
      <Section title="Page Structure">
        <Table headers={["Route", "Page", "Purpose"]}>
          <TR cells={["/", "Dashboard", "Overview: equity, P&L, recent trades, AI signals"]} />
          <TR cells={["/live", "Live Trading", "Real-time chart, order panel, options desk, execution feed"]} />
          <TR cells={["/backtest", "Backtesting", "Historical strategy simulation with equity curve"]} />
          <TR cells={["/signals", "AI Signals", "Real-time signal dashboard with confidence scores"]} />
          <TR cells={["/strategy", "Strategy Settings", "Advanced parameter configuration per strategy"]} />
          <TR cells={["/options", "Options Desk", "Full NSE option chain with payoff diagram"]} />
          <TR cells={["/analytics", "Analytics", "Heatmaps, performance metrics, trade history"]} />
          <TR cells={["/journal", "Trading Journal", "Detailed log of every trade with P&L"]} />
          <TR cells={["/risk", "Risk Management", "Portfolio risk controls and daily limits"]} />
          <TR cells={["/broker", "Broker Settings", "Fyers authentication and connection status"]} />
          <TR cells={["/settings", "Settings", "Theme, chart, indicator, and system settings"]} />
          <TR cells={["/docs", "Documentation", "This page — institutional technical docs"]} />
          <TR cells={["/about", "About", "Platform overview, tech stack, mission"]} />
        </Table>
      </Section>
      <Section title="State Management (Zustand Stores)">
        <Table headers={["Store", "File", "Manages"]}>
          <TR cells={["useLiveSettingsStore", "store/useLiveSettingsStore.ts", "Trading mode, strategy, quantity, SL, filters, pyramiding"]} />
          <TR cells={["useLiveMarketStore", "store/useLiveMarketStore.ts", "Live LTP, WS connection, ticker tape data"]} />
          <TR cells={["useChartSettingsStore", "store/useChartSettingsStore.ts", "Chart indicators, colors, timeframe settings"]} />
        </Table>
      </Section>
      <Section title="Key Components">
        <Table headers={["Component", "Purpose"]}>
          <TR cells={["NativeChart", "Custom charting engine: candlesticks, 10+ indicators, Smart Trend"]} />
          <TR cells={["OptionsDesk", "Live option chain table with Greeks, recursive polling"]} />
          <TR cells={["TradeActionPanel", "AI constraint configuration: lots, SL, strategy, filters"]} />
          <TR cells={["MetricsBar", "Real-time equity, daily P&L, open positions count"]} />
          <TR cells={["ExecutionFeed", "Live trade execution history with timestamps"]} />
          <TR cells={["MergedAiSignal", "AI signal display: BUY/SELL/HOLD with confidence %"]} />
          <TR cells={["MarketTicker", "Scrolling ticker tape with live index prices"]} />
          <TR cells={["ErrorBoundary", "Catches React runtime crashes, shows fallback UI"]} />
          <TR cells={["AuthProvider", "Wraps entire app, enforces password authentication"]} />
          <TR cells={["NewsTicker", "Scrolling market news feed"]} />
        </Table>
      </Section>
    </div>
  ),

  "trading-engine": (
    <div>
      <Section title="Overview">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The Trading Engine (trading_bot/main.py) is the autonomous core. It runs as an infinite async loop — polling the market, generating signals, validating risk, and placing orders without manual intervention.
        </p>
      </Section>
      <Section title="Execution Loop">
        <CodeBlock language="text">{`
START
  ├─ 1. Connect to Fyers WebSocket (live tick subscription)
  ├─ 2. Load settings.json (strategy, SL, filters, mode)
  ├─ 3. On each candle close:
  │     ├─ Fetch OHLCV history from Fyers REST API
  │     ├─ Run active strategy → Signal {BUY|SELL|HOLD}
  │     ├─ Risk Engine checks:
  │     │     ├─ Is market open? (9:15–3:20 IST)
  │     │     ├─ Daily loss limit breached?
  │     │     ├─ Max trades/day reached?
  │     │     └─ Position already open?
  │     ├─ If VALID ENTRY:
  │     │     ├─ ITM Selector → pick option contract
  │     │     ├─ Execution Sizer → calculate lot qty
  │     │     └─ Place order → Fyers API → record to DB
  │     └─ If POSITION OPEN:
  │           ├─ Fixed SL check
  │           ├─ Trailing SL check
  │           └─ EOD square-off (3:20 PM IST)
  └─ 4. Sleep → Wait for next candle → Repeat`}
        </CodeBlock>
      </Section>
      <Section title="Key Modules">
        <Table headers={["Module", "File", "Responsibility"]}>
          <TR cells={["Main Loop", "trading_bot/main.py", "Orchestrates full trading lifecycle"]} />
          <TR cells={["Signal Engine", "momentum_strategy/signal_engine.py", "Generates directional signals"]} />
          <TR cells={["ITM Selector", "momentum_strategy/itm_selector.py", "Picks optimal option contract"]} />
          <TR cells={["Execution Sizer", "momentum_strategy/execution_sizer.py", "Calculates lot quantity"]} />
          <TR cells={["Exit Manager", "momentum_strategy/exit_manager.py", "SL & target exit logic"]} />
          <TR cells={["MTM Trailing", "momentum_strategy/mtm_trailing.py", "Peak-tracking trailing SL engine"]} />
          <TR cells={["Environment Filter", "momentum_strategy/environment_filter.py", "Market regime / no-trade filter"]} />
          <TR cells={["Risk Engine", "trading_bot/portfolio_risk.py", "Portfolio-level daily risk controls"]} />
          <TR cells={["Fyers Client", "trading_bot/api/fyers_client.py", "Broker API abstraction layer"]} />
        </Table>
      </Section>
    </div>
  ),

  strategies: (
    <div>
      <Section title="Strategy Registry">
        <p className="text-muted-foreground leading-relaxed mb-4">
          All 7 strategies are auto-discovered and registered via <code className="bg-muted px-1 rounded text-xs">trading_bot/strategies/registry.py</code>. Each strategy exposes a <code className="bg-muted px-1 rounded text-xs">generate_signals(df, **kwargs) → pd.Series</code> function. Active strategy is selected from the Settings UI, persisted to settings.json, and hot-swapped without restart.
        </p>
        <Table headers={["Strategy ID", "File / Package", "Signal Frequency", "Best Market"]}>
          <TR cells={["institutional_momentum", "momentum_strategy/ package", "Low (high quality)", "Strong trending"]} />
          <TR cells={["advanced_ai", "advanced_ai_ml_strategy.py", "Medium", "All regimes (adaptive)"]} />
          <TR cells={["meta_agent_swarm", "meta_agent_strategy.py", "Very Low (consensus only)", "Uncertain markets"]} />
          <TR cells={["ema_rsi", "ema_rsi_strategy.py", "Medium-High", "Trending markets"]} />
          <TR cells={["ema_crossover", "ema_crossover_pro_strategy.py", "Medium", "Trending + momentum"]} />
          <TR cells={["enhanced_ai", "enhanced_ai_strategy.py", "Low (5/6 required)", "High conviction only"]} />
          <TR cells={["premium", "premium_selection/ package", "Very Low (8 gates)", "Maximum quality entries"]} />
        </Table>
      </Section>

      {/* ── Strategy 1 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-purple-500/20 bg-purple-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-purple-400 bg-purple-400/10 px-2 py-0.5 rounded">STRATEGY 1</span>
          <span className="text-xs text-muted-foreground font-mono">institutional_momentum</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">Institutional Momentum Strategy</h2>
        <p className="text-sm text-muted-foreground mb-4">The primary production strategy. Uses multi-timeframe analysis to ensure the 1-hour trend and 5-minute breakout are perfectly aligned before entering. Requires all 4 gates to pass — no exceptions.</p>
        <img src="/docs-assets/strategy_institutional_momentum.png" alt="Institutional Momentum Strategy Flowchart" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">4 Entry Gates (ALL must pass)</p>
            <ol className="space-y-1.5">
              {["GATE 1 — 1H Trend: Price > EMA50 > EMA200 (Bullish) or Price < EMA50 < EMA200 (Bearish)", "GATE 2 — 5MIN Breakout: Fast EMA crosses Slow EMA in same direction as 1H trend", "GATE 3 — Volume Surge: Breakout candle volume > 1.5× VMA-20", "GATE 4 — VWAP Position: Long entries above VWAP, Short entries below VWAP"].map((g, i) => (
                <li key={i} className="text-xs text-muted-foreground flex gap-2"><span className="text-purple-400 font-bold">✓</span>{g}</li>
              ))}
            </ol>
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Parameters</p>
            <table className="w-full text-xs">
              {[["1H EMA Fast", "50"], ["1H EMA Slow", "200"], ["5M Breakout Fast", "9"], ["5M Breakout Slow", "21"], ["Volume Multiplier", "1.5×"], ["Signal Strength", "0.5 + (vol_ratio - 1.5) × 0.2"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Strong trending days on NIFTY/BANKNIFTY. Avoids choppy / rangebound markets by design. High signal quality, lower frequency.
        </div>
      </div>

      {/* ── Strategy 2 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">STRATEGY 2</span>
          <span className="text-xs text-muted-foreground font-mono">advanced_ai</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">Advanced AI / ML Strategy (XGBoost)</h2>
        <p className="text-sm text-muted-foreground mb-4">Uses an XGBoost binary classifier trained on 6 engineered features from OHLCV data. The model predicts the probability of an UP move on the next candle. Automatically retrains every 24 hours at 11 PM to stay adaptive to current market conditions.</p>
        <img src="/docs-assets/strategy_advanced_ai_ml.png" alt="Advanced AI ML Strategy Pipeline" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">6 Input Features</p>
            {[["EMA Diff", "(fast-slow)/slow — relative momentum"], ["RSI(14)", "Overbought/oversold indicator"], ["MACD Line", "EMA(12) - EMA(26)"], ["MACD Signal", "EMA(9) of MACD"], ["BB Position", "(close-lower)/(upper-lower)"], ["Volume Ratio", "current_vol / rolling_avg(20)"]].map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-border/10 text-xs"><span className="font-mono text-emerald-400 w-24 flex-shrink-0">{k}</span><span className="text-muted-foreground">{v}</span></div>
            ))}
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Signal Thresholds</p>
            <table className="w-full text-xs">
              {[["Model", "XGBClassifier"], ["Estimators", "200"], ["Max Depth", "4"], ["Learning Rate", "0.05"], ["Train Split", "70% historical"], ["BUY threshold", "P(UP) > 0.65"], ["SELL threshold", "P(UP) < 0.35"], ["HOLD zone", "0.35 ≤ P ≤ 0.65"], ["Retrain schedule", "11 PM daily"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> All market regimes. Self-adapting — retrains daily. Most suitable when markets have complex non-linear patterns that rule-based strategies miss.
        </div>
      </div>

      {/* ── Strategy 3 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-orange-500/20 bg-orange-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-orange-400 bg-orange-400/10 px-2 py-0.5 rounded">STRATEGY 3</span>
          <span className="text-xs text-muted-foreground font-mono">meta_agent_swarm</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">Meta Agent Swarm Strategy</h2>
        <p className="text-sm text-muted-foreground mb-4">A hedge-fund grade ensemble system. Runs 5 technical sub-strategies + 1 RAG News Sentiment agent in parallel. Each agent votes +1 (Bullish), 0 (Neutral), or -1 (Bearish). Trade executes ONLY when the net vote score is ≥ +3 or ≤ -3 — requiring consensus from the majority.</p>
        <img src="/docs-assets/strategy_meta_agent_swarm.png" alt="Meta Agent Swarm Voting System" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">6 Voting Agents</p>
            {[["Agent 1", "Advanced AI (XGBoost)"], ["Agent 2", "Institutional Momentum"], ["Agent 3", "EMA Crossover Pro"], ["Agent 4", "EMA + RSI"], ["Agent 5", "Enhanced AI (6-layer)"], ["Agent 6", "RAG Sentiment (News NLP)"]].map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-border/10 text-xs"><span className="font-mono text-orange-400 w-16 flex-shrink-0">{k}</span><span className="text-muted-foreground">{v}</span></div>
            ))}
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Consensus Logic</p>
            <table className="w-full text-xs">
              {[["Max score", "±6 (all agree)"], ["BUY threshold", "Score ≥ +3"], ["SELL threshold", "Score ≤ -3"], ["HOLD zone", "-2 ≤ score ≤ +2"], ["Backtest mode", "RAG disabled (no lookahead)"], ["Sentiment tool", "VADER compound polarity"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Uncertain or mixed-signal markets. Ultra-low false positive rate. Generates fewer signals but with extremely high conviction. Ideal for capital preservation.
        </div>
      </div>

      {/* ── Strategy 4 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-sky-500/20 bg-sky-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-sky-400 bg-sky-400/10 px-2 py-0.5 rounded">STRATEGY 4</span>
          <span className="text-xs text-muted-foreground font-mono">ema_rsi</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">EMA + RSI + Supertrend Strategy</h2>
        <p className="text-sm text-muted-foreground mb-4">Classic trend-following strategy enhanced with Supertrend confirmation. Requires EMA crossover, RSI momentum, Supertrend direction, and volume filter to all agree. Simple, battle-tested logic with broad applicability.</p>
        <img src="/docs-assets/strategy_ema_rsi.png" alt="EMA RSI Strategy Flowchart" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">BUY CE (Call) Logic</p>
            <ol className="space-y-1">
              {["EMA(20) > EMA(50) — fast above slow", "RSI(14) > 55 — momentum rising", "Supertrend(10, 3.0) direction = +1", "Volume ≥ 20-bar rolling average"].map((c, i) => (
                <li key={i} className="text-xs text-muted-foreground flex gap-2"><span className="text-sky-400 font-bold">{i+1}.</span>{c}</li>
              ))}
            </ol>
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Parameters</p>
            <table className="w-full text-xs">
              {[["EMA Fast", "20"], ["EMA Slow", "50"], ["RSI Period", "14"], ["RSI Buy Threshold", "> 55"], ["RSI Sell Threshold", "< 45"], ["Supertrend Period", "10"], ["Supertrend Multiplier", "3.0"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Clear trending markets. Beginners and experienced traders alike. Generates more signals than Institutional Momentum but with adequate quality filters.
        </div>
      </div>

      {/* ── Strategy 5 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-pink-500/20 bg-pink-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-pink-400 bg-pink-400/10 px-2 py-0.5 rounded">STRATEGY 5</span>
          <span className="text-xs text-muted-foreground font-mono">ema_crossover</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">EMA Crossover Pro — Dual Entry System</h2>
        <p className="text-sm text-muted-foreground mb-4">An advanced crossover strategy with two distinct entry modes. Type A catches explosive breakouts on the exact crossover candle. Type B catches safe pullback entries up to 5 candles after the crossover. ADX anti-chop guard prevents false entries in sideways markets. Dynamic SL levels per entry type.</p>
        <img src="/docs-assets/strategy_ema_crossover_pro.png" alt="EMA Crossover Pro Dual Entry System" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-pink-400 mb-2 uppercase tracking-wider">TYPE A — Runaway Entry</p>
            <ul className="space-y-1">
              {["Exact EMA(9) cross over EMA(20)", "Green candle on crossover", "Volume ≥ 2× SMA(20) — explosive", "RSI ≥ 65 — strong momentum", "Close > VWAP", "→ SL: EMA(9) level"].map((c) => (
                <li key={c} className="text-xs text-muted-foreground flex gap-2"><span className="text-pink-400">•</span>{c}</li>
              ))}
            </ul>
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-blue-400 mb-2 uppercase tracking-wider">TYPE B — Safe Pullback</p>
            <ul className="space-y-1">
              {["Recent cross within last 5 candles", "EMA(9) still above EMA(20)", "Low touches EMA(9) but close > EMA(9)", "RSI ≥ 55 — still holding strength", "ADX(14) ≥ 20 — trending confirmed", "Within 0.5% of VWAP", "→ SL: EMA(20) level"].map((c) => (
                <li key={c} className="text-xs text-muted-foreground flex gap-2"><span className="text-blue-400">•</span>{c}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Strong momentum days. Dual entry maximizes capture of both breakout and pullback opportunities. ADX guard keeps it safe in choppy conditions.
        </div>
      </div>

      {/* ── Strategy 6 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-violet-500/20 bg-violet-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-violet-400 bg-violet-400/10 px-2 py-0.5 rounded">STRATEGY 6</span>
          <span className="text-xs text-muted-foreground font-mono">enhanced_ai</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">Enhanced AI — 6-Layer Confirmation Strategy</h2>
        <p className="text-sm text-muted-foreground mb-4">Combines traditional technical analysis with Smart Money Concepts (SMC) and option chain sentiment into a 6-point scoring system. A minimum of 5 out of 6 layers must agree before a signal is generated — ensuring extremely high conviction entries only.</p>
        <img src="/docs-assets/strategy_enhanced_ai.png" alt="Enhanced AI 6-Layer Scoring System" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">6 Scoring Layers (+1 each)</p>
            {[["Layer 1", "EMA(9/20) Crossover direction"], ["Layer 2", "RSI > 40 (Call) / RSI < 60 (Put) — catches early moves"], ["Layer 3", "MACD Line vs Signal Line cross"], ["Layer 4", "Volume > 20-bar rolling average"], ["Layer 5", "SMC: Bullish/Bearish FVG or Break of Structure"], ["Layer 6", "Option Chain Sentiment (PCR/OI bias)"]].map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-border/10 text-xs"><span className="font-mono text-violet-400 w-16 flex-shrink-0">{k}</span><span className="text-muted-foreground">{v}</span></div>
            ))}
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Key Design Choices</p>
            <table className="w-full text-xs">
              {[["Min confirmations", "5 of 6"], ["RSI buy threshold", "> 40 (not 55)"], ["RSI sell threshold", "< 60 (not 45)"], ["Why low RSI thresh?", "Catches early momentum"], ["SMC: FVG", "Fair Value Gap — imbalance zone"], ["SMC: BOS", "Break of Structure — trend shift"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground text-[10px]">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Traders who want institutional-quality entries with SMC confluence. Lower signal frequency but each signal carries multi-layer conviction.
        </div>
      </div>

      {/* ── Strategy 7 ── */}
      <div className="mb-10 p-6 rounded-2xl border border-yellow-500/20 bg-yellow-500/5">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-bold text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded">STRATEGY 7</span>
          <span className="text-xs text-muted-foreground font-mono">premium</span>
        </div>
        <h2 className="text-xl font-bold text-foreground mb-3">Premium Selection — 8-Gate Institutional Pipeline</h2>
        <p className="text-sm text-muted-foreground mb-4">The most comprehensive strategy. An 8-layer sequential gate pipeline where each gate must pass before proceeding to the next. Ends with an intelligent Options Selector that picks the optimal strike, expiry, and lot size. Designed for maximum-quality trades only.</p>
        <img src="/docs-assets/strategy_premium_selection.png" alt="Premium Selection 8-Gate Pipeline" className="w-full rounded-xl border border-border/20 mb-4" onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }} />
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">8 Sequential Gates</p>
            {[["Gate 1", "Trend Filter — EMA(20/50/200) alignment + slope"], ["Gate 2", "Momentum — RSI + MACD + Candle body strength"], ["Gate 3", "Volume — Spike detection + consecutive bars"], ["Gate 4", "Volatility — ATR regime (not too quiet/spikey)"], ["Gate 5", "Market Structure — HH/HL pattern + pullback-retest"], ["Gate 6", "No-Trade Guard — time windows + choppy detection"], ["Gate 7", "AI Confidence Gate — minimum 75% AI score"], ["Gate 8", "Options Selector — ATM/ITM + expiry + lot size"]].map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-border/10 text-xs"><span className="font-mono text-yellow-400 w-14 flex-shrink-0">{k}</span><span className="text-muted-foreground">{v}</span></div>
            ))}
          </div>
          <div className="p-3 rounded-lg bg-muted/20 border border-border/20">
            <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wider">Options Selector (Gate 8)</p>
            <table className="w-full text-xs">
              {[["Strike type", "ATM or ITM (configurable)"], ["Expiry", "Current week (Thursday)"], ["Instrument", "NIFTY, BANKNIFTY, etc."], ["Lot calculator", "base_qty ÷ lot_size"], ["Symbol format", "NSE:NIFTY26DEC2424000CE"], ["AI min score", "75% confidence required"]].map(([k, v]) => (
                <tr key={k} className="border-b border-border/10"><td className="py-1 text-muted-foreground">{k}</td><td className="py-1 text-right font-mono text-foreground text-[10px]">{v}</td></tr>
              ))}
            </table>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-green-400">
          <strong>Best for:</strong> Maximum quality entries only. Very few signals per day but each one is a premium setup. Ideal for traders who prefer quality over quantity with full options selection automation.
        </div>
      </div>

      <Section title="Signal Output Schema">
        <CodeBlock language="python">{`{
  "signal":      "BUY" | "SELL" | "HOLD",
  "confidence":  0.0–1.0,     # AI model probability score
  "reason":      "string",    # Human-readable explanation
  "strike":      24000,       # Suggested strike price
  "option_type": "CE" | "PE",
  "timeframe":   "5m" | "15m"
}`}</CodeBlock>
      </Section>
    </div>
  ),

  risk: (
    <div>
      <Section title="Risk Management Overview">
        <p className="text-muted-foreground leading-relaxed mb-4">
          Multi-layer risk controls operate at both per-trade and portfolio levels. No order is placed unless ALL checks pass. Controls are configurable via the Settings UI in real time.
        </p>
      </Section>
      <Section title="Risk Control Matrix">
        <Table headers={["Control", "Default", "Configurable", "Description"]}>
          <TR cells={["Per-Trade Stoploss", "30%", "Yes", "Exit if premium drops by this % from entry"]} />
          <TR cells={["Trailing SL Trigger", "80%", "Yes", "Activate trailing SL after this % profit"]} />
          <TR cells={["Trailing SL Offset", "20%", "Yes", "Lock in profits at this % below peak MTM"]} />
          <TR cells={["Daily Loss Limit", "2%", "Yes", "Stop all trading after this % daily drawdown"]} />
          <TR cells={["Max Trades/Day", "Unlimited", "Yes", "Hard cap on intraday trade count"]} />
          <TR cells={["Market Hours Gate", "9:15–3:20 IST", "No", "No orders outside market hours"]} />
          <TR cells={["EOD Square-off", "3:20 PM IST", "No", "All positions closed before market close"]} />
          <TR cells={["Pyramiding", "Disabled", "Yes", "Add to winning position (up to maxScales)"]} />
          <TR cells={["Emergency Panic Exit", "Manual trigger", "N/A", "Instantly closes ALL open positions"]} />
        </Table>
      </Section>
      <Section title="Stoploss Logic Flowchart">
        <CodeBlock language="text">{`
On Each Tick (position open):
  current_pnl_pct = (ltp - entry_price) / entry_price × 100

  ── Fixed SL ─────────────────────────────────────────
  IF current_pnl_pct ≤ -stoploss_pct:
    EXIT → reason: "Fixed SL Hit"

  ── Trailing SL ──────────────────────────────────────
  IF trailingSl == true AND current_pnl_pct ≥ trail_trigger:
    peak_mtm = max(peak_mtm, current_pnl_pct)
    sl_floor  = peak_mtm - trail_offset
    IF current_pnl_pct ≤ sl_floor:
      EXIT → reason: "Trailing SL Hit"

  ── EOD Square-off ───────────────────────────────────
  IF IST_time ≥ 15:20:
    EXIT → reason: "EOD Square-off"`}
        </CodeBlock>
      </Section>
    </div>
  ),

  "order-flow": (
    <div>
      <Section title="Order Execution Flow">
        <p className="text-muted-foreground leading-relaxed mb-4">
          End-to-end sequence from signal generation to confirmed order placement and trade recording.
        </p>
      </Section>
      <Section title="Entry Order Sequence">
        <CodeBlock language="text">{`
Signal Generated (e.g., BUY)
        │
        ▼
Risk Engine Validation
        │ ── FAIL ──► Skip signal, log reason
        │
        ▼ PASS
ITM Selector
  • Fetch live option chain from Fyers
  • Filter by option_type (CE for BUY, PE for SELL)
  • Select strike by ATM / ITM offset logic
  • Verify liquidity (volume > minimum threshold)
        │
        ▼
Execution Sizer
  • base_qty  = settings["quantity"]   (e.g., 65 units = 1 NIFTY lot)
  • If pyramiding: scale_qty based on scale_pct
        │
        ▼
Order Placement
  POST Fyers /orders/sync {
    symbol:     "NSE:NIFTY26DEC2424000CE",
    side:       "BUY",
    qty:        65,
    order_type: "MARKET",
    product:    "INTRADAY"
  }
        │
        ▼
Order Confirmed → order_id received
        │
        ▼
State Update
  • Record to SQLite: trades table
  • Update in-memory: entry_price, qty, symbol, order_id
  • Set position.open = True`}
        </CodeBlock>
      </Section>
      <Section title="Exit Order Sequence">
        <CodeBlock language="text">{`
Exit Trigger (SL Hit / EOD / Manual)
        │
        ▼
Place Exit Order
  POST Fyers /orders/sync {
    symbol:     same as entry,
    side:       "SELL",     (reverse of entry)
    qty:        same as entry,
    order_type: "MARKET",
    product:    "INTRADAY"
  }
        │
        ▼
Calculate P&L
  pnl = (exit_price - entry_price) × qty   (for BUY)
        │
        ▼
Update SQLite
  UPDATE trades SET exit_price, pnl, status="CLOSED", reason
        │
        ▼
Reset In-Memory State
  position.open = False, entry_price = None`}
        </CodeBlock>
      </Section>
    </div>
  ),

  api: (
    <div>
      <Section title="API Reference">
        <p className="text-muted-foreground mb-4">FastAPI on <code className="bg-muted px-1.5 py-0.5 rounded text-xs">http://localhost:8000</code>. Next.js proxies via <code className="bg-muted px-1.5 py-0.5 rounded text-xs">/api/*</code> route handlers in app/api/.</p>
      </Section>
      <Section title="Endpoints">
        {[
          { m: "GET",  p: "/api/health",           d: "Returns {status:'ok'} if backend is running" },
          { m: "GET",  p: "/api/state",             d: "Full system state: positions, P&L, trades, WS status, signals" },
          { m: "GET",  p: "/api/settings",          d: "Returns current settings.json as JSON" },
          { m: "POST", p: "/api/settings",          d: "Updates one or more settings. Partial body accepted." },
          { m: "GET",  p: "/api/strategies",        d: "Returns all registered strategy IDs and metadata" },
          { m: "GET",  p: "/api/strategy/parameters", d: "Returns configurable parameters for active strategy" },
          { m: "GET",  p: "/api/signals",           d: "Returns latest AI signal: bias, confidence, reason" },
          { m: "GET",  p: "/api/option-chain",      d: "Live NSE option chain with Greeks for symbol" },
          { m: "GET",  p: "/api/positions",         d: "Current open positions from broker" },
          { m: "GET",  p: "/api/risk",              d: "Current risk state: daily loss, trade count" },
          { m: "POST", p: "/api/panic-exit",        d: "Emergency: closes ALL open positions immediately" },
          { m: "GET",  p: "/api/engine/status",     d: "Returns running/stopped status of trading engine" },
          { m: "POST", p: "/api/engine/toggle",     d: "Start or stop the trading engine" },
          { m: "GET",  p: "/api/history",           d: "OHLCV candle history for symbol + timeframe" },
          { m: "POST", p: "/api/backtest",          d: "Run strategy backtest on historical data" },
          { m: "GET",  p: "/api/analytics",         d: "Aggregate performance: win rate, Sharpe, drawdown" },
          { m: "GET",  p: "/api/journal",           d: "All historical trades from SQLite" },
          { m: "GET",  p: "/api/logs",              d: "Recent backend log entries" },
          { m: "POST", p: "/api/broker-login",      d: "Initiate Fyers OAuth login flow" },
          { m: "GET",  p: "/api/sentiment",         d: "Market sentiment: PCR, Max Pain, VIX" },
          { m: "GET",  p: "/api/btst",              d: "BTST (Buy Today Sell Tomorrow) predictor signals" },
          { m: "GET",  p: "/api/auth/status",       d: "Returns hasPassword, lockedOut, lockoutSeconds" },
          { m: "POST", p: "/api/auth/setup",        d: "Set initial dashboard password" },
          { m: "POST", p: "/api/auth/login",        d: "Verify password and return auth token" },
          { m: "POST", p: "/api/auth/reset",        d: "Reset password using Fyers Client ID as recovery key" },
        ].map((ep) => (
          <div key={`${ep.m}-${ep.p}`} className="flex items-start gap-3 py-3 border-b border-border/10">
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono flex-shrink-0 mt-0.5 ${ep.m === 'GET' ? 'bg-blue-500/10 text-blue-400' : 'bg-emerald-500/10 text-emerald-400'}`}>{ep.m}</span>
            <code className="text-xs text-foreground font-mono flex-shrink-0 w-56">{ep.p}</code>
            <span className="text-sm text-muted-foreground">{ep.d}</span>
          </div>
        ))}
      </Section>
    </div>
  ),

  websocket: (
    <div>
      <Section title="WebSocket Architecture">
        <p className="text-muted-foreground mb-4">Two separate WebSocket connections — one backend-to-Fyers and one frontend-to-backend.</p>
      </Section>
      <Section title="1. Fyers Market Data WebSocket (Backend)">
        <CodeBlock language="text">{`
Fyers WS Server (NSE tick stream)
        │  LTP, Volume, BidAsk, OI changes
        ▼
trading_bot/api/fyers_client.py
        │  buffers latest tick in memory dict
        ▼
api_bridge.py → /api/state
        │  exposes ltp, change_pct, ws_connected
        ▼
Frontend (polls every 1.5s)`}
        </CodeBlock>
      </Section>
      <Section title="2. Frontend WebSocket (Real-Time Ticks)">
        <CodeBlock language="text">{`
useLiveMarketStore.connectWs(symbol)
        │  ws://localhost:8000/ws/ticks/{symbol}
        ▼
Backend WebSocket handler
        │  streams live tick at ~500ms
        ▼
Zustand store: ltp, volume, changePercent
        │
        ▼
NativeChart component (live candle update)`}
        </CodeBlock>
      </Section>
      <Section title="Reconnect Strategy">
        <UL items={[
          "Fyers WS: Auto-reconnects every 10s on disconnect. Backend logs reconnect events.",
          "Frontend WS: useLiveMarketStore implements reconnect on close/error events.",
          "Both WS connections show live status in the UI (sidebar green/red dot + Live Trading header).",
          "If WS is down, frontend falls back to polling /api/state for LTP data.",
        ]} />
      </Section>
    </div>
  ),

  broker: (
    <div>
      <Section title="Broker Integration — Fyers API v3">
        <p className="text-muted-foreground mb-4">The broker layer is abstracted via a BrokerFactory pattern in brokers/ directory, enabling future support for additional brokers without changing the trading engine.</p>
      </Section>
      <Section title="Authentication Flow">
        <CodeBlock language="text">{`
1. User → Broker Settings page → Enters App ID + Secret Key
2. Frontend → POST /api/broker-login
3. Backend → Generates Fyers OAuth URL (fyersapi.generate_authcode_url)
4. User → Opens URL in browser → Logs in → Gets auth_code
5. Backend → Exchanges auth_code for access_token
6. Token saved to .fyers_tokens.json (encrypted/hashed at rest)
7. All subsequent calls → Bearer {access_token}
8. Token expiry: Daily (Fyers tokens valid for 1 day)
9. Next startup → Token auto-refreshed if valid`}
        </CodeBlock>
      </Section>
      <Section title="Order Lifecycle">
        <Table headers={["Step", "Action", "API"]}>
          <TR cells={["1", "Generate signal", "Internal"]} />
          <TR cells={["2", "Select option contract", "Fyers option chain REST"]} />
          <TR cells={["3", "Calculate lot size", "Internal (execution_sizer)"]} />
          <TR cells={["4", "Place MARKET order", "POST /orders/sync"]} />
          <TR cells={["5", "Receive order_id", "Fyers response"]} />
          <TR cells={["6", "Monitor position LTP", "Fyers WebSocket"]} />
          <TR cells={["7", "Place exit MARKET order", "POST /orders/sync"]} />
          <TR cells={["8", "Record P&L to DB", "SQLite"]} />
        </Table>
      </Section>
      <Section title="Order Request Schema">
        <CodeBlock language="python">{`OrderRequest(
  symbol     = "NSE:NIFTY26DEC2424000CE",
  side       = OrderSide.BUY,
  qty        = 65,           # 1 NIFTY lot
  order_type = OrderType.MARKET,
  product    = "INTRADAY",   # MIS — auto squared off by broker EOD
)`}</CodeBlock>
      </Section>
    </div>
  ),

  auth: (
    <div>
      <Section title="Authentication & Security">
        <p className="text-muted-foreground mb-4">
          The platform uses a password-based local authentication system. The entire frontend is gated behind the AuthProvider component. No page is accessible without authentication.
        </p>
      </Section>
      <Section title="Auth Flow">
        <CodeBlock language="text">{`
On App Load:
  AuthProvider → checks localStorage for "mana_ai_auth_token"
  → If found: renders children (authenticated)
  → If not: calls GET /api/auth/status
      ├─ hasPassword=false → Show "Set Password" screen
      └─ hasPassword=true  → Show "Login" screen

Login:
  POST /api/auth/login {password}
  → Backend: bcrypt.checkpw(password, stored_hash)
  → On success: returns {token: "uuid-token"}
  → Frontend: stores token in localStorage

Password Reset (if locked out or forgotten):
  POST /api/auth/reset {client_id, new_password}
  → Recovery via Fyers Client ID (only the account owner knows this)`}
        </CodeBlock>
      </Section>
      <Section title="Security Controls">
        <Table headers={["Control", "Implementation", "Status"]}>
          <TR cells={["Password hashing", "bcrypt (hashpw / checkpw)", "Active"]} />
          <TR cells={["Auth token storage", "localStorage (UUID token)", "Active"]} />
          <TR cells={["Failed login lockout", "5 attempts → lockout (disabled for local dev)", "Implemented"]} />
          <TR cells={["Auto session lock", "30 min inactivity (commented out for local dev)", "Implemented"]} />
          <TR cells={["CORS restriction", "FastAPI CORSMiddleware — configurable origins", "Active"]} />
          <TR cells={["HTTPS", "Not enforced locally — required in production", "Production only"]} />
          <TR cells={["Fyers token storage", ".fyers_tokens.json (local file, git-ignored)", "Active"]} />
          <TR cells={["API key in .env", "FYERS_APP_ID, FYERS_SECRET_KEY in .env", "Active"]} />
          <TR cells={["Auth file", ".auth.json — bcrypt hash of dashboard password", "Active"]} />
        </Table>
      </Section>
      <Section title="Security Recommendations (Production)">
        <UL items={[
          "Enable HTTPS with a valid SSL certificate (use nginx reverse proxy)",
          "Re-enable the 30-minute auto-lock timer in auth-provider.tsx",
          "Re-enable the 5-attempt lockout in api_bridge.py",
          "Restrict CORS origins to specific frontend URL instead of '*'",
          "Store .fyers_tokens.json in an encrypted vault rather than plain filesystem",
        ]} />
      </Section>
    </div>
  ),

  database: (
    <div>
      <Section title="Database Design — SQLite">
        <p className="text-muted-foreground mb-4">SQLite is used for embedded, zero-configuration persistence. File: trading-system/state.db. No external DB server required.</p>
      </Section>
      <Section title="Schema">
        <CodeBlock language="sql">{`-- Trade History Table
CREATE TABLE IF NOT EXISTS trades (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TEXT    NOT NULL,
  symbol       TEXT    NOT NULL,
  side         TEXT    NOT NULL,   -- 'BUY' | 'SELL'
  entry_price  REAL,
  exit_price   REAL,
  qty          INTEGER,
  pnl          REAL,
  status       TEXT,               -- 'OPEN' | 'CLOSED'
  strategy     TEXT,
  reason       TEXT,               -- 'Fixed SL' | 'Trailing SL' | 'EOD' | 'Manual'
  entry_time   TEXT,
  exit_time    TEXT
);

-- Analytics queries (computed on demand):
SELECT COUNT(*) as total_trades FROM trades WHERE status='CLOSED';
SELECT SUM(pnl) as total_pnl   FROM trades WHERE DATE(timestamp) = DATE('now');
SELECT AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END) AS win_rate FROM trades;`}
        </CodeBlock>
      </Section>
      <Section title="In-Memory State (Non-Persistent)">
        <p className="text-muted-foreground mb-4">The trading engine also maintains real-time in-memory state for latency-critical operations. This state is exposed via /api/state and reset on engine restart.</p>
        <Table headers={["Key", "Type", "Description"]}>
          <TR cells={["position_open", "bool", "Is a trade currently active?"]} />
          <TR cells={["entry_price", "float", "Entry price of current position"]} />
          <TR cells={["entry_symbol", "str", "Option contract currently held"]} />
          <TR cells={["peak_mtm", "float", "Highest MTM profit seen (for trailing SL)"]} />
          <TR cells={["daily_pnl", "float", "Cumulative P&L for today"]} />
          <TR cells={["daily_trade_count", "int", "Number of trades today"]} />
          <TR cells={["ws_connected", "bool", "Fyers WebSocket connection status"]} />
          <TR cells={["live_ltp", "float", "Last traded price (from WebSocket)"]} />
        </Table>
      </Section>
    </div>
  ),

  config: (
    <div>
      <Section title="Configuration Management">
        <p className="text-muted-foreground mb-4">Primary configuration lives in trading-system/settings.json. All values can be updated live via the Settings UI (POST /api/settings). No restart required.</p>
      </Section>
      <Section title="settings.json Full Schema">
        <CodeBlock language="json">{`{
  "active_strategy":          "institutional_momentum",
  "live_trading_mode":        false,   // false = paper (safe)
  "quantity":                 65,      // base qty in units
  "stoploss":                 30,      // per-trade SL %
  "trailing_sl":              true,
  "trail_trigger":            0.8,    // activate at 80% profit
  "trail_offset":             0.2,    // lock 80% of peak
  "donchian_period":          20,
  "enable_pyramiding":        false,
  "scale_pct":                1.5,    // add at 1.5% profit
  "max_scales":               2,
  "max_daily_loss_pct":       2.0,    // 2% account daily limit
  "max_daily_trades":         0,      // 0 = unlimited
  "enable_ema_filter":        true,
  "enable_vwap_filter":       true,
  "enable_rsi_filter":        true,
  "enable_volume_filter":     false,
  "enable_adx_filter":        false,
  "enable_squeeze_filter":    false,
  "enable_extension_filter":  false,
  "enable_cpr_filter":        false,
  "enable_aggression_filter": false
}`}</CodeBlock>
      </Section>
      <Section title="Environment Variables (.env)">
        <Table headers={["Variable", "Description", "Required"]}>
          <TR cells={["FYERS_APP_ID", "Fyers API App ID", "Yes"]} />
          <TR cells={["FYERS_SECRET_KEY", "Fyers API Secret", "Yes"]} />
          <TR cells={["FYERS_CLIENT_ID", "Fyers Client ID (used as password recovery key)", "Yes"]} />
          <TR cells={["FYERS_REDIRECT_URI", "OAuth callback URI", "Yes"]} />
          <TR cells={["API_BRIDGE_PORT", "FastAPI port (default: 8000)", "No"]} />
          <TR cells={["LOG_LEVEL", "Logging verbosity (INFO/DEBUG)", "No"]} />
        </Table>
      </Section>
    </div>
  ),

  errors: (
    <div>
      <Section title="Error Handling Strategy">
        <p className="text-muted-foreground mb-4">Every layer has explicit error handling. The guiding principle: log everything, fail gracefully, never crash the trading engine mid-session.</p>
      </Section>
      <Section title="Frontend Error Handling">
        <Table headers={["Component", "Error Scenario", "Handling"]}>
          <TR cells={["NativeChart", "NaN candle data values", "Filtered before setData() — prevents Lightweight Charts crash"]} />
          <TR cells={["OptionsDesk", "API timeout / network error", "Shows last known data, console.error logs"]} />
          <TR cells={["Live Page", "fetchState failure", "Silent retry on next 1.5s cycle"]} />
          <TR cells={["TradeActionPanel", "Settings POST fails", "Sonner toast error notification"]} />
          <TR cells={["WebSocket", "Connection lost", "Auto-reconnect with exponential backoff"]} />
          <TR cells={["All pages", "React runtime crash", "ErrorBoundary catches, shows fallback UI"]} />
          <TR cells={["Auth", "Invalid password", "Shows shake animation + error message"]} />
        </Table>
      </Section>
      <Section title="Backend Error Handling">
        <Table headers={["Scenario", "Handling"]}>
          <TR cells={["Fyers API rate limit (429)", "Exponential backoff retry"]} />
          <TR cells={["Access token expired", "Auto-refresh on startup"]} />
          <TR cells={["Order rejected by broker", "Log error, do NOT retry (prevents double orders)"]} />
          <TR cells={["WebSocket disconnect", "Auto-reconnect every 10 seconds"]} />
          <TR cells={["Invalid/NaN candle data", "Skip signal generation for that tick"]} />
          <TR cells={["All unhandled exceptions", "Global FastAPI handler → JSON 500 response"]} />
          <TR cells={["Strategy exception", "Log, skip to next candle"]} />
          <TR cells={["SQLite write failure", "Log error, continue (in-memory state still valid)"]} />
        </Table>
      </Section>
    </div>
  ),

  logging: (
    <div>
      <Section title="Logging & Monitoring">
        <p className="text-muted-foreground mb-4">The system uses Python's standard logging module with a rotating file handler to ensure log files never grow unbounded.</p>
      </Section>
      <Section title="Log Files">
        <Table headers={["File", "Contents", "Max Size"]}>
          <TR cells={["fyersApi.log", "All Fyers API requests and responses", "5 MB × 3 rotations = 20 MB max"]} />
          <TR cells={["fyersDataSocket.log", "WebSocket tick events and connection events", "Per Fyers SDK defaults"]} />
          <TR cells={["fyersRequests.log", "Raw HTTP request log from Fyers client", "Cleared on demand"]} />
        </Table>
      </Section>
      <Section title="Log Rotation Setup">
        <CodeBlock language="python">{`# In api_bridge.py (_setup_log_rotation)
RotatingFileHandler(
  filename    = "fyersApi.log",
  maxBytes    = 5 * 1024 * 1024,   # 5 MB per file
  backupCount = 3,                  # fyersApi.log.1, .2, .3
  encoding    = "utf-8"
)
# Prevents: 33 MB fyersRequests.log growing forever`}
        </CodeBlock>
      </Section>
      <Section title="Key Events Logged">
        <UL items={[
          "Every API request to Fyers (method, URL, status code, response time)",
          "Order placement: symbol, side, qty, order_id, price",
          "Order exit: reason (Fixed SL / Trailing SL / EOD), exit_price, P&L",
          "Strategy signal: signal type, confidence, reason",
          "Risk engine block: reason for skipping a signal",
          "WebSocket connect / disconnect / reconnect events",
          "Engine start / stop events",
          "All exceptions with full traceback (via exc_info=True)",
        ]} />
      </Section>
      <Section title="Frontend Monitoring">
        <UL items={[
          "Live latency indicator in page header: Green (<100ms) / Yellow (100–300ms) / Red (>300ms)",
          "Broker connection status dot in sidebar: Green LIVE / Red OFFLINE",
          "WebSocket connection badge in Live Trading page",
          "Sonner toast notifications for all user-triggered actions",
        ]} />
      </Section>
    </div>
  ),

  performance: (
    <div>
      <Section title="Performance Optimization">
        <p className="text-muted-foreground mb-4">Performance is critical for a trading system — chart stutters, slow polls, or memory leaks can cause missed signals or incorrect UI state during high volatility.</p>
      </Section>
      <Section title="Frontend Optimizations">
        <Table headers={["Optimization", "Implementation", "Impact"]}>
          <TR cells={["Dynamic imports", "next/dynamic for NativeChart, AdvancedChart", "Prevents SSR crash, lazy-loads heavy chart code"]} />
          <TR cells={["Recursive setTimeout", "OptionsDesk uses recursive setTimeout not setInterval", "Prevents overlapping API calls under lag"]} />
          <TR cells={["Zustand fine-grained state", "Separate stores for market, settings, chart", "Only subscribed components re-render"]} />
          <TR cells={["isMounted guard", "All async effects check isMounted before setState", "Prevents memory leaks on unmount"]} />
          <TR cells={["Suspense boundary", "LiveTradingContent wrapped in Suspense", "Prevents full-page crash during URL param reads"]} />
          <TR cells={["NaN filtering", "candle data filtered before chart.setData()", "Prevents Lightweight Charts assertion error"]} />
        </Table>
      </Section>
      <Section title="Backend Optimizations">
        <Table headers={["Optimization", "Impact"]}>
          <TR cells={["FastAPI async endpoints", "Non-blocking I/O — handles concurrent requests efficiently"]} />
          <TR cells={["In-memory state", "No DB query needed for hot trading state"]} />
          <TR cells={["numpy type converter", "convert_numpy_types() prevents JSON serialization errors"]} />
          <TR cells={["Log rotation (5MB cap)", "Prevents disk fill during high-volume sessions"]} />
          <TR cells={["XGBoost 24h cache", "Model loaded from file if < 24h old — no retraining delay"]} />
        </Table>
      </Section>
    </div>
  ),

  scalability: (
    <div>
      <Section title="Scalability & High Availability">
        <p className="text-muted-foreground mb-4">The current architecture is designed as a single-machine deployment optimized for an individual trader. This section describes both current limits and future scaling paths.</p>
      </Section>
      <Section title="Current Architecture Limits">
        <Table headers={["Dimension", "Current Limit", "Reason"]}>
          <TR cells={["Concurrent instruments", "1 (single symbol per session)", "WebSocket subscribes to 1 symbol"]} />
          <TR cells={["Concurrent strategies", "1 active at a time", "Registry selects one strategy"]} />
          <TR cells={["Concurrency model", "Single Python process (GIL)", "Standard Python threading"]} />
          <TR cells={["Database", "SQLite (single-writer)", "File-based, not network DB"]} />
          <TR cells={["Frontend users", "1 (local dashboard)", "No multi-user auth"]} />
        </Table>
      </Section>
      <Section title="Scaling Path (Future)">
        <UL items={[
          "Multi-instrument support: Run separate engine instances per symbol via subprocess manager",
          "Multi-strategy ensemble: Already partially implemented via meta_agent_swarm",
          "High availability: Deploy on cloud VM (AWS/GCP) with auto-restart on crash via PM2/supervisor",
          "Database scaling: Migrate SQLite → PostgreSQL for multi-user support",
          "API scaling: Uvicorn + Gunicorn with multiple workers",
          "Monitoring: Add Prometheus metrics endpoint + Grafana dashboard for live system health",
        ]} />
      </Section>
    </div>
  ),

  deployment: (
    <div>
      <Section title="Deployment Architecture">
        <p className="text-muted-foreground mb-4">Three processes must run simultaneously. Current target: single Windows or Linux machine.</p>
      </Section>
      <Section title="Startup Commands">
        <CodeBlock language="bash">{`# ── Process 1: FastAPI Backend ────────────────────────────────
cd "d:/Projects/AI trading Bot/trading-system"
.\\venv\\Scripts\\uvicorn.exe api_bridge:app --host 0.0.0.0 --port 8000

# ── Process 2: Trading Bot Engine ─────────────────────────────
.\\venv\\Scripts\\python.exe trading_bot\\main.py

# ── Process 3: Next.js Frontend ───────────────────────────────
cd "d:/Projects/AI trading Bot/frontend"
npm run dev                   # development
# OR:
npm run build && npm start    # production`}
        </CodeBlock>
      </Section>
      <Section title="Process Map">
        <Table headers={["Process", "Port", "Role", "Restart Needed?"]}>
          <TR cells={["Next.js", "3000", "Frontend UI", "On code change"]} />
          <TR cells={["FastAPI (Uvicorn)", "8000", "API Bridge + WebSocket server", "On api_bridge.py change"]} />
          <TR cells={["Python Trading Bot", "N/A (subprocess)", "Autonomous trading engine", "On main.py or strategy change"]} />
        </Table>
      </Section>
      <Section title="Production Checklist">
        <UL items={[
          "Use PM2 (npm i -g pm2) to keep all 3 processes alive after crash or reboot",
          "Set NODE_ENV=production and build frontend with npm run build",
          "Verify .env has valid FYERS_APP_ID, FYERS_SECRET_KEY, FYERS_CLIENT_ID",
          "Ensure .fyers_tokens.json is present (run broker login once manually)",
          "Configure log rotation (already built-in — 5 MB × 3 backups)",
          "Set live_trading_mode=false initially and verify with paper trading first",
          "Ensure system clock is synced to IST (critical for market hours detection)",
        ]} />
      </Section>
    </div>
  ),

  testing: (
    <div>
      <Section title="Testing Strategy">
        <p className="text-muted-foreground mb-4">The system has integration tests for backend API endpoints and a live paper trading mode for full end-to-end validation.</p>
      </Section>
      <Section title="Test Files">
        <Table headers={["File", "Tests", "Run Command"]}>
          <TR cells={["tests/test_api_bridge.py", "/api/history, /api/backtest, /api/signals structure validation", "python tests/test_api_bridge.py"]} />
          <TR cells={["tests/test_backtest.py", "Backtest engine computation tests", "python tests/test_backtest.py"]} />
          <TR cells={["tests/test_connection.py", "Fyers API connectivity + auth token validity", "python tests/test_connection.py"]} />
          <TR cells={["tests/test_history.py", "Historical candle data fetch and format", "python tests/test_history.py"]} />
          <TR cells={["tests/test_nifty.py", "NIFTY live data fetch test", "python tests/test_nifty.py"]} />
          <TR cells={["tests/test_funds.py", "Account funds/margin fetch test", "python tests/test_funds.py"]} />
        </Table>
      </Section>
      <Section title="Testing Levels">
        <Table headers={["Level", "Method", "Tool"]}>
          <TR cells={["Unit Tests", "Individual function validation", "pytest + FastAPI TestClient"]} />
          <TR cells={["Integration Tests", "API endpoint request/response structure", "test_api_bridge.py"]} />
          <TR cells={["Paper Trading (UAT)", "Full system run with live data, no real orders", "live_trading_mode=false"]} />
          <TR cells={["Backtesting", "Strategy validation on historical data", "/api/backtest endpoint"]} />
          <TR cells={["TypeScript Build", "Frontend type safety validation", "npx tsc --noEmit"]} />
          <TR cells={["Lint Check", "Code quality and unused vars", "npm run lint"]} />
        </Table>
      </Section>
    </div>
  ),

  disaster: (
    <div>
      <Section title="Disaster Recovery">
        <p className="text-muted-foreground mb-4">Procedures for recovering from common failure scenarios during live trading sessions.</p>
      </Section>
      <Section title="Failure Scenarios & Recovery">
        <Table headers={["Scenario", "Impact", "Recovery Procedure"]}>
          <TR cells={["API Bridge crashes mid-trade", "Frontend loses data feed", "1. Restart api_bridge.py  2. Check if position is still open via Fyers portal  3. Manually exit if needed"]} />
          <TR cells={["Trading engine crashes with open position", "Position unmonitored", "1. Check Fyers portal for open positions  2. Exit manually  3. Restart engine"]} />
          <TR cells={["Fyers token expired", "All API calls return 401", "1. Navigate to Broker Settings  2. Run auth flow again  3. Restart engine"]} />
          <TR cells={["Internet outage mid-trade", "WS disconnected, no monitoring", "1. Fyers has broker-level MIS auto square-off at 3:20 PM  2. Once internet restored, engine reconnects automatically"]} />
          <TR cells={["Runaway loss (fat finger / wrong settings)", "Large unexpected loss", "1. Use Panic Exit button immediately  2. Set live_trading_mode=false  3. Investigate in Trading Journal"]} />
          <TR cells={["Disk full (log files)", "Logging stops, potential crash", "1. Run: Clear-Content fyersRequests.log  2. Log rotation prevents recurrence"]} />
          <TR cells={["System crash (power loss)", "All processes stopped", "1. Fyers auto-squares off open positions  2. Restart all 3 processes on system restore"]} />
        </Table>
      </Section>
      <Section title="Safety Nets (Built-In)">
        <UL items={[
          "Broker-level MIS auto square-off: Fyers forcibly closes all INTRADAY positions at 3:20 PM regardless of our engine state",
          "Panic Exit button: Available in the Live Trading page header — closes all positions via API immediately",
          "Paper trading mode: Can switch without restart — safe fallback if live trading behaves unexpectedly",
          "Log rotation: 5 MB × 3 backups — disk never fills due to logs",
        ]} />
      </Section>
    </div>
  ),

  maintenance: (
    <div>
      <Section title="Maintenance & Operations">
        <p className="text-muted-foreground mb-4">Routine tasks required to keep the system running at peak performance.</p>
      </Section>
      <Section title="Daily Checklist (Pre-Market)">
        <UL items={[
          "Verify all 3 processes are running (API Bridge, Trading Engine, Frontend)",
          "Check sidebar connection status: Green LIVE = backend connected",
          "Verify Fyers token is valid (Broker Settings page)",
          "Review previous day's trades in Trading Journal",
          "Confirm settings (strategy, SL, filters) are as intended",
          "Switch from Paper → Live mode only after verification",
        ]} />
      </Section>
      <Section title="Weekly Maintenance">
        <UL items={[
          "Review trading logs for any unexpected errors or warnings",
          "Check models/ directory for xgboost_model.json (should be recent)",
          "Run backtest to validate current strategy on last week's data",
          "Check disk space — log files should be capped by rotation",
          "Review P&L analytics for win rate and Sharpe ratio trends",
        ]} />
      </Section>
      <Section title="Dependency Updates">
        <CodeBlock language="bash">{`# Frontend dependencies
npm audit                    # check for vulnerabilities
npm update                   # update minor versions

# Backend dependencies
pip list --outdated          # see outdated packages
pip install --upgrade <pkg>  # update specific package

# After updates: always run
npm run build                # verify frontend still builds
python tests/test_api_bridge.py  # verify backend still works`}
        </CodeBlock>
      </Section>
    </div>
  ),

  "ai-models": (
    <div>
      <Section title="AI / ML Model Documentation">
        <p className="text-muted-foreground mb-4">XGBoost binary classifier trained on live intraday OHLCV data. Automatically retrains every 24 hours. Saved to models/xgboost_model.json.</p>
      </Section>
      <Section title="Feature Engineering">
        <Table headers={["Feature", "Formula / Description"]}>
          <TR cells={["EMA Diff", "(EMA_fast - EMA_slow) / EMA_slow — relative momentum"]} />
          <TR cells={["RSI (14)", "Standard RSI — overbought/oversold indicator"]} />
          <TR cells={["MACD Line", "EMA(12) - EMA(26)"]} />
          <TR cells={["MACD Signal", "EMA(9) of MACD — crossover signal"]} />
          <TR cells={["BB Position", "(close - BB_lower) / (BB_upper - BB_lower) — range position"]} />
          <TR cells={["Volume Ratio", "current_volume / rolling_avg_volume(20)"]} />
          <TR cells={["ATR", "Average True Range — volatility proxy"]} />
          <TR cells={["Target (Label)", "1 if next_close > current_close, else 0"]} />
        </Table>
      </Section>
      <Section title="Training Pipeline">
        <CodeBlock language="python">{`# Walk-forward split — NO data leakage
train_data  = candle_data.iloc[:-3]       # exclude last 3 (no future label)
split_idx   = int(len(train_data) * 0.70) # 70% train
X_train     = train_data.iloc[:split_idx][features]
y_train     = train_data.iloc[:split_idx]["target"]

model = xgb.XGBClassifier(
  n_estimators=200, max_depth=4, learning_rate=0.05
)
model.fit(X_train, y_train)
model.save_model("models/xgboost_model.json")

# Retrain trigger (every 24 hours):
if (time.time() - os.path.getmtime("models/xgboost_model.json")) > 86400:
    need_train = True`}
        </CodeBlock>
      </Section>
      <Section title="Signal Generation">
        <CodeBlock language="python">{`proba = model.predict_proba(X_predict)
confidence = float(proba[-1][1])  # probability of UP move (class 1)

if confidence > 0.65:    signal = "BUY"
elif confidence < 0.35:  signal = "SELL"
else:                    signal = "HOLD"  # low conviction → skip`}
        </CodeBlock>
      </Section>
    </div>
  ),

  roadmap: (
    <div>
      <Section title="Future Enhancement Roadmap">
        <p className="text-muted-foreground mb-4">Planned improvements prioritized by trading impact and technical feasibility.</p>
      </Section>
      <Section title="Short-Term (Next 30 Days)">
        {[
          { title: "Multi-Symbol Support", desc: "Run the engine simultaneously on NIFTY and BANKNIFTY with separate risk pools." },
          { title: "AI Signal Confidence Threshold UI", desc: "Allow traders to set minimum confidence threshold from the dashboard (currently hardcoded at 0.65)." },
          { title: "Trade Notification System", desc: "Telegram/WhatsApp alerts on every trade entry and exit." },
          { title: "Greeks in Live Position", desc: "Show live Delta, Theta of open position in the Live Trading dashboard." },
        ].map((item) => (
          <div key={item.title} className="p-4 rounded-lg border border-border/20 bg-card mb-3">
            <h3 className="font-semibold text-foreground text-sm mb-1">{item.title}</h3>
            <p className="text-sm text-muted-foreground">{item.desc}</p>
          </div>
        ))}
      </Section>
      <Section title="Medium-Term (1–3 Months)">
        {[
          { title: "Reinforcement Learning Strategy", desc: "Replace XGBoost with a PPO-based RL agent trained on live market interactions." },
          { title: "Multi-Broker Support", desc: "Add Zerodha Kite API as an alternative broker via the existing BrokerFactory pattern." },
          { title: "Cloud Deployment", desc: "Docker + AWS EC2 deployment for 24/7 uptime without keeping a local machine on." },
          { title: "Advanced Backtesting", desc: "Add options-specific backtesting: premium decay, IV crush simulation, real bid-ask spread." },
        ].map((item) => (
          <div key={item.title} className="p-4 rounded-lg border border-border/20 bg-card mb-3">
            <h3 className="font-semibold text-foreground text-sm mb-1">{item.title}</h3>
            <p className="text-sm text-muted-foreground">{item.desc}</p>
          </div>
        ))}
      </Section>
      <Section title="Long-Term Vision (3–12 Months)">
        {[
          { title: "Portfolio-Level Position Sizing", desc: "Kelly Criterion or volatility-adjusted sizing across multiple simultaneous positions." },
          { title: "Institutional Dashboard for Teams", desc: "Multi-user authentication, role-based access (viewer / trader / admin)." },
          { title: "AI Market Regime Detector", desc: "Automatically switch strategies based on detected market regime (trending / choppy / high VIX)." },
          { title: "Live P&L Benchmark vs NIFTY", desc: "Compare AI trading P&L against a simple buy-and-hold benchmark in real time." },
        ].map((item) => (
          <div key={item.title} className="p-4 rounded-lg border border-border/20 bg-card mb-3">
            <h3 className="font-semibold text-foreground text-sm mb-1">{item.title}</h3>
            <p className="text-sm text-muted-foreground">{item.desc}</p>
          </div>
        ))}
      </Section>
    </div>
  ),

  "backend-arch": (
    <div>
      <Section title="Backend Architecture — api_bridge.py">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The entire backend is a single FastAPI application in api_bridge.py (1,849 lines). It serves as the API bridge, WebSocket server, trading state manager, and AI scheduler — all in one process.
        </p>
      </Section>
      <Section title="Internal Architecture">
        <CodeBlock language="text">{`
api_bridge.py  (FastAPI app)
  │
  ├── Middleware
  │     └── CORSMiddleware: allow localhost:3000
  │
  ├── Global State (in-memory, thread-safe)
  │     ├── current_market_data: dict   ← live tick data per symbol
  │     ├── market_data_lock: Lock()    ← thread-safe write access
  │     ├── engine_state: dict          ← is_active, last_start_time, mode
  │     └── fyers_socket_instance       ← active WS connection handle
  │
  ├── Config Cache (_load_config_settings)
  │     └── mtime-based cache of settings.json → avoids disk I/O on every request
  │
  ├── Symbol Formatter (format_broker_symbol)
  │     └── NIFTY → NSE:NIFTY50-INDEX, BANKNIFTY → NSE:NIFTYBANK-INDEX, etc.
  │
  ├── Background Tasks (on startup)
  │     └── daily_retrain_scheduler: asyncio task
  │           └── Every night at 11:00 PM → runs scripts/daily_ai_retrain.py
  │
  ├── REST API Routes (~25 endpoints)
  │     ├── /api/health, /api/state, /api/settings, /api/signals...
  │     └── /api/auth/*, /api/backtest, /api/option-chain...
  │
  ├── WebSocket Routes
  │     └── /ws/ticks/{symbol}  ← streams live tick at 500ms
  │
  └── Global Exception Handler
        └── All unhandled exceptions → JSON 500 response + logger.error`}</CodeBlock>
      </Section>
      <Section title="Key Internal Utilities">
        <Table headers={["Function", "Purpose"]}>
          <TR cells={["_load_config_settings()", "mtime-based cached reader for settings.json — avoids disk I/O on every API call"]} />
          <TR cells={["format_broker_symbol(symbol)", "Converts NIFTY → NSE:NIFTY50-INDEX. Handles stocks, indices, F&O symbols"]} />
          <TR cells={["convert_numpy_types(obj)", "Recursively converts numpy types to native Python for JSON serialization. Handles NaN/Inf → 0.0"]} />
          <TR cells={["daily_retrain_scheduler()", "Async coroutine running as a background task. Triggers AI retrain at 11 PM daily"]} />
          <TR cells={["_hash_password(pwd)", "bcrypt hash for dashboard auth password storage"]} />
          <TR cells={["_verify_password(hash, pwd)", "bcrypt verify for login validation"]} />
        </Table>
      </Section>
      <Section title="Threading Model">
        <p className="text-muted-foreground mb-4">The backend uses two concurrency mechanisms:</p>
        <Table headers={["Mechanism", "Used For"]}>
          <TR cells={["asyncio (async/await)", "FastAPI request handlers, WebSocket streaming, daily_retrain_scheduler"]} />
          <TR cells={["threading.Lock()", "Protecting market_data dict writes from Fyers WS thread (different from FastAPI event loop)"]} />
        </Table>
      </Section>
    </div>
  ),

  "chart-indicators": (
    <div>
      <Section title="Charting Engine — native-chart.tsx">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The native chart is a custom React component (1,108 lines) built on top of Lightweight Charts. It implements all indicator calculations from scratch in TypeScript — no external indicator library.
        </p>
      </Section>
      <Section title="Available Indicators">
        <Table headers={["Indicator", "Default", "Configurable", "Description"]}>
          <TR cells={["EMA 1 (Fast)", "Period: 9, Color: #2962FF", "Yes", "Exponential Moving Average — fast trend line"]} />
          <TR cells={["EMA 2 (Slow)", "Period: 21, Color: #FF6D00", "Yes", "Exponential Moving Average — slow trend line"]} />
          <TR cells={["RSI", "Period: 14, OB: 70, OS: 30", "Yes", "Relative Strength Index in a separate sub-pane"]} />
          <TR cells={["Volume", "Enabled by default", "Toggle", "Volume histogram in lower sub-pane"]} />
          <TR cells={["Smart Trend", "Disabled by default", "Yes", "Custom proprietary trend coloring system (see below)"]} />
        </Table>
      </Section>
      <Section title="Smart Trend System">
        <p className="text-muted-foreground mb-4">Smart Trend is a proprietary candle-coloring system that classifies each candle into one of 5 states based on momentum and EMA relationship:</p>
        <Table headers={["State", "Default Color", "Condition"]}>
          <TR cells={["Bullish Surge", "#7C3AED (Purple)", "Strong bullish momentum above fast EMA"]} />
          <TR cells={["Bearish Surge", "#FF007F (Magenta)", "Strong bearish momentum below fast EMA"]} />
          <TR cells={["Bullish Normal", "#00FF00 (Green)", "Price above EMA, mild bullish momentum"]} />
          <TR cells={["Bearish Normal", "#FF0000 (Red)", "Price below EMA, mild bearish momentum"]} />
          <TR cells={["Chop", "#6B7280 (Gray)", "Sideways / indecisive — no clear direction"]} />
        </Table>
      </Section>
      <Section title="Chart Settings Storage">
        <p className="text-muted-foreground mb-4">All chart settings are persisted using Zustand with localStorage persistence (key: 'chart-settings-storage'). They survive page refresh.</p>
        <CodeBlock language="typescript">{`// useChartSettingsStore.ts — persisted via Zustand persist middleware
{
  ema1Length: 9,       ema1Color: '#2962FF',  ema1LineWidth: 2,
  ema2Length: 21,      ema2Color: '#FF6D00',  ema2LineWidth: 2,
  showVolume: true,
  showRsi: false,      rsiLength: 14,   rsiOverbought: 70, rsiOversold: 30,
  showSmartTrend: false,
  bullishSurgeColor: '#7C3AED',  bearishSurgeColor: '#FF007F',
  bullishNormalColor: '#00FF00', bearishNormalColor: '#FF0000',
  chopColor: '#6B7280',
  // Line styles: 0=Solid, 1=Dotted, 2=Dashed, 3=LargeDashed
}`}</CodeBlock>
      </Section>
      <Section title="Indicator Calculation Methods">
        <Table headers={["Indicator", "Algorithm"]}>
          <TR cells={["EMA", "Exponential: (close - prevEMA) × (2/(period+1)) + prevEMA"]} />
          <TR cells={["SMA", "Simple rolling average over period candles"]} />
          <TR cells={["RSI", "Wilder's Smoothed RS: avgGain/avgLoss over 14 periods"]} />
          <TR cells={["Volume Avg", "Rolling SMA of volume over configurable period"]} />
        </Table>
      </Section>
    </div>
  ),

  "inst-filters": (
    <div>
      <Section title="Institutional Filters Layer">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The Institutional Filters layer (shared/filters/institutional.py) is applied globally to all strategy signals via the Strategy Registry. After a strategy generates a raw BUY or SELL signal, these filters can nullify it based on unfavorable market conditions. Each filter is configurable via the Settings UI.
        </p>
      </Section>
      <Section title="How It Works">
        <CodeBlock language="text">{`
Strategy generates raw signal (BUY / SELL)
        │
        ▼
strategy_registry.run_strategy(name, df, **kwargs)
        │  calls apply_institutional_filters(df, bullish, bearish, **kwargs)
        ▼
For each enabled filter:
  IF filter condition is TRUE (bad market condition):
    nullify the signal (set to 0 / HOLD)
        │
        ▼
Filtered signal returned to trading engine`}</CodeBlock>
      </Section>
      <Section title="Available Filters">
        {[
          { name: "TTM Squeeze Filter", key: "enable_squeeze_filter", desc: "Detects when Bollinger Bands are completely inside Keltner Channels. When active, market is in low-volatility compression — breakout direction is uncertain. Signals are blocked until the squeeze releases.", logic: "squeeze_on = (bb_upper < kc_upper) AND (bb_lower > kc_lower). Checks last 5 bars." },
          { name: "EMA Extension Filter", key: "enable_extension_filter", desc: "Blocks signals when price has moved too far from the 20 EMA. Over-extended moves tend to revert, making new entries risky.", logic: "block if abs(close - EMA20) / EMA20 > 0.006 (0.6% extension threshold)" },
          { name: "CPR Rejection Filter", key: "enable_cpr_filter", desc: "Central Pivot Range filter. Blocks long signals near R1/Top CPR resistance and short signals near S1/Bottom CPR support. Uses yesterday's OHLC to compute today's pivot levels.", logic: "proximity_threshold = 0.15% of price from pivot level" },
          { name: "Candle Aggression Filter", key: "enable_aggression_filter", desc: "Checks if the breakout candle has strong real body. Rejects weak candles (Doji-like) where bulls or bears didn't commit. Ensures entries are on strong momentum candles only.", logic: "bull_strength = (close-low)/(high-low). Reject if < 0.6" },
        ].map((f) => (
          <div key={f.name} className="p-4 rounded-lg border border-border/20 bg-card mb-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-foreground text-sm">{f.name}</h3>
              <code className="text-[10px] bg-muted px-2 py-0.5 rounded font-mono text-muted-foreground">{f.key}</code>
            </div>
            <p className="text-sm text-muted-foreground mb-2">{f.desc}</p>
            <p className="text-xs text-primary/80 font-mono bg-primary/5 px-3 py-1.5 rounded">{f.logic}</p>
          </div>
        ))}
      </Section>
    </div>
  ),

  "btst": (
    <div>
      <Section title="BTST Predictor — Buy Today Sell Tomorrow">
        <p className="text-muted-foreground leading-relaxed mb-4">
          The BTST Predictor is a specialized end-of-day signal component that analyzes market conditions between 2:30 PM and 3:30 PM IST to predict the probability of a gap-up or gap-down opening the next day.
        </p>
      </Section>
      <Section title="Active Window">
        <p className="text-muted-foreground mb-4">The BTST predictor is only active during the 2:30 PM – 3:30 PM IST window. Outside this window, it shows a "Not Active" state. This is intentional — BTST decisions should only be made at EOD with full session data.</p>
        <CodeBlock language="typescript">{`// Time check in btst-predictor.tsx
const timeInMins = hours * 60 + minutes;
if (timeInMins >= 870 && timeInMins <= 930) {  // 2:30PM–3:30PM
  setIsActiveWindow(true);
}`}</CodeBlock>
      </Section>
      <Section title="Signal Output">
        <CodeBlock language="json">{`{
  "status":      "bullish" | "bearish" | "neutral",
  "action":      "BUY" | "HOLD" | "AVOID",
  "gapUpProb":   0.0–1.0,   // probability of gap-up tomorrow
  "gapDownProb": 0.0–1.0,   // probability of gap-down tomorrow
  "reason":      "string",  // human-readable explanation
  "metrics": {
    "momentum": number,  // EOD price momentum
    "rsi":      number   // current RSI value
  }
}`}</CodeBlock>
      </Section>
      <Section title="API Endpoint">
        <p className="text-muted-foreground mb-2">The BTST signal is fetched via:</p>
        <p className="font-mono text-sm bg-muted px-3 py-2 rounded">GET /api/btst?symbol=NIFTY</p>
        <p className="text-muted-foreground text-sm mt-3">The frontend component polls this endpoint every 5 minutes during the active window. Outside the window, no API call is made.</p>
      </Section>
    </div>
  ),

  "ux-workflows": (
    <div>
      <Section title="UI/UX Workflows — Step-by-Step User Journeys">
        <p className="text-muted-foreground mb-4">Complete user workflows for every major operation in the platform.</p>
      </Section>
      {[
        {
          title: "1. First-Time Setup",
          steps: [
            "Start all 3 processes: API Bridge, Trading Engine, Frontend",
            "Open http://localhost:3000 → Auth screen appears",
            "If no password set: Click 'Set Password', enter and confirm password → Submit",
            "Navigate to Broker Settings (/broker) → Enter Fyers App ID and Secret Key",
            "Click 'Connect Fyers' → Browser opens Fyers OAuth login page",
            "Login to Fyers, copy the auth_code → Paste in the field → Submit",
            "Sidebar shows green 'LIVE' dot → Backend connected",
            "Navigate to Settings (/settings) → Set trading mode to Paper first",
            "Navigate to Live Trading (/live) → Verify chart loads with real data",
          ]
        },
        {
          title: "2. Starting the AI Trading Bot",
          steps: [
            "Ensure live_trading_mode is set to Paper in Settings (for safety)",
            "Go to Live Trading (/live) → Review TradeActionPanel on right side",
            "Set: Strategy, Quantity (lots), Stoploss %, and enable desired filters",
            "Set Mode toggle: Paper Trading (safe) or Live Trading",
            "Click the Engine Start button (▶) in the header or Live Trading page",
            "AI bot begins signal generation — watch AI Signal panel for BUY/SELL",
            "When bot places a trade, Execution Feed shows the entry with symbol, price, time",
          ]
        },
        {
          title: "3. Monitoring a Live Trade",
          steps: [
            "Go to Live Trading (/live) → MetricsBar shows: Open PnL, Equity, Trade Count",
            "Native Chart updates in real time — watch candlesticks + indicator overlays",
            "AI Signal widget shows current signal and confidence score",
            "TradeActionPanel shows current position: symbol, entry price, current MTM",
            "When SL or target hit → Bot auto-exits, Execution Feed updates",
            "Post-trade P&L visible in MetricsBar (daily P&L)",
          ]
        },
        {
          title: "4. Emergency Panic Exit",
          steps: [
            "If position needs to be closed immediately for any reason",
            "Click the 'Panic Exit' button (red ⚡ button) in the Live Trading page",
            "System calls POST /api/panic-exit",
            "Backend places immediate MARKET SELL order for all open positions",
            "Execution Feed shows exit with reason: 'Manual Panic Exit'",
            "Review the exit in Trading Journal (/journal)",
          ]
        },
        {
          title: "5. Running a Backtest",
          steps: [
            "Navigate to Backtesting (/backtest)",
            "Select: Symbol (NIFTY/BANKNIFTY), Timeframe (5m/15m), Date Range",
            "Select Strategy to test",
            "Click 'Run Backtest' → System fetches historical data and runs simulation",
            "Review results: Equity Curve chart, Win Rate, Sharpe Ratio, Max Drawdown",
            "Compare multiple strategies to find the best performer for current market",
          ]
        },
        {
          title: "6. Switching Strategy Without Restart",
          steps: [
            "Go to Strategy Settings (/strategy) or use TradeActionPanel dropdown",
            "Select new strategy from the dropdown",
            "Frontend calls POST /api/settings {active_strategy: 'new_strategy_id'}",
            "settings.json is updated immediately",
            "Trading engine reads new strategy on next candle close",
            "No restart of any process required",
          ]
        },
      ].map((workflow) => (
        <div key={workflow.title} className="mb-6 p-4 rounded-xl border border-border/20 bg-card">
          <h3 className="font-bold text-foreground mb-3">{workflow.title}</h3>
          <ol className="space-y-2">
            {workflow.steps.map((step, i) => (
              <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
                <span className="mt-0.5 w-5 h-5 rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center flex-shrink-0">{i+1}</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  ),

  "glossary": (
    <div>
      <Section title="Trading Glossary">
        <p className="text-muted-foreground mb-6">Complete reference of all trading terms, abbreviations, and technical concepts used in this platform.</p>
      </Section>
      <Section title="Options Terminology">
        <Table headers={["Term", "Full Form", "Definition"]}>
          <TR cells={["CE", "Call Option", "Right to BUY the underlying at strike price. Profits when market goes UP."]} />
          <TR cells={["PE", "Put Option", "Right to SELL the underlying at strike price. Profits when market goes DOWN."]} />
          <TR cells={["ATM", "At The Money", "Option strike closest to the current market price."]} />
          <TR cells={["ITM", "In The Money", "CE with strike below market price, or PE with strike above market price. Has intrinsic value."]} />
          <TR cells={["OTM", "Out of The Money", "Option with no intrinsic value — CE above market or PE below market."]} />
          <TR cells={["Premium", "—", "The price paid to buy an option contract."]} />
          <TR cells={["Strike Price", "—", "The pre-agreed price at which the option can be exercised."]} />
          <TR cells={["Expiry", "—", "The date on which the option contract expires. Weekly (Thursday) or Monthly."]} />
          <TR cells={["Lot Size", "—", "Minimum quantity to trade. NIFTY = 75 units, BANKNIFTY = 30 units."]} />
        </Table>
      </Section>
      <Section title="Options Greeks">
        <Table headers={["Greek", "Measures", "Practical Meaning"]}>
          <TR cells={["Delta", "Price sensitivity", "How much option price changes per ₹1 move in underlying. CE Delta: 0 to 1, PE Delta: -1 to 0."]} />
          <TR cells={["Theta", "Time decay", "How much the option loses per day due to time passage. Always negative for buyers — the enemy of option buyers."]} />
          <TR cells={["Gamma", "Delta acceleration", "Rate of change of Delta. High near ATM. Causes P&L to accelerate or decelerate quickly."]} />
          <TR cells={["Vega", "Volatility sensitivity", "How much option price changes per 1% change in Implied Volatility. High Vega = option premium expands/contracts with IV."]} />
        </Table>
      </Section>
      <Section title="Market & Strategy Terms">
        <Table headers={["Term", "Definition"]}>
          <TR cells={["MTM", "Mark-to-Market — current unrealized P&L of an open position based on current market price."]} />
          <TR cells={["SL", "Stoploss — the price level at which we exit to limit our loss."]} />
          <TR cells={["MIS", "Margin Intraday Square-off — Fyers product type for intraday trades, auto squared off at 3:20 PM."]} />
          <TR cells={["PCR", "Put-Call Ratio — Ratio of total Put OI to Call OI. PCR > 1 = more bearish bets (often contrarian bullish signal)."]} />
          <TR cells={["Max Pain", "The strike price at which option buyers lose the most money. Market tends to gravitate here near expiry."]} />
          <TR cells={["VIX", "Volatility Index — measures expected market volatility. India VIX > 20 = high fear/high premium. < 12 = complacency."]} />
          <TR cells={["OI", "Open Interest — total number of outstanding option contracts. Rising OI confirms trend strength."]} />
          <TR cells={["VWAP", "Volume Weighted Average Price — price level weighted by volume. Acts as a key intraday support/resistance."]} />
          <TR cells={["EMA", "Exponential Moving Average — gives more weight to recent prices vs SMA. Used for trend detection."]} />
          <TR cells={["RSI", "Relative Strength Index — momentum oscillator (0-100). > 70 = overbought, < 30 = oversold."]} />
          <TR cells={["MACD", "Moving Average Convergence Divergence — trend + momentum indicator. MACD line crossing signal = entry."]} />
          <TR cells={["ADX", "Average Directional Index — measures trend strength (not direction). ADX > 25 = trending market."]} />
          <TR cells={["CPR", "Central Pivot Range — Support and Resistance levels calculated from previous day's OHLC."]} />
          <TR cells={["BTST", "Buy Today Sell Tomorrow — holding overnight, profiting from gap-up opening next day."]} />
          <TR cells={["Pyramiding", "Adding more contracts to an already winning position (scaling in). High reward, high risk."]} />
          <TR cells={["Squareoff", "Closing an open position. EOD squareoff = forced close before market closes."]} />
          <TR cells={["Slippage", "Difference between expected order price and actual fill price. Higher in illiquid options."]} />
          <TR cells={["Walk-Forward", "Backtesting method where model is trained on early data and tested on unseen future data — prevents overfitting."]} />
        </Table>
      </Section>
      <Section title="System-Specific Terms">
        <Table headers={["Term", "Meaning in This Platform"]}>
          <TR cells={["Paper Trading", "live_trading_mode=false — all signals generated but NO real orders placed. Safe simulation mode."]} />
          <TR cells={["Live Trading", "live_trading_mode=true — real orders placed via Fyers API. Real money at risk."]} />
          <TR cells={["Engine", "The Python trading_bot/main.py process — the autonomous loop that generates signals and places orders."]} />
          <TR cells={["Signal Confidence", "XGBoost model's probability of UP move (0.0 to 1.0). > 0.65 = BUY, < 0.35 = SELL."]} />
          <TR cells={["Panic Exit", "Emergency button that closes ALL open positions immediately via POST /api/panic-exit."]} />
          <TR cells={["MTM Trailing", "Trailing stoploss that follows the peak MTM profit, locking in gains as the position moves in our favour."]} />
        </Table>
      </Section>
    </div>
  ),
};

// ─── Main Page ────────────────────────────────────────────────────
export default function DocsPage() {
  const [activeTab, setActiveTab] = useState("architecture");

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <div className="flex-1 flex overflow-hidden">

          {/* Docs Sidebar */}
          <div className="w-60 flex-shrink-0 border-r border-border/30 overflow-y-auto bg-card/40 backdrop-blur-sm">
            <div className="p-4 border-b border-border/30">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" />
                <h2 className="font-bold text-sm text-foreground">Documentation</h2>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">v2.0 ULTRA — Institutional Grade</p>
            </div>
            <nav className="p-2 space-y-0.5">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all text-left ${
                    activeTab === tab.id
                      ? "bg-primary/10 text-primary font-medium border border-primary/20"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  }`}
                >
                  <tab.icon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{tab.label}</span>
                </button>
              ))}
            </nav>
          </div>

          {/* Main Content */}
          <div className="flex-1 overflow-y-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="p-8 max-w-4xl"
              >
                <div className="mb-8 pb-6 border-b border-border/30">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                    <FileText className="w-3.5 h-3.5" />
                    <span>Mana AI Docs</span>
                    <ArrowRight className="w-3 h-3" />
                    <span className="text-foreground">{tabs.find(t => t.id === activeTab)?.label}</span>
                  </div>
                  <h1 className="font-display font-bold text-3xl text-foreground">
                    {tabs.find(t => t.id === activeTab)?.label}
                  </h1>
                </div>
                {content[activeTab]}
              </motion.div>
            </AnimatePresence>
          </div>

        </div>
      </div>
    </div>
  );
}
