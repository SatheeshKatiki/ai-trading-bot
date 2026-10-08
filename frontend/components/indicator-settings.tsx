"use client";

import React, { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Star,
  Settings2,
  Sliders,
  Check,
  Plus,
  X,
  Layers,
  BarChart3,
  Activity,
  Compass,
  TrendingUp,
  Sparkles,
  BookOpen,
  ExternalLink,
  Info,
  ChevronRight,
  Shield,
  Zap,
  HelpCircle
} from "lucide-react";
import TradingViewIndicatorModal, { IndicatorType } from "@/components/tradingview-indicator-modal";

// Persistent indicator settings data structure
export interface IndicatorSettingsData {
  smc: {
    mode: "Present" | "Historical";
    style: "Colored" | "Monochrome";
    color_candles: boolean;
    show_internal_structure: boolean;
    internal_bullish_color: string;
    internal_bearish_color: string;
    internal_confluence_filter: boolean;
    internal_label_size: "tiny" | "small" | "normal";
    show_swing_structure: boolean;
    swing_points_length: number;
    swing_bullish_color: string;
    swing_bearish_color: string;
    swing_label_size: "tiny" | "small" | "normal";
    show_swing_points: boolean;
    show_strong_weak_high_low: boolean;
    show_order_blocks: boolean;
    internal_ob_count: number;
    swing_ob_count: number;
    ob_filter: "ATR" | "Cumulative Volume" | "None";
    ob_mitigation: "High/Low" | "Close";
    bullish_ob_color: string;
    bearish_ob_color: string;
    show_equal_high_low: boolean;
    eq_bars_confirmation: number;
    eq_threshold: number;
    eq_label_size: "tiny" | "small" | "normal";
    show_fvg: boolean;
    fvg_auto_threshold: boolean;
    fvg_timeframe: string;
    fvg_extend: number;
    mtf_daily: boolean;
    mtf_weekly: boolean;
    mtf_monthly: boolean;
    mtf_color: string;
    show_premium_discount: boolean;
    premium_color: string;
    equilibrium_color: string;
    discount_color: string;
    plot_candles: boolean;
    show_boxes: boolean;
    show_panel_labels: boolean;
    show_lines: boolean;
    precision: string;
    labels_on_price_scale: boolean;
    values_in_status_line: boolean;
    inputs_in_status_line: boolean;
    vis_ticks: boolean;
    vis_seconds: boolean;
    vis_minutes: boolean;
    vis_hours: boolean;
    vis_days: boolean;
    vis_weeks: boolean;
    vis_months: boolean;
  };
  frvp: {
    enabled: boolean;
    num_bins: number;
    value_area_pct: number;
    show_poc: boolean;
    poc_color: string;
    show_value_area: boolean;
    vah_color: string;
    val_color: string;
    show_volume_delta: boolean;
    show_hvn_lvn: boolean;
    hvn_sensitivity_pct: number;
  };
  rsi: {
    enabled: boolean;
    period: number;
    ma_length: number;
    overbought: number;
    oversold: number;
    band_normal: number;
    band_strong: number;
    band_very_strong: number;
    detect_regular_bullish: boolean;
    detect_regular_bearish: boolean;
    detect_hidden_bullish: boolean;
    detect_hidden_bearish: boolean;
    pivot_lookback: number;
    color: string;
  };
}

export const defaultIndicatorSettings: IndicatorSettingsData = {
  smc: {
    mode: "Present",
    style: "Colored",
    color_candles: true,
    show_internal_structure: true,
    internal_bullish_color: "#10b981",
    internal_bearish_color: "#ef4444",
    internal_confluence_filter: true,
    internal_label_size: "tiny",
    show_swing_structure: true,
    swing_points_length: 50,
    swing_bullish_color: "#10b981",
    swing_bearish_color: "#ef4444",
    swing_label_size: "tiny",
    show_swing_points: true,
    show_strong_weak_high_low: true,
    show_order_blocks: true,
    internal_ob_count: 3,
    swing_ob_count: 3,
    ob_filter: "ATR",
    ob_mitigation: "High/Low",
    bullish_ob_color: "#10b981",
    bearish_ob_color: "#ef4444",
    show_equal_high_low: true,
    eq_bars_confirmation: 3,
    eq_threshold: 0.1,
    eq_label_size: "tiny",
    show_fvg: true,
    fvg_auto_threshold: true,
    fvg_timeframe: "Chart",
    fvg_extend: 20,
    mtf_daily: true,
    mtf_weekly: true,
    mtf_monthly: true,
    mtf_color: "#3b82f6",
    show_premium_discount: true,
    premium_color: "#ef4444",
    equilibrium_color: "#ec4899",
    discount_color: "#10b981",
    plot_candles: true,
    show_boxes: true,
    show_panel_labels: true,
    show_lines: true,
    precision: "Default",
    labels_on_price_scale: true,
    values_in_status_line: true,
    inputs_in_status_line: true,
    vis_ticks: true,
    vis_seconds: true,
    vis_minutes: true,
    vis_hours: true,
    vis_days: true,
    vis_weeks: true,
    vis_months: true,
  },
  frvp: {
    enabled: true,
    num_bins: 50,
    value_area_pct: 70,
    show_poc: true,
    poc_color: "#eab308",
    show_value_area: true,
    vah_color: "#38bdf8",
    val_color: "#38bdf8",
    show_volume_delta: true,
    show_hvn_lvn: true,
    hvn_sensitivity_pct: 40,
  },
  rsi: {
    enabled: true,
    period: 14,
    ma_length: 20,
    overbought: 70,
    oversold: 30,
    band_normal: 40,
    band_strong: 50,
    band_very_strong: 60,
    detect_regular_bullish: true,
    detect_regular_bearish: true,
    detect_hidden_bullish: true,
    detect_hidden_bearish: true,
    pivot_lookback: 5,
    color: "#7e57c2",
  },
};

// Documentation specification interface
export interface IndicatorDoc {
  overview: string;
  theory: string;
  keyFeatures: string[];
  formula: string;
  parametersExplained: { param: string; description: string }[];
  tradingEdge: string;
  docUrl: string;
}

