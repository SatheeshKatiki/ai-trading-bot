/**
 * Strategy-to-Indicator Profiles Registry.
 *
 * VERY IMPORTANT ARCHITECTURAL RULE:
 * Whichever strategy the user selects, ONLY the indicators and signals corresponding
 * to that strategy must be active and visible on the chart.
 * Indicators and signals from other strategies must NEVER contaminate the chart.
 * When switching strategies, the chart automatically updates to display only
 * that strategy's indicators and signals.
 */

export interface StrategyProfile {
  id: string;
  name: string;
  badge: string;
  description: string;
  indicators: {
    ema1: boolean;       // Fast EMA
    ema2: boolean;       // Slow EMA
    rsi: boolean;        // RSI Panel (14 with 20 EMA Smoothing)
    smc: boolean;        // Smart Money Concepts (BOS, CHOCH, Order Blocks, FVGs)
    frvp: boolean;       // Fixed Range Volume Profile (POC, VAH, VAL)
    vol: boolean;        // Volume histogram
    rsiSmc: boolean;     // Backend SMC analytical overlay
    smartTrend: boolean; // CM Ultimate MA Yellow crossing candles & trend highlights
    vwap: boolean;       // VWAP line
  };
  params: {
    ema1Length: number;
    ema2Length: number;
    rsiLength: number;
    rsiMaLength: number;
  };
}

export const STRATEGY_PROFILES: Record<string, StrategyProfile> = {
  ema9_rsi_momentum: {
    id: "ema9_rsi_momentum",
    name: "EMA 9 / RSI Momentum (CM Ultimate MA)",
    badge: "9/20 EMA + RSI",
    description: "CM Ultimate Moving Average (9 EMA & 20 EMA) with Yellow Crossing Candles, RSI 14 (20 EMA smoothed), and Chop Box filter.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,   // Strictly NO SMC
      frvp: false,  // Strictly NO FRVP
      vol: true,
      rsiSmc: false,
      smartTrend: true, // Yellow Crossing Candles
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  rsi_smc_options_buyer: {
    id: "rsi_smc_options_buyer",
    name: "RSI + SMC Options Buyer",
    badge: "SMC + RSI",
    description: "Smart Money Concepts: Order Blocks, Fair Value Gaps, Liquidity Sweeps, Market Structure, and RSI confirmation.",
    indicators: {
      ema1: false,  // Strictly NO EMA
      ema2: false,  // Strictly NO EMA
      rsi: true,
      smc: true,    // SMC ON
      frvp: true,   // FRVP ON
      vol: true,
      rsiSmc: true, // Backend SMC Overlay ON
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  smc_rsi_frvp_options_v1: {
    id: "smc_rsi_frvp_options_v1",
    name: "SMC + RSI + FRVP Options v1",
    badge: "SMC + FRVP",
    description: "Institutional Order Blocks, Fixed Range Volume Profile (POC/VAH/VAL), and RSI divergence setups.",
    indicators: {
      ema1: false,
      ema2: false,
      rsi: true,
      smc: true,
      frvp: true,
      vol: true,
      rsiSmc: true,
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  ema_crossover: {
    id: "ema_crossover",
    name: "Ultra-EMA Crossover Pro",
    badge: "EMA Cross",
    description: "Pure trend-following Dual EMA crossover system (9 Fast EMA & 21 Slow EMA).",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: false,   // NO RSI
      smc: false,   // NO SMC
      frvp: false,  // NO FRVP
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 21,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  ema_rsi: {
    id: "ema_rsi",
    name: "EMA + RSI Classical",
    badge: "EMA + RSI",
    description: "Classic Exponential Moving Average trend filter with Relative Strength Index.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: false,
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  institutional_momentum: {
    id: "institutional_momentum",
    name: "Institutional Momentum (15/5)",
    badge: "Inst. Momentum",
    description: "Institutional volume breakout, 15/5 Momentum squeeze, and VWAP value zones.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: true,
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: true,
    },
    params: {
      ema1Length: 15,
      ema2Length: 5,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  momentum_15_5: {
    id: "momentum_15_5",
    name: "Momentum 15/5 Scalp",
    badge: "15/5 Scalp",
    description: "Fast 15-period and 5-period momentum scalp strategy.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: false,
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 15,
      ema2Length: 5,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  structure_break: {
    id: "structure_break",
    name: "Market Structure Breakout",
    badge: "Structure Break",
    description: "Swing high/low breakouts and structure shifts with Volume Profile validation.",
    indicators: {
      ema1: false,
      ema2: false,
      rsi: false,
      smc: true,
      frvp: true,
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  advanced_ai: {
    id: "advanced_ai",
    name: "Advanced AI / ML Regime",
    badge: "AI Ensemble",
    description: "Machine Learning regime classification with volatility bands and volume profiles.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: true,
      vol: true,
      rsiSmc: false,
      smartTrend: true,
      vwap: true,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  enhanced_ai: {
    id: "enhanced_ai",
    name: "Enhanced AI Multi-Brain",
    badge: "Enhanced AI",
    description: "Multi-model AI architecture with dynamic thresholding and trend confirmation.",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: true,
      vol: true,
      rsiSmc: false,
      smartTrend: true,
      vwap: true,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  meta_agent_swarm: {
    id: "meta_agent_swarm",
    name: "Meta-Agent AI Swarm (5 Brains)",
    badge: "AI Swarm",
    description: "Consensus voting of 5 specialized agents (Trend, Momentum, Volatility, Volume, Pattern).",
    indicators: {
      ema1: true,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: true,
      vol: true,
      rsiSmc: false,
      smartTrend: true,
      vwap: false,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  },
  buy_the_dip: {
    id: "buy_the_dip",
    name: "Buy The Dip Mean Reversion",
    badge: "Buy The Dip",
    description: "Oversold RSI dip buying with VWAP and 20 EMA dynamic support.",
    indicators: {
      ema1: false,
      ema2: true,
      rsi: true,
      smc: false,
      frvp: false,
      vol: true,
      rsiSmc: false,
      smartTrend: false,
      vwap: true,
    },
    params: {
      ema1Length: 9,
      ema2Length: 20,
      rsiLength: 14,
      rsiMaLength: 20,
    }
  }
};

/** Get the profile for a given strategy ID, falling back to default ema9_rsi_momentum */
export function getStrategyProfile(strategyId?: string): StrategyProfile {
  if (strategyId && STRATEGY_PROFILES[strategyId]) {
    return STRATEGY_PROFILES[strategyId];
  }
  return STRATEGY_PROFILES.ema9_rsi_momentum;
}
