/**
 * Institutional Algorithmic Indicators Engine (Mana AI)
 * Real-time zero-lag calculations for:
 * 1. Smart Money Concepts (SMC): Swing Pivots, BOS, CHoCH, Order Blocks, FVGs
 * 2. Fixed Range Volume Profile (FRVP): 50 Row Bins, POC, VAH (70%), VAL (70%), Delta
 * 3. Momentum RSI Divergence Engine (MDE): Wilder RSI (14) + Signal EMA (20) + Divergences
 */

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

// ============================================================================
// 1. SMART MONEY CONCEPTS (SMC PRO)
// ============================================================================

export interface OrderBlockZone {
  id: string;
  isBullish: boolean;
  top: number;
  bottom: number;
  midpoint: number;
  startIndex: number;
  startTime: number;
  mitigated: boolean;
}

export interface SMCStructureLevel {
  type: "BOS" | "CHoCH";
  isBullish: boolean;
  price: number;
  startIndex: number;
  startTime: number;
  breakIndex: number;
  breakTime: number;
}

export interface SMCSwingPivot {
  time: number;
  price: number;
  type: "HH" | "LH" | "HL" | "LL" | "EQH" | "EQL" | "H" | "L";
  isHigh: boolean;
  label: string;
}

export interface SMCLiquidityLevel {
  type: "PDH" | "PDL" | "PWH" | "PWL";
  price: number;
  time: number;
  sessionStartTime?: number;
  label: string;
}

export interface SMCEqualPivotPair {
  type: "EQH" | "EQL";
  time1: number;
  time2: number;
  price: number;
}

export interface SMCDealingRange {
  top: number;
  bottom: number;
  equilibrium: number;
  startTime: number;
  endTime: number;
}

export interface SMCResult {
  bullishOrderBlocks: OrderBlockZone[];
  bearishOrderBlocks: OrderBlockZone[];
  structures: SMCStructureLevel[];
  swingHighs: { index: number; time: number; price: number }[];
  swingLows: { index: number; time: number; price: number }[];
  swingPivots: SMCSwingPivot[];
  strongHigh: { time: number; price: number } | null;
  strongLow: { time: number; price: number } | null;
  weakHigh: { time: number; price: number } | null;
  weakLow: { time: number; price: number } | null;
  equalPivots: SMCEqualPivotPair[];
  sessionStarts: number[];
  dealingRange: SMCDealingRange | null;
  mtfLevels: SMCLiquidityLevel[];
  equilibrium: number;
  rangeHigh: number;
  rangeLow: number;
}

