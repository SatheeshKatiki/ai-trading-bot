"use client";

import { ShieldCheck, Target, Clock, Zap, AlertTriangle } from "lucide-react";
import CustomSwitch from "@/components/custom-switch";
import { useState } from "react";

export default function RiskManagementTab({ settings, setSettings }: { settings: any, setSettings: (s: any) => void }) {
  const stopLossType = settings.stop_loss_type || "Percentage";

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Stop Loss Physics (Option Buyer's Life Insurance) */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[#ef4444]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-red-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#ef4444]/20 rounded-xl text-[#ef4444] shadow-lg shadow-red-500/10">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Stop Loss Physics</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Stop Loss Type</label>
              {/* Triple Switch Button - Advanced Level */}
              <div className="flex bg-background p-1 rounded-lg border border-border">
                {["Points", "Amount", "Percentage"].map((type) => (
                  <button
                    key={type}
                    onClick={() => setSettings({ ...settings, stop_loss_type: type })}
                    className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${stopLossType === type
                        ? "bg-[#ef4444] text-white shadow-lg shadow-red-500/20"
                        : "text-gray-400 hover:text-foreground"
                      }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">
                Value ({stopLossType === "Points" ? "Pts" : stopLossType === "Amount" ? "₹" : "%"})
              </label>
              <input
                type="number"
                value={
                  stopLossType === "Percentage"
                    ? (settings.stoploss_pct || 1.8)
                    : stopLossType === "Points"
                      ? (settings.stop_loss_points || 20)
                      : (settings.stop_loss_amount || 5000)
                }
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  if (stopLossType === "Percentage") {
                    setSettings({ ...settings, stoploss_pct: val });
                  } else if (stopLossType === "Points") {
                    setSettings({ ...settings, stop_loss_points: val });
                  } else if (stopLossType === "Amount") {
                    setSettings({ ...settings, stop_loss_amount: val });
                  }
                }}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ef4444]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Option Premium Stop</span>
          <CustomSwitch
            checked={settings.option_premium_stop}
            onChange={(checked) => setSettings({ ...settings, option_premium_stop: checked })}
          />
        </div>
      </div>

      {/* Box 2: Theta Protection (Time Decay Exit) */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[#f59e0b]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-amber-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
              <Clock className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Theta Protection</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Hold Time (Minutes)</label>
              <input
                type="number"
                value={settings.max_hold_time || 30}
                onChange={(e) => setSettings({ ...settings, max_hold_time: parseInt(e.target.value) })}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              />
              <p className="text-[10px] text-gray-500 mt-1">Option buyers lose edge if price stalls. Hard exit after time limit.</p>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Breakeven Trigger (Min)</label>
              <input
                type="number"
                value={settings.breakeven_trigger || 10}
                onChange={(e) => setSettings({ ...settings, breakeven_trigger: parseInt(e.target.value) })}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Time-Based Exit</span>
          <CustomSwitch
            checked={settings.time_based_exit}
            onChange={(checked) => setSettings({ ...settings, time_based_exit: checked })}
          />
        </div>
      </div>

      {/* Box 3: Profit Booking & Trailing */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[#10b981]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-emerald-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
              <Target className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Profit & Trailing</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Target 1 (Partial 50%)</label>
              <input
                type="number"
                value={settings.target_pct || 2.0}
                onChange={(e) => setSettings({ ...settings, target_pct: parseFloat(e.target.value) })}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#10b981]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Trailing Trigger</label>
              <select
                value={settings.trailing_trigger || "At Target 1"}
                onChange={(e) => setSettings({ ...settings, trailing_trigger: e.target.value })}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#10b981]"
              >
                <option>At Target 1</option>
                <option>Immediate</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Trailing SL</span>
          <CustomSwitch
            checked={settings.trailing_sl}
            onChange={(checked) => setSettings({ ...settings, trailing_sl: checked })}
          />
        </div>
      </div>

    </div>
  );
}
