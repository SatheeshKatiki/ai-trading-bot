"use client";

import { Cpu, ShieldCheck, Zap, BarChart } from "lucide-react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";

interface AIFiltersTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function AIFiltersTab({ settings, setSettings }: AIFiltersTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Model Selection */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Model Selection</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Active ML Model</label>
              <select
                value={settings.active_ml_model || "XGBoost Classifier"}
                onChange={(e) => updateSetting("active_ml_model", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              >
                <option>XGBoost Classifier</option>
                <option>Random Forest</option>
                <option>LSTM Neural Network</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Training Data Lookback</label>
              <select
                value={settings.training_data_lookback || "Last 12 Months"}
                onChange={(e) => updateSetting("training_data_lookback", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              >
                <option>Last 12 Months</option>
                <option>Last 3 Years</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Real-Time Learning</span>
          <CustomSwitch
            checked={settings.enable_real_time_learning}
            onChange={(checked) => updateSetting("enable_real_time_learning", checked)}
          />
        </div>
      </div>

      {/* Box 2: Confidence Thresholds */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#00f2fe]/20 rounded-xl text-[#00f2fe] shadow-lg shadow-cyan-500/10">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Thresholds</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Min Confidence</span>
                <span className="text-[#00f2fe] font-extrabold text-sm">{settings.min_confidence || 75}%</span>
              </div>
              <CustomSlider
                min={50}
                max={95}
                value={settings.min_confidence || 75}
                onChange={(val) => updateSetting("min_confidence", val)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Extreme Signal Filter</span>
                <span className="text-[#00f2fe] font-extrabold text-sm">{settings.extreme_signal_filter || 90}%</span>
              </div>
              <CustomSlider
                min={80}
                max={99}
                value={settings.extreme_signal_filter || 90}
                onChange={(val) => updateSetting("extreme_signal_filter", val)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Block Low Confidence</span>
          <CustomSwitch
            checked={settings.block_low_confidence}
            onChange={(checked) => updateSetting("block_low_confidence", checked)}
          />
        </div>
      </div>

      {/* Box 3: Feature Weights */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[400px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ff9f43]/20 rounded-xl text-[#ff9f43] shadow-lg shadow-orange-500/10">
              <BarChart className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Feature Weights</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Technical Indicators</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_tech_indicators || 40}%</span>
              </div>
              <CustomSlider
                min={0}
                max={100}
                value={settings.weight_tech_indicators || 40}
                onChange={(val) => updateSetting("weight_tech_indicators", val)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Order Flow</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_order_flow || 30}%</span>
              </div>
              <CustomSlider
                min={0}
                max={100}
                value={settings.weight_order_flow || 30}
                onChange={(val) => updateSetting("weight_order_flow", val)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Sentiment Analysis</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_sentiment || 30}%</span>
              </div>
              <CustomSlider
                min={0}
                max={100}
                value={settings.weight_sentiment || 30}
                onChange={(val) => updateSetting("weight_sentiment", val)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Auto-Optimize Weights</span>
          <CustomSwitch
            checked={settings.auto_optimize_weights}
            onChange={(checked) => updateSetting("auto_optimize_weights", checked)}
          />
        </div>
      </div>

    </div>
  );
}
