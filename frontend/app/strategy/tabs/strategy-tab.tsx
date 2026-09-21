"use client";

import { Compass, Target, ArrowRightCircle, Repeat, Clock, ShieldCheck, Minus, Plus } from "lucide-react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";

interface StrategyTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function StrategyTab({ settings, setSettings }: StrategyTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Entry Conditions */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
              <Compass className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Entry Conditions</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Primary Trigger</label>
              <select
                value={settings.primary_trigger || "Candle Breakout"}
                onChange={(e) => updateSetting("primary_trigger", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              >
                <option>Candle Breakout</option>
                <option>EMA Crossover</option>
                <option>RSI Extreme</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Confirmation Source</label>
              <select
                value={settings.confirmation_source || "Volume + Price Action"}
                onChange={(e) => updateSetting("confirmation_source", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              >
                <option>Volume + Price Action</option>
                <option>Option Chain Open Interest</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Strict Entry Mode</span>
          <CustomSwitch
            checked={settings.strict_entry_mode || false}
            onChange={(checked) => updateSetting("strict_entry_mode", checked)}
          />
        </div>

        {/* Anticipate the EMA crossover instead of waiting for it. Measured
            over 675 sessions with costs from real option premiums, so the
            number is on the switch rather than buried in a doc: it was the
            most damaging change tried on this strategy. */}
        <div className="pt-3 border-t border-border">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground uppercase tracking-wider">
                Anticipate Crossover
              </span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30">
                MEASURED WORSE
              </span>
            </div>
            <CustomSwitch
              checked={(settings.ema9_rsi_anticipate_cross_bars ?? 0) > 0}
              onChange={(checked) =>
                updateSetting("ema9_rsi_anticipate_cross_bars", checked ? 1 : 0)
              }
            />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
            Enter when EMA9 is about to cross EMA20, without waiting for the cross.
            Backtested 2024-01 to 2026-09: NIFTY <span className="text-emerald-400 font-semibold">+₹11,150</span> →{" "}
            <span className="text-rose-400 font-semibold">−₹64,551</span>, SENSEX −₹37,841 → −₹56,247.
            EMA9 approaches EMA20 far more often than it crosses, so this roughly doubles
            trades and most of the extra ones are approaches that failed.
          </p>
          {(settings.ema9_rsi_anticipate_cross_bars ?? 0) > 0 && (
            <div className="mt-3">
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">
                Look ahead
              </label>
              <select
                value={settings.ema9_rsi_anticipate_cross_bars ?? 1}
                onChange={(e) =>
                  updateSetting("ema9_rsi_anticipate_cross_bars", Number(e.target.value))
                }
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-rose-500"
              >
                <option value={1}>1 candle ahead</option>
                <option value={2}>2 candles ahead</option>
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Box 2: Exit Conditions */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Target className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Exit Conditions</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Primary Exit Signal</label>
              <select
                value={settings.primary_exit_signal || "Opposite Signal"}
                onChange={(e) => updateSetting("primary_exit_signal", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              >
                <option>Opposite Signal</option>
                <option>Trailing Stop Hit</option>
                <option>Time-based Exit</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Partial Profit Target</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.partial_profit_target || 50}%</span>
              </div>
              <CustomSlider
                min={10}
                max={100}
                value={settings.partial_profit_target || 50}
                onChange={(val) => updateSetting("partial_profit_target", val)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Auto-Exit</span>
          <CustomSwitch
            checked={settings.enable_auto_exit || false}
            onChange={(checked) => updateSetting("enable_auto_exit", checked)}
          />
        </div>

        {/* Carrying a position past 15:25. Off by default: it changes the risk
            class rather than the return, so the reason sits next to the switch. */}
        <div className="pt-3 border-t border-border">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground uppercase tracking-wider">
                Overnight Carry
              </span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                GAP RISK
              </span>
            </div>
            <CustomSwitch
              checked={settings.ema9_rsi_allow_overnight_carry || false}
              onChange={(checked) =>
                updateSetting("ema9_rsi_allow_overnight_carry", checked)
              }
            />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
            Off: everything is squared off at 15:25. On: a position up{" "}
            <span className="font-semibold text-foreground">
              +{settings.ema9_rsi_overnight_min_gain_pct ?? 40}%
            </span>{" "}
            with VERY_STRONG momentum and the signal intact is held to the next session.
            An intraday buyer&apos;s edge is that no gap can happen while the position is
            open — held overnight, one gap can exceed every stop the ladder would apply,
            and no stop order protects against a gap.{" "}
            <span className="text-emerald-400 font-semibold">Never on expiry day</span> —
            the contract expires, so there is nothing to carry.
          </p>
          {settings.ema9_rsi_allow_overnight_carry && (
            <div className="mt-3 space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Minimum gain to carry</span>
                <span className="text-amber-400 font-extrabold text-sm">
                  +{settings.ema9_rsi_overnight_min_gain_pct ?? 40}%
                </span>
              </div>
              <CustomSlider
                min={20}
                max={200}
                value={settings.ema9_rsi_overnight_min_gain_pct ?? 40}
                onChange={(val) => updateSetting("ema9_rsi_overnight_min_gain_pct", val)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Box 3: Position Sizing & Pyramiding */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
              <ArrowRightCircle className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Position Sizing</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Sizing Method</label>
              <select
                value={settings.sizing_method || "Fixed Percentage"}
                onChange={(e) => updateSetting("sizing_method", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>Fixed Percentage</option>
                <option>Kelly Criterion</option>
                <option>Volatility Adjusted</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Pyramid Levels</label>
              <div className="flex items-center border border-border rounded-lg bg-background overflow-hidden">
                <button
                  onClick={() => updateSetting("max_pyramid_levels", Math.max(1, (settings.max_pyramid_levels || 3) - 1))}
                  className="px-4 py-2.5 hover:bg-muted text-gray-400"
                >
                  <Minus className="w-4 h-4" />
                </button>
                <input type="text" value={settings.max_pyramid_levels || 3} className="w-full bg-transparent text-center text-sm font-extrabold text-foreground focus:outline-none" readOnly />
                <button
                  onClick={() => updateSetting("max_pyramid_levels", (settings.max_pyramid_levels || 3) + 1)}
                  className="px-4 py-2.5 hover:bg-muted text-gray-400"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Allow Pyramiding</span>
          <CustomSwitch
            checked={settings.allow_pyramiding || false}
            onChange={(checked) => updateSetting("allow_pyramiding", checked)}
          />
        </div>
      </div>

      {/* Box 4: Time Filters */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#06b6d4]/20 rounded-xl text-[#06b6d4] shadow-lg shadow-cyan-500/10">
              <Clock className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Time Filters</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Start Time</label>
                <input
                  type="time"
                  value={settings.start_time || "09:15"}
                  onChange={(e) => updateSetting("start_time", e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#06b6d4]"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">End Time</label>
                <input
                  type="time"
                  value={settings.end_time || "15:15"}
                  onChange={(e) => updateSetting("end_time", e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#06b6d4]"
                />
              </div>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">No Trade Days</label>
              <div className="flex gap-2">
                {["S", "M", "T", "W", "T", "F", "S"].map((day, i) => {
                  const noTradeDays = settings.no_trade_days || [0, 6]; // Default Sun, Sat
                  const isActive = noTradeDays.includes(i);
                  return (
                    <button
                      key={i}
                      onClick={() => {
                        const newDays = isActive
                          ? noTradeDays.filter((d: number) => d !== i)
                          : [...noTradeDays, i];
                        updateSetting("no_trade_days", newDays);
                      }}
                      className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-extrabold transition-colors ${isActive ? 'bg-[#ff4d4d]/20 text-[#ff4d4d]' : 'bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground'}`}
                    >
                      {day}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Intraday Square-off</span>
          <CustomSwitch
            checked={settings.intraday_square_off || false}
            onChange={(checked) => updateSetting("intraday_square_off", checked)}
          />
        </div>
      </div>

    </div>
  );
}