// Indicator Directory item definition
export interface ManaIndicatorItem {
  id: string;
  name: string;
  code: string;
  category: "structure" | "volume" | "momentum" | "trend" | "pivots";
  categoryLabel: string;
  author: string;
  boosts: string;
  description: string;
  isCore: boolean;
  hasSettingsModal: boolean;
  settingsType?: IndicatorType;
  defaultActive?: boolean;
  doc: IndicatorDoc;
}

export const MANA_INDICATORS_DIRECTORY: ManaIndicatorItem[] = [
  {
    id: "cm_ma",
    name: "CM Ultimate Moving Average (9/20 EMA + Yellow Candles)",
    code: "CM-ULTIMATE-MA",
    category: "trend",
    categoryLabel: "Trend & Technicals",
    author: "ChrisMoody / Mana AI",
    boosts: "248.5 K",
    description: "CM Ultimate Dual EMA (9 Fast & 20 Slow) with Yellow Crossing Candle Alerts and Chop Box Compression Filter",
    isCore: true,
    hasSettingsModal: false,
    defaultActive: true,
    doc: {
      overview: "CM Ultimate Moving Average pairs a 9-period Fast EMA and a 20-period Slow EMA with automated Yellow Crossing Candle alerts when momentum shifts across the baseline.",
      theory: "Created by ChrisMoody on TradingView, this benchmark trend-following indicator uses dual exponential smoothing to filter market noise. High-momentum crossover bars are highlighted in yellow, while consolidation periods inside the chop box warn against false breakout entries.",
      keyFeatures: [
        "9 EMA Fast Trigger Line for rapid trend capture",
        "20 EMA Slow Baseline for dynamic support and resistance",
        "Yellow Crossing Candles alerting to key 9/20 EMA bullish/bearish crossover transitions",
        "Chop Phase detection filtering low-volatility sideways whipsaws",
        "Full synergy with RSI 14 (20 EMA Signal Line) momentum confirmation"
      ],
      formula: "Fast EMA = EMA(Close, 9); Slow EMA = EMA(Close, 20). Crossing Candle = (Close[t] crosses FastEMA) OR (FastEMA crosses SlowEMA).",
      parametersExplained: [
        { param: "Fast EMA Length", description: "Period for fast trigger moving average (default 9)" },
        { param: "Slow EMA Length", description: "Period for baseline trend moving average (default 20)" },
        { param: "Smart Trend Colors", description: "Highlights bullish surge (green), bearish surge (red), and crossing candles (yellow)" }
      ],
      tradingEdge: "Entering on yellow candle confirmation when RSI crosses its 20 EMA signal line produces high-probability trend continuation entries with minimal drawdown.",
      docUrl: "/docs?tab=chart-indicators#cm-ultimate-ma"
    }
  },
  {
    id: "rsi",
    name: "Relative Strength Index (RSI 14 + 20 EMA Signal)",
    code: "RSI-14",
    category: "momentum",
    categoryLabel: "Momentum & Reversals",
    author: "Mana AI",
    boosts: "142.8 K",
    description: "Wilder RSI (14) with 20 EMA Signal Smoothing Line, Multi-Tier Momentum Bands (40/50/60), and Divergence Detection",
    isCore: true,
    hasSettingsModal: true,
    settingsType: "rsi",
    defaultActive: true,
    doc: {
      overview: "Wilder's 14-period Relative Strength Index paired with a 20-period Exponential Moving Average signal smoothing line and automated divergence detection.",
      theory: "Price momentum leads price action. When price prints a new extreme but momentum fails to confirm, an exhaustion divergence occurs, signaling a high-probability mean-reversion or trend continuation. The 20 EMA smoothing line eliminates false whipsaws.",
      keyFeatures: [
        "Wilder smoothed RSI (14 period) + Signal EMA (20 period) for smooth crossovers",
        "Regular Bullish & Bearish Divergence engine for counter-trend reversals",
        "Hidden Bullish & Bearish Divergence engine for strong trend continuation pullback entries",
        "Multi-bar pivot confirmation window to eliminate false repaint signals",
        "Multi-tier overbought/oversold zones (Normal 40/60, Strong 30/70, Extreme 20/80)"
      ],
      formula: "RSI = 100 - (100 / (1 + RS)), where RS = WilderEMA(Gains, 14) / WilderEMA(Losses, 14). Regular Bearish = Price High > Prev High AND RSI High < Prev RSI High.",
      parametersExplained: [
        { param: "RSI Period", description: "Lookback window for gains/losses calculation (default 14)" },
        { param: "Signal MA Length", description: "Exponential moving average smoothed signal line period (default 20)" },
        { param: "Pivot Lookback", description: "Number of confirming bars required to lock a swing pivot for divergence calculation" }
      ],
      tradingEdge: "Hidden Bullish Divergence during an uptrend pullback provides the tightest risk-to-reward continuation entry in options buying.",
      docUrl: "/docs?tab=chart-indicators#rsi-divergence"
    }
  },
  {
    id: "rsi_smc",
    name: "RSI SMC Options Buyer (Engine Overlay)",
    code: "RSI_SMC_OPTIONS_BUYER_V1",
    category: "structure",
    categoryLabel: "Institutional Structure",
    author: "Engine",
    boosts: "—",
    description: "The backend strategy's OWN structure, sweeps, FVGs and prior-day band, served from Python. Analytical view. The strategy is inactive — this draws only.",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: false,
    doc: {
      overview: "Draws what RSI_SMC_OPTIONS_BUYER_V1 computes, using the strategy's own Python modules rather than a second implementation in the browser. The chart and the engine cannot disagree, because there is only one implementation.",
      theory: "This repository already paid for a duplicated rule once: until 2026-09-22 the chart drew its own BUY CE/PE markers with no ADX filter and disagreed with the engine four-to-zero on 2026-09-18 NIFTY. /api/strategy-markers fixed that by moving the rule to the code that trades. This overlay follows the same principle for the SMC objects.",
      keyFeatures: [
        "Structure events (BOS / CHoCH) from the strategy's own causal series",
        "Liquidity sweeps with the swept level and the extreme the wick reached",
        "Rolling extreme levels (lookback 20, recent 5) — the levels the entry rule reads",
        "Unmitigated Fair Value Gaps",
        "Prior-day-extreme band (PDH/PDL ±0.25×ATR) — the frozen rule the recorder is collecting for",
        "Order Blocks are deliberately NOT drawn: Phase 7 blocked them for this strategy"
      ],
      formula: "Served by GET /api/rsi-smc-overlay, which runs structure.build_analytical(), liquidity.reference_sweeps() and levels.compute_daily_levels() from trading_bot/strategies/rsi_smc_options_buyer/.",
      parametersExplained: [
        { param: "View", description: "ANALYTICAL — objects are drawn on the bar that formed them, including ones the live engine could not have confirmed yet. It matches a TradingView-style SMC chart; it is not what the engine saw in real time." },
        { param: "Swing Points Length", description: "5 (strategy default)" },
        { param: "Sweep Lookback / Recent", description: "20 bars / 5 bars" },
        { param: "Prior-day band", description: "0.25 × ATR(14) around the previous day's high and low" }
      ],
      tradingEdge: "None claimed. The strategy is NO-GO and has never been run, live or paper. This overlay exists to read the market the way the strategy reads it, not to signal trades.",
      docUrl: "/docs?tab=chart-indicators#rsi-smc"
    }
  },
  {
    id: "smc",
    name: "Smart Money Concepts (SMC Pro)",
    code: "SMC-PRO",
    category: "structure",
    categoryLabel: "Institutional Structure",
    author: "Mana AI",
    boosts: "167.5 K",
    description: "Internal & Swing Structure (BOS / CHoCH), Order Blocks, Fair Value Gaps (FVG), MTF Highs/Lows, Equilibrium",
    isCore: true,
    hasSettingsModal: true,
    settingsType: "smc",
    defaultActive: true,
    doc: {
      overview: "SMC Pro is an institutional-grade market structure recognition engine that maps where major institutions, liquidity providers, and central banks position liquidity in intraday index auctions.",
      theory: "Financial markets do not move randomly; they continuously auction between pools of resting liquidity (stops). SMC Pro identifies swing pivots, breaks of structure (BOS), changes of character (CHoCH), order blocks, and imbalance fair value gaps (FVG) without lookahead bias.",
      keyFeatures: [
        "Internal Structure vs Swing Structure with 50-bar rolling pivot windows",
        "Bullish & Bearish Order Blocks (OB) with ATR volatility filters and wick mitigation tracking",
        "Fair Value Gap (FVG) detection with auto-threshold and customizable bar extension",
        "Multi-Timeframe (MTF) Highs and Lows (Daily, Weekly, Monthly) for institutional reference levels",
        "Premium vs Discount zones with 50% Equilibrium line"
      ],
      formula: "BOS = Close[t] > SwingHigh[t-1] (Bullish) or Close[t] < SwingLow[t-1] (Bearish). FVG = Low[t-2] > High[t] (Bearish Imbalance) or High[t-2] < Low[t] (Bullish Imbalance).",
      parametersExplained: [
        { param: "Mode", description: "Present (active unmitigated zones only) vs Historical (all historical zones)" },
        { param: "Swing Points Length", description: "Rolling pivot lookback window (default 50) for identifying macro swing highs and lows" },
        { param: "OB Mitigation", description: "Mitigation detection trigger: High/Low wick touch vs Close confirmation" },
        { param: "Equal High/Low Threshold", description: "Maximum price percentage tolerance (0.1%) to classify double highs/lows as liquidity pools" }
      ],
      tradingEdge: "Filter out retail trap breakouts by waiting for liquidity sweeps at EQH/EQL or entering on pullbacks to unmitigated Order Blocks aligned with higher timeframe trend.",
      docUrl: "/docs?tab=chart-indicators#smc"
    }
  },
  {
    id: "frvp",
    name: "Fixed Range Volume Profile (FRVP)",
    code: "FRVP",
    category: "volume",
    categoryLabel: "Auction Volume Flow",
    author: "Mana AI",
    boosts: "94.2 K",
    description: "50 Row Dynamic Price Bins, 70% Value Area Volume, Point of Control (POC), VAH & VAL Boundaries, Volume Delta",
    isCore: true,
    hasSettingsModal: true,
    settingsType: "frvp",
    defaultActive: true,
    doc: {
      overview: "FRVP analyzes auction price distribution by calculating traded volume per price bin, revealing true institutional fair value and acceptance vs rejection zones.",
      theory: "Based on J. Peter Steidlmayer's Auction Market Theory. Price is the advertising mechanism, time regulates opportunity, and volume confirms market acceptance.",
      keyFeatures: [
        "50 dynamic row bins spanning the high-low auction range",
        "70% Value Area Volume (Value Area High / Value Area Low) calculations",
        "Point of Control (POC) level marking peak institutional trade concentration",
        "High Volume Nodes (HVN) for support/resistance and Low Volume Nodes (LVN) for fast rejection slippage",
        "Buyer vs Seller volume delta distribution per price row"
      ],
      formula: "POC = argmax(Volume[bin_i]). Value Area: Cumulative volume sorted outward from POC until sum(Volume) >= 0.70 * TotalVolume.",
      parametersExplained: [
        { param: "Num Bins", description: "Resolution of the profile (default 50 bins across range)" },
        { param: "Value Area %", description: "Percentage of total auction volume included in Value Area (institutional standard 70%)" },
        { param: "HVN Sensitivity", description: "Threshold percentage relative to POC volume to qualify as a High Volume Node" }
      ],
      tradingEdge: "Trades entering inside the Value Area target POC and opposite value boundary. Clean breakouts past VAH/VAL signify new directional auction expansion.",
      docUrl: "/docs?tab=chart-indicators#volume-profile"
    }
  },
  {
    id: "cpr",
    name: "Central Pivot Range (CPR Pro)",
    code: "CPR-PRO",
    category: "pivots",
    categoryLabel: "Floor Pivots & CPR",
    author: "Mana AI",
    boosts: "38.4 K",
    description: "Daily, Weekly & Monthly Central Pivot Range (TC, Pivot, BC) with Camarilla H3/H4 & L3/L4 Breakout Boundaries",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: true,
    doc: {
      overview: "CPR Pro plots the three Central Pivot lines along with Camarilla floor equations to determine day type (trending vs range-bound).",
      theory: "The relationship between Pivot, Bottom Central (BC), and Top Central (TC) reveals the consensus of value from the previous trading session.",
      keyFeatures: [
        "Daily, Weekly, and Monthly CPR levels",
        "Virgin CPR tracking (CPR ranges not tested during session)",
        "Camarilla H3/L3 reversal bands and H4/L4 expansion breakouts",
        "Narrow CPR detection for explosive trend days"
      ],
      formula: "Pivot = (H + L + C) / 3; BC = (H + L) / 2; TC = (Pivot - BC) + Pivot.",
      parametersExplained: [
        { param: "Anchor Period", description: "Daily, Weekly, or Monthly calculation base" },
        { param: "Show Camarilla", description: "Toggle H3/H4 and L3/L4 floor boundaries" }
      ],
      tradingEdge: "A Narrow CPR predicts an expansion trend day. Price opening above TC signals aggressive institutional buying bias.",
      docUrl: "/docs?tab=chart-indicators#cpr"
    }
  },
  {
    id: "vsc",
    name: "Volatility Squeeze & Compression (VSC)",
    code: "VSC-CORE",
    category: "momentum",
    categoryLabel: "Momentum & Reversals",
    author: "Mana AI",
    boosts: "116.3 K",
    description: "Bollinger Bands compression inside Keltner Channels with directional momentum histogram for volatility breakout timing",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: true,
    doc: {
      overview: "VSC identifies periods where market volatility contracts into an explosive pre-breakout compression channel.",
      theory: "Markets oscillate between low volatility consolidation and high volatility expansion. Buying options during compression allows entering right before explosive gamma moves.",
      keyFeatures: [
        "Bollinger Bands (20, 2.0 std dev) contraction inside Keltner Channels (20, 1.5 ATR)",
        "Squeeze On (black dots) vs Squeeze Fired (green dots) visual status",
        "Linear regression momentum histogram indicating breakout direction"
      ],
      formula: "Squeeze = BB_Upper < KC_Upper AND BB_Lower > KC_Lower.",
      parametersExplained: [
        { param: "BB Multiplier", description: "Standard deviation multiplier for outer Bollinger Band (default 2.0)" },
        { param: "KC Multiplier", description: "ATR multiplier for inner Keltner Channel (default 1.5)" }
      ],
      tradingEdge: "When the squeeze fires with momentum shifting above zero, enter long calls with predefined trailing stop.",
      docUrl: "/docs?tab=chart-indicators#squeeze"
    }
  },
  {
    id: "dtr",
    name: "Dynamic Trend Rider (DTR)",
    code: "DTR-ATR",
    category: "trend",
    categoryLabel: "Trend & Technicals",
    author: "Mana AI",
    boosts: "81.8 K",
    description: "Average True Range (ATR 10, Factor 3.0) dynamic trailing band with instant regime shift alerts",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: false,
    doc: {
      overview: "DTR is an adaptive trailing trend filter that dynamically expands and contracts with market volatility.",
      theory: "Fixed stop losses fail in volatile index trading. DTR scales the trailing band using Average True Range (ATR), preventing premature stops during pullbacks.",
      keyFeatures: [
        "10-period ATR with 3.0 multiplier for institutional index noise tolerance",
        "Instant trend shift alerts on bar close",
        "Dynamic colored ribbon indicating current regime status"
      ],
      formula: "UpperBand = (H + L)/2 + Factor * ATR(10); LowerBand = (H + L)/2 - Factor * ATR(10).",
      parametersExplained: [
        { param: "ATR Period", description: "Smoothing lookback for true range calculation" },
        { param: "Multiplier", description: "Distance multiplier applied to ATR" }
      ],
      tradingEdge: "Stay in winning trend runs without guessing the top; trail stop along the DTR band until a confirmed bar closes opposite.",
      docUrl: "/docs?tab=chart-indicators#dtr"
    }
  },
  {
    id: "ils",
    name: "Institutional Liquidity Sweep (ILS)",
    code: "ILS-FLOW",
    category: "structure",
    categoryLabel: "Institutional Structure",
    author: "Mana AI",
    boosts: "12.8 K",
    description: "Unmitigated liquidity pools, equal high/low runs, buy-side & sell-side liquidity sweeps with wick mitigation",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: false,
    doc: {
      overview: "ILS detects false breakouts engineered by market makers to trigger retail stop-loss clusters before reversing.",
      theory: "When price pokes above an old high and immediately closes back inside the range with a long rejection wick, institutional selling has absorbed retail breakout buyers.",
      keyFeatures: [
        "Automated sweep detection on major swing highs and lows",
        "Minimum wick rejection percentage requirement (>60% of candle range)",
        "Volume spike validation on the sweep candle"
      ],
      formula: "BullSweep = High[t] > SwingHigh AND Close[t] < SwingHigh AND (High[t]-Close[t]) > 0.60*(High[t]-Low[t]).",
      parametersExplained: [
        { param: "Wick Threshold", description: "Minimum upper/lower wick percentage of candle range required" }
      ],
      tradingEdge: "Enter immediately after a sweep candle closes back inside the structure, targeting the opposite liquidity pool.",
      docUrl: "/docs?tab=chart-indicators#liquidity-sweep"
    }
  },
  {
    id: "etr",
    name: "Exponential Trend Ribbon (ETR)",
    code: "ETR-921",
    category: "trend",
    categoryLabel: "Trend & Technicals",
    author: "Mana AI",
    boosts: "64.7 K",
    description: "9 EMA Fast Trigger, 21 EMA Baseline Trend, 50 & 200 EMA Institutional Trend Filters with dynamic slope coloring",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: true,
    doc: {
      overview: "ETR aligns short, medium, and long term exponential moving averages to ensure all trades align with the dominant trend.",
      theory: "Moving average ribbons prevent counter-trend trading by verifying that all timeframes agree on direction before signal generation.",
      keyFeatures: [
        "9 EMA (Fast Signal Line)",
        "21 EMA (Dynamic Intraday Support/Resistance)",
        "50 EMA (Intermediate Trend Anchor)",
        "200 EMA (Macro Institutional Trend Line)"
      ],
      formula: "EMA[t] = Close[t] * (2 / (N + 1)) + EMA[t-1] * (1 - (2 / (N + 1))).",
      parametersExplained: [
        { param: "Periods", description: "Fast 9, Medium 21, Intermediate 50, Baseline 200" }
      ],
      tradingEdge: "Only take Long trades when 9 > 21 > 50 > 200; only take Short trades when 9 < 21 < 50 < 200.",
      docUrl: "/docs?tab=chart-indicators#ema-ribbon"
    }
  },
  {
    id: "vwap",
    name: "Intraday VWAP & Deviation Bands (VWAP Pro)",
    code: "VWAP-PRO",
    category: "volume",
    categoryLabel: "Auction Volume Flow",
    author: "Mana AI",
    boosts: "75.3 K",
    description: "Intraday Volume Weighted Average Price with 1st, 2nd, and 3rd standard deviation bands and session resets",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: true,
    doc: {
      overview: "VWAP Pro benchmarks the true intraday average price weighted by traded volume, reset every morning at 09:15 IST.",
      theory: "Institutional algorithms are benchmarked to VWAP execution. Big funds buy below VWAP to get a discount and sell above VWAP to maximize execution alpha.",
      keyFeatures: [
        "Session anchor reset at 09:15 IST",
        "+/- 1 Sigma and +/- 2 Sigma statistical deviation bands",
        "Dynamic color shading based on price position relative to VWAP"
      ],
      formula: "VWAP = sum(TypicalPrice * Volume) / sum(Volume); Sigma = sqrt(sum(Volume * (TypicalPrice - VWAP)^2) / sum(Volume)).",
      parametersExplained: [
        { param: "Session Reset", description: "Anchor time (09:15 IST for Indian equity indices)" },
        { param: "Bands", description: "Multipliers for standard deviation envelopes (1.0, 2.0, 3.0)" }
      ],
      tradingEdge: "Mean-reversion trades from 2-Sigma back to VWAP; trend continuation trades entering on VWAP pullbacks.",
      docUrl: "/docs?tab=chart-indicators#vwap"
    }
  },
  {
    id: "macd",
    name: "MACD Trend Momentum Oscillator",
    code: "MACD-1226",
    category: "momentum",
    categoryLabel: "Momentum & Reversals",
    author: "Mana AI",
    boosts: "52.1 K",
    description: "Moving Average Convergence Divergence (12, 26, 9) signal line crossovers and zero-lag momentum histogram",
    isCore: false,
    hasSettingsModal: false,
    defaultActive: false,
    doc: {
      overview: "MACD calculates the relationship between two exponential moving averages to measure trend acceleration and deceleration.",
      theory: "When the difference between fast and slow moving averages expands, momentum accelerates. Histogram color shifts precede price reversals.",
      keyFeatures: [
        "12 EMA Fast minus 26 EMA Slow",
        "9 EMA Signal line",
        "Color-coded momentum histogram (Dark/Light Green for expansion/contraction, Dark/Light Red for bearish)"
      ],
      formula: "MACD Line = EMA(12) - EMA(26); Signal Line = EMA(MACD, 9); Histogram = MACD Line - Signal Line.",
      parametersExplained: [
        { param: "Fast Length", description: "Short-term exponential period (default 12)" },
        { param: "Slow Length", description: "Long-term exponential period (default 26)" },
        { param: "Signal Length", description: "Signal smoothing period (default 9)" }
      ],
      tradingEdge: "Zero-line crosses confirm macro direction; histogram momentum deceleration warns of impending pullback.",
      docUrl: "/docs?tab=chart-indicators#macd"
    }
  },
];