export function computeSMC(candles: Candle[], lookbackWindow: number = 150): SMCResult {
  if (!candles || candles.length < 10) {
    return {
      bullishOrderBlocks: [],
      bearishOrderBlocks: [],
      structures: [],
      swingHighs: [],
      swingLows: [],
      swingPivots: [],
      strongHigh: null,
      strongLow: null,
      weakHigh: null,
      weakLow: null,
      equalPivots: [],
      sessionStarts: [],
      dealingRange: null,
      mtfLevels: [],
      equilibrium: 0,
      rangeHigh: 0,
      rangeLow: 0,
    };
  }

  const startIdx = Math.max(0, candles.length - lookbackWindow);
  const data = candles.slice(startIdx);
  const n = data.length;

  const swingHighs: { index: number; time: number; price: number }[] = [];
  const swingLows: { index: number; time: number; price: number }[] = [];

  // 1. Detect 5-bar swing pivots (2 left, 2 right)
  for (let i = 2; i < n - 2; i++) {
    const cur = data[i];
    if (
      cur.high >= data[i - 1].high &&
      cur.high > data[i - 2].high &&
      cur.high >= data[i + 1].high &&
      cur.high > data[i + 2].high
    ) {
      swingHighs.push({ index: startIdx + i, time: cur.time, price: cur.high });
    }
    if (
      cur.low <= data[i - 1].low &&
      cur.low < data[i - 2].low &&
      cur.low <= data[i + 1].low &&
      cur.low < data[i + 2].low
    ) {
      swingLows.push({ index: startIdx + i, time: cur.time, price: cur.low });
    }
  }

  // 1b. Classify Swing Pivots (HH, LH, EQH / HL, LL, EQL)
  const swingPivots: SMCSwingPivot[] = [];

  for (let i = 0; i < swingHighs.length; i++) {
    const cur = swingHighs[i];
    if (i === 0) {
      swingPivots.push({ time: cur.time, price: cur.price, type: "H", isHigh: true, label: "H" });
    } else {
      const prev = swingHighs[i - 1];
      const diff = Math.abs(cur.price - prev.price) / prev.price;
      let type: "HH" | "LH" | "EQH" = "LH";
      if (diff <= 0.0015) {
        type = "EQH";
      } else if (cur.price > prev.price) {
        type = "HH";
      }
      swingPivots.push({ time: cur.time, price: cur.price, type, isHigh: true, label: type });
    }
  }

  for (let i = 0; i < swingLows.length; i++) {
    const cur = swingLows[i];
    if (i === 0) {
      swingPivots.push({ time: cur.time, price: cur.price, type: "L", isHigh: false, label: "L" });
    } else {
      const prev = swingLows[i - 1];
      const diff = Math.abs(cur.price - prev.price) / prev.price;
      let type: "HL" | "LL" | "EQL" = "HL";
      if (diff <= 0.0015) {
        type = "EQL";
      } else if (cur.price < prev.price) {
        type = "LL";
      }
      swingPivots.push({ time: cur.time, price: cur.price, type, isHigh: false, label: type });
    }
  }

  // 2. Identify BOS & CHoCH Market Structure Shifts
  const structures: SMCStructureLevel[] = [];
  let currentTrend: "BULLISH" | "BEARISH" | "NEUTRAL" = "NEUTRAL";
  let lastBrokenHigh = 0;
  let lastBrokenLow = 0;

  for (let i = 5; i < n; i++) {
    const candle = data[i];
    const prevHighs = swingHighs.filter((sh) => sh.index < startIdx + i && sh.price > lastBrokenHigh);
    const prevLows = swingLows.filter((sl) => sl.index < startIdx + i && sl.price < lastBrokenLow || lastBrokenLow === 0);

    // Bullish break
    if (prevHighs.length > 0) {
      const nearestHigh = prevHighs[prevHighs.length - 1];
      if (candle.close > nearestHigh.price && nearestHigh.price !== lastBrokenHigh) {
        const isChoch = currentTrend === "BEARISH";
        structures.push({
          type: isChoch ? "CHoCH" : "BOS",
          isBullish: true,
          price: nearestHigh.price,
          startIndex: nearestHigh.index,
          startTime: nearestHigh.time,
          breakIndex: startIdx + i,
          breakTime: candle.time,
        });
        currentTrend = "BULLISH";
        lastBrokenHigh = nearestHigh.price;
      }
    }

    // Bearish break
    if (prevLows.length > 0) {
      const nearestLow = prevLows[prevLows.length - 1];
      if (candle.close < nearestLow.price && nearestLow.price !== lastBrokenLow) {
        const isChoch = currentTrend === "BULLISH";
        structures.push({
          type: isChoch ? "CHoCH" : "BOS",
          isBullish: false,
          price: nearestLow.price,
          startIndex: nearestLow.index,
          startTime: nearestLow.time,
          breakIndex: startIdx + i,
          breakTime: candle.time,
        });
        currentTrend = "BEARISH";
        lastBrokenLow = nearestLow.price;
      }
    }
  }

  // 2b. Identify Strong High & Strong Low and Weak High & Weak Low from market structure
  let strongLow: { time: number; price: number } | null = null;
  let strongHigh: { time: number; price: number } | null = null;
  let weakHigh: { time: number; price: number } | null = null;
  let weakLow: { time: number; price: number } | null = null;

  const bullishStructures = structures.filter((s) => s.isBullish);
  if (bullishStructures.length > 0) {
    const latestBull = bullishStructures[bullishStructures.length - 1];
    let minLow = Infinity;
    let minLowTime = latestBull.startTime;
    for (const c of candles) {
      if (c.time >= latestBull.startTime && c.time <= latestBull.breakTime) {
        if (c.low < minLow) {
          minLow = c.low;
          minLowTime = c.time;
        }
      }
    }
    if (minLow < Infinity) {
      strongLow = { time: minLowTime, price: minLow };
    }
  } else if (swingLows.length > 0) {
    const minLow = swingLows.reduce((min, cur) => (cur.price < min.price ? cur : min), swingLows[0]);
    strongLow = { time: minLow.time, price: minLow.price };
  }

  const bearishStructures = structures.filter((s) => !s.isBullish);
  if (bearishStructures.length > 0) {
    const latestBear = bearishStructures[bearishStructures.length - 1];
    let maxHigh = -Infinity;
    let maxHighTime = latestBear.startTime;
    for (const c of candles) {
      if (c.time >= latestBear.startTime && c.time <= latestBear.breakTime) {
        if (c.high > maxHigh) {
          maxHigh = c.high;
          maxHighTime = c.time;
        }
      }
    }
    if (maxHigh > -Infinity) {
      strongHigh = { time: maxHighTime, price: maxHigh };
    }
  } else if (swingHighs.length > 0) {
    const maxHigh = swingHighs.reduce((max, cur) => (cur.price > max.price ? cur : max), swingHighs[0]);
    strongHigh = { time: maxHigh.time, price: maxHigh.price };
  }

  // Derive Weak High and Weak Low
  if (strongLow) {
    const highsAfter = swingHighs.filter((sh) => sh.time >= strongLow!.time);
    if (highsAfter.length > 0) {
      const highest = highsAfter.reduce((max, cur) => (cur.price > max.price ? cur : max), highsAfter[0]);
      weakHigh = { time: highest.time, price: highest.price };
    } else if (swingHighs.length > 0) {
      const latest = swingHighs[swingHighs.length - 1];
      weakHigh = { time: latest.time, price: latest.price };
    }
  }

  if (strongHigh) {
    const lowsAfter = swingLows.filter((sl) => sl.time >= strongHigh!.time);
    if (lowsAfter.length > 0) {
      const lowest = lowsAfter.reduce((min, cur) => (cur.price < min.price ? cur : min), lowsAfter[0]);
      weakLow = { time: lowest.time, price: lowest.price };
    } else if (swingLows.length > 0) {
      const latest = swingLows[swingLows.length - 1];
      weakLow = { time: latest.time, price: latest.price };
    }
  }

  // 2c. Equal Highs & Equal Lows (Dual-Pivot Pairs) - TradingView LuxAlgo Institutional Standard
  // Only detect recent UNMITIGATED equal pivots (liquidity pools that have NOT yet been swept by subsequent price)
  const unmitigatedEqh: SMCEqualPivotPair[] = [];
  for (let i = 1; i < swingHighs.length; i++) {
    const prev = swingHighs[i - 1];
    const cur = swingHighs[i];
    const diff = Math.abs(cur.price - prev.price) / prev.price;
    if (diff <= 0.0015) {
      const eqPrice = (prev.price + cur.price) / 2;
      // Check if any candle after cur.time breached above this EQH
      let swept = false;
      for (const c of candles) {
        if (c.time > cur.time && c.high > eqPrice) {
          swept = true;
          break;
        }
      }
      if (!swept) {
        unmitigatedEqh.push({ type: "EQH", time1: prev.time, time2: cur.time, price: eqPrice });
      }
    }
  }

  const unmitigatedEql: SMCEqualPivotPair[] = [];
  for (let i = 1; i < swingLows.length; i++) {
    const prev = swingLows[i - 1];
    const cur = swingLows[i];
    const diff = Math.abs(cur.price - prev.price) / prev.price;
    if (diff <= 0.0015) {
      const eqPrice = (prev.price + cur.price) / 2;
      // Check if any candle after cur.time breached below this EQL
      let swept = false;
      for (const c of candles) {
        if (c.time > cur.time && c.low < eqPrice) {
          swept = true;
          break;
        }
      }
      if (!swept) {
        unmitigatedEql.push({ type: "EQL", time1: prev.time, time2: cur.time, price: eqPrice });
      }
    }
  }

  // Keep only the most recent 1 active EQH and 1 active EQL (clean TradingView style, max 2 total)
  const equalPivots: SMCEqualPivotPair[] = [
    ...unmitigatedEqh.slice(-1),
    ...unmitigatedEql.slice(-1),
  ];

  // 3. Detect Order Blocks (Last down candle before bullish impulse, or last up candle before bearish impulse)
  const bullishOrderBlocks: OrderBlockZone[] = [];
  const bearishOrderBlocks: OrderBlockZone[] = [];

  for (let i = 2; i < n - 3; i++) {
    const c1 = data[i];
    const c2 = data[i + 1];
    const c3 = data[i + 2];

    const isBullishImpulse = c1.close <= c1.open && c2.close > c2.open && c3.close > c3.open && c3.close > c1.high;
    if (isBullishImpulse) {
      const top = Math.max(c1.open, c1.close, (c1.high + c1.low) / 2);
      const bottom = c1.low;
      const id = `ob-bull-${startIdx + i}`;

      let mitigated = false;
      for (let j = i + 3; j < n; j++) {
        if (data[j].low <= bottom) {
          mitigated = true;
          break;
        }
      }

      bullishOrderBlocks.push({
        id,
        isBullish: true,
        top,
        bottom,
        midpoint: (top + bottom) / 2,
        startIndex: startIdx + i,
        startTime: c1.time,
        mitigated,
      });
    }

    const isBearishImpulse = c1.close >= c1.open && c2.close < c2.open && c3.close < c3.open && c3.close < c1.low;
    if (isBearishImpulse) {
      const top = c1.high;
      const bottom = Math.min(c1.open, c1.close, (c1.high + c1.low) / 2);
      const id = `ob-bear-${startIdx + i}`;

      let mitigated = false;
      for (let j = i + 3; j < n; j++) {
        if (data[j].high >= top) {
          mitigated = true;
          break;
        }
      }

      bearishOrderBlocks.push({
        id,
        isBullish: false,
        top,
        bottom,
        midpoint: (top + bottom) / 2,
        startIndex: startIdx + i,
        startTime: c1.time,
        mitigated,
      });
    }
  }

  // Active unmitigated order blocks (clean TradingView standard: latest 2 of each)
  const activeBullishOBs = bullishOrderBlocks.filter((ob) => !ob.mitigated).slice(-2);
  const activeBearishOBs = bearishOrderBlocks.filter((ob) => !ob.mitigated).slice(-2);

  // 4. Multi-Timeframe Levels (PDH, PDL, PWH, PWL) in IST (UTC+5:30)
  const mtfLevels: SMCLiquidityLevel[] = [];
  if (candles.length > 0) {
    const dayMap = new Map<string, Candle[]>();
    const weekMap = new Map<string, Candle[]>();

    for (const c of candles) {
      const d = new Date((c.time + 19800) * 1000);
      const yyyy = d.getUTCFullYear();
      const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
      const dd = String(d.getUTCDate()).padStart(2, "0");
      const dateKey = `${yyyy}-${mm}-${dd}`;

      const dayArr = dayMap.get(dateKey) || [];
      dayArr.push(c);
      dayMap.set(dateKey, dayArr);

      const dayOfWeek = d.getUTCDay() || 7;
      const monDate = new Date(d.getTime() - (dayOfWeek - 1) * 86400000);
      const weekKey = `${monDate.getUTCFullYear()}-${String(monDate.getUTCMonth() + 1).padStart(2, "0")}-${String(monDate.getUTCDate()).padStart(2, "0")}`;
      const weekArr = weekMap.get(weekKey) || [];
      weekArr.push(c);
      weekMap.set(weekKey, weekArr);
    }

    const uniqueDays = Array.from(dayMap.keys()).sort();
    const curDayKey = uniqueDays[uniqueDays.length - 1];
    const curDayCandles = dayMap.get(curDayKey) || [];
    const curDayStart = curDayCandles.length > 0 ? curDayCandles[0].time : undefined;

    if (uniqueDays.length >= 2) {
      const prevDayCandles = dayMap.get(uniqueDays[uniqueDays.length - 2]) || [];
      if (prevDayCandles.length > 0) {
        const pdh = Math.max(...prevDayCandles.map((c) => c.high));
        const pdl = Math.min(...prevDayCandles.map((c) => c.low));
        mtfLevels.push({ type: "PDH", price: pdh, time: prevDayCandles[0].time, sessionStartTime: curDayStart, label: `PDH` });
        mtfLevels.push({ type: "PDL", price: pdl, time: prevDayCandles[0].time, sessionStartTime: curDayStart, label: `PDL` });
      }
    } else if (uniqueDays.length === 1) {
      const dayCandles = dayMap.get(uniqueDays[0]) || [];
      if (dayCandles.length > 0) {
        const pdh = Math.max(...dayCandles.map((c) => c.high));
        const pdl = Math.min(...dayCandles.map((c) => c.low));
        mtfLevels.push({ type: "PDH", price: pdh, time: dayCandles[0].time, sessionStartTime: dayCandles[0].time, label: `PDH` });
        mtfLevels.push({ type: "PDL", price: pdl, time: dayCandles[0].time, sessionStartTime: dayCandles[0].time, label: `PDL` });
      }
    }

    const uniqueWeeks = Array.from(weekMap.keys()).sort();
    const curWeekKey = uniqueWeeks[uniqueWeeks.length - 1];
    const curWeekCandles = weekMap.get(curWeekKey) || [];
    const curWeekStart = curWeekCandles.length > 0 ? curWeekCandles[0].time : undefined;

    if (uniqueWeeks.length >= 2) {
      const prevWeekCandles = weekMap.get(uniqueWeeks[uniqueWeeks.length - 2]) || [];
      if (prevWeekCandles.length > 0) {
        const pwh = Math.max(...prevWeekCandles.map((c) => c.high));
        const pwl = Math.min(...prevWeekCandles.map((c) => c.low));
        mtfLevels.push({ type: "PWH", price: pwh, time: prevWeekCandles[0].time, sessionStartTime: curWeekStart, label: `PWH` });
        mtfLevels.push({ type: "PWL", price: pwl, time: prevWeekCandles[0].time, sessionStartTime: curWeekStart, label: `PWL` });
      }
    } else if (uniqueWeeks.length === 1) {
      const weekCandles = weekMap.get(uniqueWeeks[0]) || [];
      if (weekCandles.length > 0) {
        const pwh = Math.max(...weekCandles.map((c) => c.high));
        const pwl = Math.min(...weekCandles.map((c) => c.low));
        mtfLevels.push({ type: "PWH", price: pwh, time: weekCandles[0].time, sessionStartTime: weekCandles[0].time, label: `PWH` });
        mtfLevels.push({ type: "PWL", price: pwl, time: weekCandles[0].time, sessionStartTime: weekCandles[0].time, label: `PWL` });
      }
    }
  }

  // 5. Daily Session Start timestamps (IST)
  const sessionStarts: number[] = [];
  let prevDateStr = "";
  for (const c of candles) {
    const d = new Date((c.time + 19800) * 1000);
    const dateStr = `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
    if (dateStr !== prevDateStr) {
      sessionStarts.push(c.time);
      prevDateStr = dateStr;
    }
  }

  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const c of data) {
    if (c.high > rangeHigh) rangeHigh = c.high;
    if (c.low < rangeLow) rangeLow = c.low;
  }

  const equilibrium = (rangeHigh + rangeLow) / 2;

  // 6. Active Dealing Range
  let dealingRange: SMCDealingRange | null = null;
  if (strongLow && weakHigh && weakHigh.price > strongLow.price) {
    dealingRange = {
      top: weakHigh.price,
      bottom: strongLow.price,
      equilibrium: (weakHigh.price + strongLow.price) / 2,
      startTime: strongLow.time,
      endTime: data[n - 1].time,
    };
  } else if (strongHigh && weakLow && strongHigh.price > weakLow.price) {
    dealingRange = {
      top: strongHigh.price,
      bottom: weakLow.price,
      equilibrium: (strongHigh.price + weakLow.price) / 2,
      startTime: strongHigh.time,
      endTime: data[n - 1].time,
    };
  } else if (rangeHigh > rangeLow) {
    dealingRange = {
      top: rangeHigh,
      bottom: rangeLow,
      equilibrium: (rangeHigh + rangeLow) / 2,
      startTime: data[0].time,
      endTime: data[n - 1].time,
    };
  }

  // Sort swing pivots chronologically (keep latest 2 e.g. LH, HL like TradingView)
  const sortedPivots = [...swingPivots].sort((a, b) => a.time - b.time).slice(-2);

  return {
    bullishOrderBlocks: activeBullishOBs,
    bearishOrderBlocks: activeBearishOBs,
    structures: structures.slice(-25),
    swingHighs: swingHighs.slice(-4),
    swingLows: swingLows.slice(-4),
    swingPivots: sortedPivots,
    strongHigh,
    strongLow,
    weakHigh,
    weakLow,
    equalPivots,
    sessionStarts,
    dealingRange,
    mtfLevels,
    equilibrium,
    rangeHigh,
    rangeLow,
  };
}

// ============================================================================
// 2. FIXED RANGE VOLUME PROFILE (FRVP)
// ============================================================================

export interface VolumeProfileBinData {
  priceLow: number;
  priceHigh: number;
  priceMid: number;
  totalVolume: number;
  buyVolume: number;
  sellVolume: number;
  delta: number;
  isPoc: boolean;
  isInValueArea: boolean;
}

export interface FRVPResult {
  pocPrice: number;
  vahPrice: number;
  valPrice: number;
  totalVolume: number;
  maxBinVolume: number;
  bins: VolumeProfileBinData[];
  rangeHigh: number;
  rangeLow: number;
}

export function computeFRVP(
  candles: Candle[],
  numBins: number = 50,
  valueAreaPct: number = 70,
  lookbackBars: number = 180
): FRVPResult {
  if (!candles || candles.length === 0) {
    return {
      pocPrice: 0,
      vahPrice: 0,
      valPrice: 0,
      totalVolume: 0,
      maxBinVolume: 0,
      bins: [],
      rangeHigh: 0,
      rangeLow: 0,
    };
  }

  const startIdx = Math.max(0, candles.length - lookbackBars);
  const data = candles.slice(startIdx);

  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  let totalVolume = 0;

  for (const c of data) {
    if (c.high > rangeHigh) rangeHigh = c.high;
    if (c.low < rangeLow) rangeLow = c.low;
    totalVolume += c.volume || 1000;
  }

  const rangeHeight = rangeHigh - rangeLow;
  if (rangeHeight <= 0 || !isFinite(rangeHeight)) {
    return {
      pocPrice: candles[candles.length - 1].close,
      vahPrice: candles[candles.length - 1].close,
      valPrice: candles[candles.length - 1].close,
      totalVolume,
      maxBinVolume: 0,
      bins: [],
      rangeHigh,
      rangeLow,
    };
  }

  const binWidth = rangeHeight / numBins;
  const bins: VolumeProfileBinData[] = [];

  for (let i = 0; i < numBins; i++) {
    const priceLow = rangeLow + i * binWidth;
    const priceHigh = priceLow + binWidth;
    bins.push({
      priceLow,
      priceHigh,
      priceMid: (priceLow + priceHigh) / 2,
      totalVolume: 0,
      buyVolume: 0,
      sellVolume: 0,
      delta: 0,
      isPoc: false,
      isInValueArea: false,
    });
  }

  // Distribute candle volume across bins
  for (const c of data) {
    const vol = c.volume && c.volume > 0 ? c.volume : 1000;
    const candleSpan = c.high - c.low || 1;

    // Proportional Buy vs Sell
    let buyRatio = 0.5;
    if (c.high > c.low) {
      if (c.close >= c.open) {
        buyRatio = 0.5 + 0.5 * ((c.close - c.open) / candleSpan);
      } else {
        buyRatio = 0.5 - 0.5 * ((c.open - c.close) / candleSpan);
      }
    }
    buyRatio = Math.max(0.1, Math.min(0.9, buyRatio));
    const buyVol = vol * buyRatio;
    const sellVol = vol * (1 - buyRatio);

    const minBinIdx = Math.max(0, Math.min(numBins - 1, Math.floor((c.low - rangeLow) / binWidth)));
    const maxBinIdx = Math.max(0, Math.min(numBins - 1, Math.floor((c.high - rangeLow) / binWidth)));
    const coveredBins = Math.max(1, maxBinIdx - minBinIdx + 1);

    const volPerBin = vol / coveredBins;
    const buyPerBin = buyVol / coveredBins;
    const sellPerBin = sellVol / coveredBins;

    for (let b = minBinIdx; b <= maxBinIdx; b++) {
      bins[b].totalVolume += volPerBin;
      bins[b].buyVolume += buyPerBin;
      bins[b].sellVolume += sellPerBin;
      bins[b].delta = bins[b].buyVolume - bins[b].sellVolume;
    }
  }

  // Find POC (Point of Control)
  let maxBinIndex = 0;
  let maxBinVolume = 0;
  for (let i = 0; i < bins.length; i++) {
    if (bins[i].totalVolume > maxBinVolume) {
      maxBinVolume = bins[i].totalVolume;
      maxBinIndex = i;
    }
  }
  bins[maxBinIndex].isPoc = true;
  const pocPrice = bins[maxBinIndex].priceMid;

  // Compute 70% Value Area (VAH / VAL)
  const targetAreaVol = totalVolume * (valueAreaPct / 100);
  let currentAreaVol = bins[maxBinIndex].totalVolume;
  bins[maxBinIndex].isInValueArea = true;

  let upperIdx = maxBinIndex;
  let lowerIdx = maxBinIndex;

  while (currentAreaVol < targetAreaVol && (upperIdx < numBins - 1 || lowerIdx > 0)) {
    const nextUpperVol = upperIdx < numBins - 1 ? bins[upperIdx + 1].totalVolume : -1;
    const nextLowerVol = lowerIdx > 0 ? bins[lowerIdx - 1].totalVolume : -1;

    if (nextUpperVol >= nextLowerVol && upperIdx < numBins - 1) {
      upperIdx++;
      currentAreaVol += bins[upperIdx].totalVolume;
      bins[upperIdx].isInValueArea = true;
    } else if (lowerIdx > 0) {
      lowerIdx--;
      currentAreaVol += bins[lowerIdx].totalVolume;
      bins[lowerIdx].isInValueArea = true;
    } else if (upperIdx < numBins - 1) {
      upperIdx++;
      currentAreaVol += bins[upperIdx].totalVolume;
      bins[upperIdx].isInValueArea = true;
    } else {
      break;
    }
  }

  const vahPrice = bins[upperIdx].priceHigh;
  const valPrice = bins[lowerIdx].priceLow;

  return {
    pocPrice,
    vahPrice,
    valPrice,
    totalVolume,
    maxBinVolume,
    bins,
    rangeHigh,
    rangeLow,
  };
}

// ============================================================================
// 3. MOMENTUM RSI DIVERGENCE ENGINE (MDE PRO)
// ============================================================================

export interface RSIDataPoint {
  time: number;
  value: number;
}

export interface RSISignalResult {
  rsiSeries: RSIDataPoint[];
  signalSeries: RSIDataPoint[];
  currentRsi: number;
  currentSignal: number;
}

export function computeRSIWithSignal(
  candles: Candle[],
  rsiPeriod: number = 14,
  signalPeriod: number = 20
): RSISignalResult {
  if (!candles || candles.length < rsiPeriod + 1) {
    return {
      rsiSeries: [],
      signalSeries: [],
      currentRsi: 50,
      currentSignal: 50,
    };
  }

  const p = Math.max(1, rsiPeriod);
  const rsiSeries: RSIDataPoint[] = [];

  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= p; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  let avgGain = gains / p;
  let avgLoss = losses / p;
  let rs = avgGain / (avgLoss === 0 ? 1 : avgLoss);
  let rsi = 100 - 100 / (1 + rs);
  rsiSeries.push({ time: candles[p].time, value: isNaN(rsi) ? 50 : rsi });

  for (let i = p + 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;

    avgGain = (avgGain * (p - 1) + gain) / p;
    avgLoss = (avgLoss * (p - 1) + loss) / p;

    rs = avgGain / (avgLoss === 0 ? 1 : avgLoss);
    rsi = 100 - 100 / (1 + rs);
    rsiSeries.push({ time: candles[i].time, value: isNaN(rsi) ? 50 : rsi });
  }

  // Calculate Signal EMA (20) of the RSI Series
  const signalSeries: RSIDataPoint[] = [];
  const sp = Math.max(1, signalPeriod);
  const mult = 2 / (sp + 1);
  let prevEma = 0;

  for (let i = 0; i < rsiSeries.length; i++) {
    const val = rsiSeries[i].value;
    if (i === 0) {
      prevEma = val;
      signalSeries.push({ time: rsiSeries[i].time, value: prevEma });
    } else {
      const ema = (val - prevEma) * mult + prevEma;
      signalSeries.push({ time: rsiSeries[i].time, value: isNaN(ema) ? val : ema });
      prevEma = ema;
    }
  }

  const currentRsi = rsiSeries.length > 0 ? rsiSeries[rsiSeries.length - 1].value : 50;
  const currentSignal = signalSeries.length > 0 ? signalSeries[signalSeries.length - 1].value : 50;

  return {
    rsiSeries,
    signalSeries,
    currentRsi,
    currentSignal,
  };
}
