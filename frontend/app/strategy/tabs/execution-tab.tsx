"use client";

import { Zap, ShieldAlert, Cpu, BarChart } from "lucide-react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";

interface ExecutionTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function ExecutionTab({ settings, setSettings }: ExecutionTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Order Routing */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Order Routing</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Default Broker</label>
              <select
                value={settings.default_broker || "Fyers API v3"}
                onChange={(e) => updateSetting("default_broker", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              >
                <option>Fyers API v3</option>
                <option>Zerodha Kite</option>
                <option>Angel One</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Product Type</label>
              <select
                value={settings.product_type || "MIS (Intraday)"}
                onChange={(e) => updateSetting("product_type", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              >
                <option>MIS (Intraday)</option>
                <option>NRML (Carry Forward)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Smart Routing</span>
          <CustomSwitch
            checked={settings.enable_smart_routing}
            onChange={(checked) => updateSetting("enable_smart_routing", checked)}
          />
        </div>
      </div>

      {/* Box 2: Slippage & Costs */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Slippage & Costs</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-muted-foreground">Slippage Tolerance</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.slippage_tolerance || 0.5}%</span>
              </div>
              <CustomSlider
                min={0.1}
                max={2}
                step={0.1}
                value={settings.slippage_tolerance || 0.5}
                onChange={(val) => updateSetting("slippage_tolerance", val)}
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Max Bid-Ask Spread</label>
              <input
                type="number"
                value={settings.max_bid_ask_spread || 2.0}
                step="0.5"
                onChange={(e) => updateSetting("max_bid_ask_spread", parseFloat(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Block on High Spread</span>
          <CustomSwitch
            checked={settings.block_on_high_spread}
            onChange={(checked) => updateSetting("block_on_high_spread", checked)}
          />
        </div>
      </div>

      {/* Box 3: Speed & Execution */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Speed & Execution</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Order Type</label>
              <select
                value={settings.order_type || "Market Order"}
                onChange={(e) => updateSetting("order_type", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>Market Order</option>
                <option>Limit Order</option>
                <option>SL-Limit Order</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Execution Delay (ms)</label>
              <input
                type="number"
                value={settings.execution_delay_ms || 0}
                onChange={(e) => updateSetting("execution_delay_ms", parseInt(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Retry on Failure</span>
          <CustomSwitch
            checked={settings.retry_on_failure}
            onChange={(checked) => updateSetting("retry_on_failure", checked)}
          />
        </div>
      </div>

    </div>
  );
}