export interface IndicatorSettingsProps {
  isModal?: boolean;
  onClose?: () => void;
}

export default function IndicatorSettings({ isModal = false, onClose }: IndicatorSettingsProps) {
  const [settings, setSettings] = useState<IndicatorSettingsData>(defaultIndicatorSettings);
  const [activeModal, setActiveModal] = useState<IndicatorType | null>(null);
  const [selectedDocItem, setSelectedDocItem] = useState<ManaIndicatorItem | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [favorites, setFavorites] = useState<string[]>(["cm_ma", "rsi", "smc", "frvp"]);
  const [activeIndicators, setActiveIndicators] = useState<Record<string, boolean>>({
    cm_ma: true,
    rsi: true,
    rsi_smc: false,
    smc: true,
    frvp: true,
    cpr: true,
    vsc: true,
    etr: true,
    vwap: true,
  });

  // Load settings & favorites from localStorage / backend
  useEffect(() => {
    try {
      const savedFavs = localStorage.getItem("mana_favorite_indicators");
      if (savedFavs) {
        setFavorites(JSON.parse(savedFavs));
      }

      const appliedRaw = localStorage.getItem("mana_applied_indicators");
      if (appliedRaw) {
        try {
          const applied = JSON.parse(appliedRaw);
          setActiveIndicators((prev) => ({
            ...prev,
            cm_ma: applied.ema1 !== undefined ? (Boolean(applied.ema1) || Boolean(applied.smartTrend)) : prev.cm_ma,
            rsi: applied.rsi !== undefined ? Boolean(applied.rsi) : prev.rsi,
            smc: applied.smc !== undefined ? Boolean(applied.smc) : prev.smc,
            frvp: applied.frvp !== undefined ? Boolean(applied.frvp) : prev.frvp,
            rsi_smc: applied.rsiSmc !== undefined ? Boolean(applied.rsiSmc) : prev.rsi_smc,
          }));
        } catch {}
      }

      const local = localStorage.getItem("mana_indicator_settings");
      if (local) {
        const parsed = JSON.parse(local);
        setSettings((prev) => ({ ...prev, ...parsed }));
        setActiveIndicators((prev) => ({
          ...prev,
          smc: parsed.smc?.color_candles ?? prev.smc,
          frvp: parsed.frvp?.enabled ?? prev.frvp,
          rsi: parsed.rsi?.enabled ?? prev.rsi,
        }));
      }

      fetch("/api/settings")
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data?.indicator_settings) {
            setSettings((prev) => ({ ...prev, ...data.indicator_settings }));
          }
        })
        .catch((e) => console.error("Could not fetch indicator settings", e));
    } catch (e) {
      console.error("Error loading indicator favorites/settings:", e);
    }
  }, []);

  // Toggle favorite
  const toggleFavorite = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setFavorites((prev) => {
      const next = prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id];
      localStorage.setItem("mana_favorite_indicators", JSON.stringify(next));
      return next;
    });
  };

  // Toggle active status
  const toggleActive = async (item: ManaIndicatorItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const newStatus = !activeIndicators[item.id];
    setActiveIndicators((prev) => ({ ...prev, [item.id]: newStatus }));

    if (item.id === "cm_ma") {
      try {
        const raw = localStorage.getItem("mana_applied_indicators");
        const next = { ...(raw ? JSON.parse(raw) : {}), ema1: newStatus, ema2: newStatus, smartTrend: newStatus };
        localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
      } catch {}
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("chart:cm-ma-toggled", { detail: { value: newStatus } }));
      }
      return;
    }

    if (item.id === "rsi") {
      try {
        const raw = localStorage.getItem("mana_applied_indicators");
        const next = { ...(raw ? JSON.parse(raw) : {}), rsi: newStatus };
        localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
      } catch {}
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("chart:rsi-toggled", { detail: { value: newStatus } }));
      }
    }

    if (item.id === "rsi_smc") {
      // This one has no settings payload -- it is served whole by the
      // backend. Applying it only tells the chart to draw it.
      try {
        const raw = localStorage.getItem("mana_applied_indicators");
        const next = { ...(raw ? JSON.parse(raw) : {}), rsiSmc: newStatus };
        localStorage.setItem("mana_applied_indicators", JSON.stringify(next));
      } catch {}
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("chart:rsi-smc-toggled",
          { detail: { value: newStatus } }));
      }
      return;
    }

    if (item.settingsType) {
      const updated = { ...settings };
      if (item.settingsType === "smc") {
        updated.smc = { ...updated.smc, color_candles: newStatus };
      } else if (item.settingsType === "frvp") {
        updated.frvp = { ...updated.frvp, enabled: newStatus };
      } else if (item.settingsType === "rsi") {
        updated.rsi = { ...updated.rsi, enabled: newStatus };
      }
      setSettings(updated);
      localStorage.setItem("mana_indicator_settings", JSON.stringify(updated));

      // Broadcast event so chart updates immediately
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("indicatorSettingsChanged", {
            detail: { indicator: item.settingsType, settings: updated },
          })
        );
      }

      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indicator_settings: updated }),
      }).catch(() => {});
    }
  };

  // Filter indicators
  const filteredIndicators = useMemo(() => {
    return MANA_INDICATORS_DIRECTORY.filter((ind) => {
      // Category filter
      if (activeCategory === "favorites" && !favorites.includes(ind.id)) return false;
      if (activeCategory === "active" && !activeIndicators[ind.id]) return false;
      if (activeCategory === "core" && !ind.isCore) return false;
      if (["structure", "volume", "momentum", "trend", "pivots"].includes(activeCategory)) {
        if (ind.category !== activeCategory) return false;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matchesName = ind.name.toLowerCase().includes(query);
        const matchesDesc = ind.description.toLowerCase().includes(query);
        const matchesAuthor = ind.author.toLowerCase().includes(query);
        const matchesCode = ind.code.toLowerCase().includes(query);
        const matchesCategory = ind.categoryLabel.toLowerCase().includes(query);
        return matchesName || matchesDesc || matchesAuthor || matchesCode || matchesCategory;
      }

      return true;
    });
  }, [searchQuery, activeCategory, favorites, activeIndicators]);

  const content = (
    <div className="w-full bg-[#131722] border border-[#2a2e39] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh] text-[#d1d4dc] font-sans select-none">
      {/* Top Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2e39] bg-[#1e222d]/90">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10 text-primary border border-primary/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-[#f0f3fa] tracking-tight flex items-center gap-2.5">
              Indicators, Metrics & Strategies
              <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                MANA AI
              </span>
            </h1>
            <p className="text-xs text-[#787b86] mt-0.5">
              Institutional Algorithmic Engines & Quantitative Strategy Directory
            </p>
          </div>
        </div>

        {isModal && onClose && (
          <button
            onClick={onClose}
            className="text-[#787b86] hover:text-[#f0f3fa] p-1.5 rounded-lg hover:bg-[#2a2e39] transition-colors"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Search Bar matching TradingView */}
      <div className="px-6 py-3.5 border-b border-[#2a2e39] bg-[#171b26]">
        <div className="relative flex items-center">
          <Search className="absolute left-3.5 w-4 h-4 text-[#787b86]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search indicators, algorithms, metrics..."
            className="w-full bg-[#1e222d] border border-[#2a2e39] focus:border-[#2962ff] rounded-xl pl-10 pr-10 py-2 text-sm text-[#f0f3fa] placeholder-[#787b86] outline-none transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3.5 text-[#787b86] hover:text-[#f0f3fa] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Main Body: Two-Column TradingView Layout */}
      <div className="flex-1 flex overflow-hidden min-h-[500px]">
        {/* Left Sidebar: Categories */}
        <div className="w-60 border-r border-[#2a2e39] bg-[#171b26]/70 p-3 overflow-y-auto space-y-4 shrink-0">
          {/* Section: PERSONAL */}
          <div>
            <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-[#787b86]">
              Personal
            </div>
            <div className="space-y-0.5 mt-1">
              <button
                type="button"
                onClick={() => setActiveCategory("favorites")}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "favorites"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                  Favorites
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#2a2e39] text-[#787b86]">
                  {favorites.length}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("active")}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "active"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  Active on Chart
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#2a2e39] text-[#787b86]">
                  {Object.values(activeIndicators).filter(Boolean).length}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("core")}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "core"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  Core Engines
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#2a2e39] text-[#787b86]">
                  {MANA_INDICATORS_DIRECTORY.filter((i) => i.isCore).length}
                </span>
              </button>
            </div>
          </div>

          {/* Section: BUILT-IN ENGINES */}
          <div>
            <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-[#787b86]">
              Built-in Engines
            </div>
            <div className="space-y-0.5 mt-1">
              <button
                type="button"
                onClick={() => setActiveCategory("structure")}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "structure"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <Layers className="w-3.5 h-3.5 text-emerald-400" />
                Institutional Structure
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("volume")}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "volume"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
                Auction Volume Flow
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("momentum")}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "momentum"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <Activity className="w-3.5 h-3.5 text-purple-400" />
                Momentum & Reversals
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("trend")}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "trend"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5 text-blue-400" />
                Trend & Technicals
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory("pivots")}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === "pivots"
                    ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                    : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
                }`}
              >
                <Compass className="w-3.5 h-3.5 text-cyan-400" />
                Floor Pivots & CPR
              </button>
            </div>
          </div>

          {/* Section: ALL DIRECTORY */}
          <div className="pt-2 border-t border-[#2a2e39]">
            <button
              type="button"
              onClick={() => setActiveCategory("all")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeCategory === "all"
                  ? "bg-[#2962ff]/15 text-[#2962ff] font-bold"
                  : "text-[#d1d4dc] hover:bg-[#1e222d] hover:text-[#f0f3fa]"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <Sliders className="w-3.5 h-3.5 text-[#787b86]" />
                All Indicators
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#2a2e39] text-[#787b86]">
                {MANA_INDICATORS_DIRECTORY.length}
              </span>
            </button>
          </div>
        </div>

        {/* Right Main Area: TradingView Table Directory */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[#131722]">
          {/* Table Header */}
          <div className="grid grid-cols-12 px-6 py-2.5 border-b border-[#2a2e39] text-[11px] font-bold uppercase tracking-wider text-[#787b86] bg-[#1e222d]/40">
            <div className="col-span-5 flex items-center gap-4">
              <span className="w-4" />
              <span>Name</span>
            </div>
            <div className="col-span-2">Author</div>
            <div className="col-span-1 text-right">Boosts</div>
            <div className="col-span-4 text-right pr-2">Actions & Docs</div>
          </div>

          {/* Table Rows */}
          <div className="flex-1 overflow-y-auto divide-y divide-[#2a2e39]/50">
            {filteredIndicators.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-center p-6 space-y-2">
                <Search className="w-8 h-8 text-[#787b86]/50" />
                <p className="text-sm font-semibold text-[#f0f3fa]">No indicators match your criteria</p>
                <p className="text-xs text-[#787b86]">Try searching with a different term or change category filter.</p>
              </div>
            ) : (
              filteredIndicators.map((ind) => {
                const isFav = favorites.includes(ind.id);
                const isActive = !!activeIndicators[ind.id];

                return (
                  <div
                    key={ind.id}
                    onClick={() => {
                      if (ind.hasSettingsModal && ind.settingsType) {
                        setActiveModal(ind.settingsType);
                      } else {
                        setSelectedDocItem(ind);
                      }
                    }}
                    className="grid grid-cols-12 items-center px-6 py-3 hover:bg-[#1e222d]/60 transition-colors group cursor-pointer"
                  >
                    {/* Column 1: Star & Name */}
                    <div className="col-span-5 flex items-center gap-3.5 pr-4 min-w-0">
                      {/* Star Button */}
                      <button
                        type="button"
                        onClick={(e) => toggleFavorite(ind.id, e)}
                        className="text-[#787b86] hover:text-amber-400 transition-colors shrink-0 p-0.5"
                        title={isFav ? "Remove from Favorites" : "Add to Favorites"}
                      >
                        <Star
                          className={`w-4 h-4 ${
                            isFav ? "text-amber-400 fill-amber-400" : "text-[#787b86]/70"
                          }`}
                        />
                      </button>

                      {/* Name & Subtitle */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-[#f0f3fa] group-hover:text-primary transition-colors truncate">
                            {ind.name}
                          </span>
                          {ind.isCore && (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-primary/20 text-primary border border-primary/30 shrink-0">
                              CORE
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#787b86] truncate mt-0.5">
                          {ind.description}
                        </p>
                      </div>
                    </div>

                    {/* Column 2: Author (Mana AI for all) */}
                    <div className="col-span-2 min-w-0 pr-2">
                      <span className="text-xs text-[#38bdf8] hover:underline font-semibold cursor-pointer truncate flex items-center gap-1">
                        {ind.author}
                        <Check className="w-3 h-3 text-emerald-400" />
                      </span>
                      <span className="text-[10px] text-[#787b86] font-mono block truncate">
                        {ind.categoryLabel}
                      </span>
                    </div>

                    {/* Column 3: Boosts */}
                    <div className="col-span-1 text-right font-mono text-xs text-[#d1d4dc]">
                      {ind.boosts}
                    </div>

                    {/* Column 4: Actions & Documentation Link */}
                    <div className="col-span-4 flex items-center justify-end gap-2 pr-2">
                      {/* Documentation Link Button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedDocItem(ind);
                        }}
                        className="px-2 py-1 rounded text-[11px] font-medium text-[#787b86] hover:text-[#38bdf8] hover:bg-[#2a2e39] transition-colors flex items-center gap-1 border border-transparent hover:border-[#38bdf8]/30"
                        title="View Full Indicator Documentation & Formulas"
                      >
                        <BookOpen className="w-3.5 h-3.5 text-[#38bdf8]" />
                        <span className="hidden sm:inline">Docs</span>
                        <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                      </button>

                      {/* Settings Gear (opens modal) */}
                      {ind.hasSettingsModal && ind.settingsType && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveModal(ind.settingsType!);
                          }}
                          className="p-1.5 rounded-lg text-[#787b86] hover:text-[#f0f3fa] hover:bg-[#2a2e39] transition-colors"
                          title="Configure Parameters (Inputs, Style, Visibility)"
                        >
                          <Settings2 className="w-4 h-4" />
                        </button>
                      )}

                      {/* Active / Add Button */}
                      <button
                        type="button"
                        onClick={(e) => toggleActive(ind, e)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1.5 ${
                          isActive
                            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25"
                            : "bg-[#2a2e39] text-[#787b86] hover:text-[#f0f3fa] hover:bg-[#363a45]"
                        }`}
                        title={isActive ? "Active in trading system" : "Click to activate"}
                      >
                        {isActive ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" />
                            Active
                          </>
                        ) : (
                          <>
                            <Plus className="w-3 h-3" />
                            Add
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Settings Parameter Modal */}
      {activeModal && (
        <TradingViewIndicatorModal
          isOpen={true}
          indicator={activeModal}
          onClose={() => setActiveModal(null)}
          onOpenDocs={(indKey) => {
            const found = MANA_INDICATORS_DIRECTORY.find((item) => item.id === indKey);
            if (found) setSelectedDocItem(found);
          }}
        />
      )}

      {/* Comprehensive In-App Documentation Modal */}
      <AnimatePresence>
        {selectedDocItem && (
          <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-in fade-in duration-150">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              transition={{ duration: 0.15 }}
              className="w-full max-w-2xl bg-[#1e222d] border border-[#2a2e39] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] text-[#d1d4dc] font-sans"
            >
              {/* Doc Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2e39] bg-[#171b26]">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-primary/10 text-primary border border-primary/20">
                    <BookOpen className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#f0f3fa] tracking-tight flex items-center gap-2">
                      {selectedDocItem.name}
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        {selectedDocItem.code}
                      </span>
                    </h2>
                    <p className="text-xs text-[#787b86] mt-0.5 flex items-center gap-2">
                      <span>Author: <strong className="text-[#38bdf8]">{selectedDocItem.author}</strong></span>
                      <span>•</span>
                      <span>{selectedDocItem.categoryLabel}</span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedDocItem(null)}
                  className="text-[#787b86] hover:text-[#f0f3fa] p-1.5 rounded-lg hover:bg-[#2a2e39] transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Doc Modal Body */}
              <div className="p-6 overflow-y-auto space-y-6 text-sm">
                {/* Overview */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#38bdf8] flex items-center gap-2">
                    <Info className="w-3.5 h-3.5" />
                    Overview & Objective
                  </h3>
                  <p className="text-xs text-[#d1d4dc] leading-relaxed bg-[#131722]/80 p-3.5 rounded-xl border border-[#2a2e39]">
                    {selectedDocItem.doc.overview}
                  </p>
                </div>

                {/* Theoretical Foundation */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#38bdf8] flex items-center gap-2">
                    <Layers className="w-3.5 h-3.5" />
                    Market Theory & Core Engine
                  </h3>
                  <p className="text-xs text-[#d1d4dc] leading-relaxed bg-[#131722]/80 p-3.5 rounded-xl border border-[#2a2e39]">
                    {selectedDocItem.doc.theory}
                  </p>
                </div>

                {/* Key Features */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#38bdf8] flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5" />
                    Algorithmic Capabilities
                  </h3>
                  <ul className="space-y-1.5 bg-[#131722]/80 p-3.5 rounded-xl border border-[#2a2e39] text-xs">
                    {selectedDocItem.doc.keyFeatures.map((feat, i) => (
                      <li key={i} className="flex items-start gap-2 text-[#d1d4dc]">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Mathematical Formula */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#38bdf8] flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5" />
                    Mathematical Calculation
                  </h3>
                  <div className="bg-[#131722] p-3 rounded-xl border border-[#2a2e39] font-mono text-[11px] text-emerald-400 overflow-x-auto leading-relaxed">
                    {selectedDocItem.doc.formula}
                  </div>
                </div>

                {/* Parameters Explained */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#38bdf8] flex items-center gap-2">
                    <Sliders className="w-3.5 h-3.5" />
                    Parameters & Inputs Guide
                  </h3>
                  <div className="rounded-xl border border-[#2a2e39] overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-[#171b26] text-[#787b86] font-bold uppercase text-[10px] border-b border-[#2a2e39]">
                        <tr>
                          <th className="px-3.5 py-2">Parameter</th>
                          <th className="px-3.5 py-2">Explanation</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2a2e39]/50 bg-[#131722]/50 text-xs">
                        {selectedDocItem.doc.parametersExplained.map((p, idx) => (
                          <tr key={idx} className="hover:bg-[#1e222d]/40">
                            <td className="px-3.5 py-2 font-mono font-bold text-amber-400">{p.param}</td>
                            <td className="px-3.5 py-2 text-[#d1d4dc]">{p.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Trading Edge */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
                    <Shield className="w-3.5 h-3.5" />
                    Institutional Trading Edge
                  </h3>
                  <p className="text-xs text-emerald-300 leading-relaxed bg-emerald-500/10 p-3.5 rounded-xl border border-emerald-500/25">
                    {selectedDocItem.doc.tradingEdge}
                  </p>
                </div>
              </div>

              {/* Doc Modal Footer */}
              <div className="flex items-center justify-between px-6 py-3.5 border-t border-[#2a2e39] bg-[#171b26]">
                <a
                  href={selectedDocItem.doc.docUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-semibold text-[#38bdf8] hover:underline flex items-center gap-1.5"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open Full Architecture Docs in New Tab
                </a>

                <div className="flex items-center gap-2.5">
                  {selectedDocItem.hasSettingsModal && selectedDocItem.settingsType && (
                    <button
                      type="button"
                      onClick={() => {
                        const type = selectedDocItem.settingsType;
                        setSelectedDocItem(null);
                        if (type) setActiveModal(type);
                      }}
                      className="px-4 py-1.5 rounded-lg text-xs font-bold text-white bg-[#2962ff] hover:bg-[#1e53e5] transition-all flex items-center gap-1.5"
                    >
                      <Settings2 className="w-3.5 h-3.5" />
                      Configure Parameters
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setSelectedDocItem(null)}
                    className="px-4 py-1.5 rounded-lg text-xs font-semibold text-[#d1d4dc] bg-[#2a2e39] hover:bg-[#363a45] transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );

  if (isModal) {
    return (
      <div className="fixed inset-0 z-[9990] flex items-center justify-center p-4 sm:p-6 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 10 }}
          transition={{ duration: 0.15 }}
          className="w-full max-w-5xl"
        >
          {content}
        </motion.div>
      </div>
    );
  }

  return content;
}
