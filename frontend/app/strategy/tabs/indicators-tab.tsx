"use client";

import { LineChart, BarChart, Activity, Cpu, Layers } from "lucide-react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";

interface IndicatorsTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function IndicatorsTab({ settings, setSettings }: IndicatorsTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Multi-Timeframe Indicators */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
              <Layers className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Multi-Timeframe</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Anchor Timeframe</label>
              <select
                value={settings.anchor_timeframe || "1 Hour"}
                onChange={(e) => updateSetting("anchor_timeframe", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>1 Hour</option>
                <option>4 Hours</option>
                <option>Daily</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Trend Indicator</label>
              <select
                value={settings.trend_indicator || "Supertrend (10, 3)"}
                onChange={(e) => updateSetting("trend_indicator", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>Supertrend (10, 3)</option>
                <option>Ichimoku Cloud</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable MTF Alignment</span>
          <CustomSwitch
            checked={settings.enable_mtf_alignment}
            onChange={(checked) => updateSetting("enable_mtf_alignment", checked)}
          />
        </div>
      </div>

      {/* Box 2: Custom Script Indicators */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Custom Scripts</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Loaded Script</label>
              <select
                value={settings.loaded_script || "VWAP Stochastics Cross"}
                onChange={(e) => updateSetting("loaded_script", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#10b981]"
              >
                <option>VWAP Stochastics Cross</option>
                <option>Custom Pine Script V5</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Script Weight</span>
                <span className="text-[#10b981] font-extrabold text-sm">{settings.script_weight || 80}%</span>
              </div>
              <CustomSlider
                min={10}
                max={100}
                value={settings.script_weight || 80}
                onChange={(val) => updateSetting("script_weight", val)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Run Script Realtime</span>
          <CustomSwitch
            checked={settings.run_script_realtime}
            onChange={(checked) => updateSetting("run_script_realtime", checked)}
          />
        </div>
      </div>

      {/* Box 3: Signal Combinations */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
              <Activity className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Signal Combinations</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Logic Gate</label>
              <select
                value={settings.logic_gate || "ALL Conditions Met (AND)"}
                onChange={(e) => updateSetting("logic_gate", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>ALL Conditions Met (AND)</option>
                <option>ANY Condition Met (OR)</option>
                <option>Weighted Scoring</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Min Indicators Required</label>
              <select
                value={settings.min_indicators_required || "3 Indicators"}
                onChange={(e) => updateSetting("min_indicators_required", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>3 Indicators</option>
                <option>2 Indicators</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Strict Alignment</span>
          <CustomSwitch
            checked={settings.strict_alignment}
            onChange={(checked) => updateSetting("strict_alignment", checked)}
          />
        </div>
      </div>

    </div>
  );
}
