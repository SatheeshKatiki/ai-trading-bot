"use client";

import { Layers, Zap, ShieldAlert, Activity } from "lucide-react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";

interface OptionChainTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function OptionChainTab({ settings, setSettings }: OptionChainTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

      {/* Box 1: Strike Selection */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
              <Layers className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Strike Selection</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Strike Type</label>
              <select
                value={settings.strike_type || "ATM (At The Money)"}
                onChange={(e) => updateSetting("strike_type", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>ATM (At The Money)</option>
                <option>ITM (In The Money)</option>
                <option>OTM (Out of The Money)</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Expiry Selection</label>
              <select
                value={settings.expiry_selection || "Current Week"}
                onChange={(e) => updateSetting("expiry_selection", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>Current Week</option>
                <option>Next Week</option>
                <option>Monthly</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Auto-Roll Expiry</span>
          <CustomSwitch
            checked={settings.auto_roll_expiry}
            onChange={(checked) => updateSetting("auto_roll_expiry", checked)}
          />
        </div>
      </div>

      {/* Box 2: IV Filters */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">IV Filters</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Min IV Percentile</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.min_iv_percentile || 30}%</span>
              </div>
              <CustomSlider
                min={0}
                max={100}
                value={settings.min_iv_percentile || 30}
                onChange={(val) => updateSetting("min_iv_percentile", val)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Max IV Percentile</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.max_iv_percentile || 80}%</span>
              </div>
              <CustomSlider
                min={0}
                max={100}
                value={settings.max_iv_percentile || 80}
                onChange={(val) => updateSetting("max_iv_percentile", val)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Block High IV Trades</span>
          <CustomSwitch
            checked={settings.block_high_iv_trades}
            onChange={(checked) => updateSetting("block_high_iv_trades", checked)}
          />
        </div>
      </div>

      {/* Box 3: Greeks Thresholds */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Greeks Thresholds</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Min Delta</label>
              <input
                type="number"
                value={settings.min_delta || 0.30}
                step="0.05"
                onChange={(e) => updateSetting("min_delta", parseFloat(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Max Theta Decay</label>
              <input
                type="number"
                value={settings.max_theta_decay || -10.00}
                step="0.5"
                onChange={(e) => updateSetting("max_theta_decay", parseFloat(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Strict Greeks Filter</span>
          <CustomSwitch
            checked={settings.strict_greeks_filter}
            onChange={(checked) => updateSetting("strict_greeks_filter", checked)}
          />
        </div>
      </div>

      {/* Box 4: Volatility & VIX (Option Buyer's Edge) */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#00f2fe]/20 rounded-xl text-[#00f2fe] shadow-lg shadow-cyan-500/10">
              <Activity className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Volatility & VIX</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Max India VIX</label>
              <input
                type="number"
                value={settings.max_india_vix || 22}
                onChange={(e) => updateSetting("max_india_vix", parseFloat(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#00f2fe]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Min India VIX</label>
              <input
                type="number"
                value={settings.min_india_vix || 12}
                onChange={(e) => updateSetting("min_india_vix", parseFloat(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#00f2fe]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">VIX Trend Filter</span>
          <CustomSwitch
            checked={settings.vix_trend_filter}
            onChange={(checked) => updateSetting("vix_trend_filter", checked)}
          />
        </div>
      </div>

    </div>
  );
}
