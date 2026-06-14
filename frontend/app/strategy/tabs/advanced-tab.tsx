"use client";

import { Cpu, ShieldAlert, Zap, BarChart } from "lucide-react";
import CustomSwitch from "@/components/custom-switch";

interface AdvancedTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function AdvancedTab({ settings, setSettings }: AdvancedTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Webhook Integration */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Webhook Integration</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">TradingView Webhook URL</label>
              <input
                type="text"
                value={settings.tradingview_webhook_url || "https://api.quantai.com/webhook"}
                onChange={(e) => updateSetting("tradingview_webhook_url", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Secret Token</label>
              <input type="password" value="••••••••••••••••" className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]" readOnly />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Webhook Auth</span>
          <CustomSwitch
            checked={settings.enable_webhook_auth}
            onChange={(checked) => updateSetting("enable_webhook_auth", checked)}
          />
        </div>
      </div>

      {/* Box 2: System Logs */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">System Logs</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Log Level</label>
              <select
                value={settings.log_level || "Info"}
                onChange={(e) => updateSetting("log_level", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              >
                <option>Info</option>
                <option>Debug</option>
                <option>Error Only</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Log Retention (Days)</label>
              <input
                type="number"
                value={settings.log_retention_days || 7}
                onChange={(e) => updateSetting("log_retention_days", parseInt(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Auto-Clear Logs</span>
          <CustomSwitch
            checked={settings.auto_clear_logs}
            onChange={(checked) => updateSetting("auto_clear_logs", checked)}
          />
        </div>
      </div>

      {/* Box 3: Database & State */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
              <BarChart className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Database & State</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Persistence Interval</label>
              <select
                value={settings.persistence_interval || "Every 5 Seconds"}
                onChange={(e) => updateSetting("persistence_interval", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>Every 5 Seconds</option>
                <option>Every Minute</option>
                <option>On Trade Only</option>
              </select>
            </div>
            <button className="w-full py-2.5 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg text-xs font-bold text-primary transition-colors">
              Purge Database State
            </button>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Backup</span>
          <CustomSwitch
            checked={settings.enable_backup}
            onChange={(checked) => updateSetting("enable_backup", checked)}
          />
        </div>
      </div>

    </div>
  );
}
