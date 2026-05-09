"use client";

import { ShieldCheck, Target, Clock, Zap, AlertTriangle } from "lucide-react";
import { useState } from "react";

export default function RiskManagementTab({ settings, setSettings }: { settings: any, setSettings: (s: any) => void }) {
  const [stopLossType, setStopLossType] = useState("Percentage");

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      
      {/* Box 1: Stop Loss Physics (Option Buyer's Life Insurance) */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ef4444]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-red-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#ef4444]/20 rounded-xl text-[#ef4444] shadow-lg shadow-red-500/10">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Stop Loss Physics</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Stop Loss Type</label>
              {/* Triple Switch Button - Advanced Level */}
              <div className="flex bg-[#151c2c] p-1 rounded-lg border border-[#242e42]">
                {["Points", "Amount", "Percentage"].map((type) => (
                  <button
                    key={type}
                    onClick={() => setStopLossType(type)}
                    className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${
                      stopLossType === type 
                        ? "bg-[#ef4444] text-white shadow-lg shadow-red-500/20" 
                        : "text-gray-400 hover:text-white"
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
                value={stopLossType === "Percentage" ? (settings.stoploss_pct || 1.8) : stopLossType === "Points" ? "20" : "5000"} 
                onChange={(e) => {
                  if (stopLossType === "Percentage") {
                    setSettings({...settings, stoploss_pct: parseFloat(e.target.value)});
                  }
                }}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#ef4444]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Option Premium Stop</span>
          <button className="w-12 h-6 rounded-full bg-[#ef4444] p-0.5 transition-colors shadow-lg shadow-red-500/20">
            <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
          </button>
        </div>
      </div>

      {/* Box 2: Theta Protection (Time Decay Exit) */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#f59e0b]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-amber-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
              <Clock className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Theta Protection</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Hold Time (Minutes)</label>
              <input type="number" defaultValue="30" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b]" />
              <p className="text-[10px] text-gray-500 mt-1">Option buyers lose edge if price stalls. Hard exit after time limit.</p>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Breakeven Trigger (Min)</label>
              <input type="number" defaultValue="10" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b]" />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Time-Based Exit</span>
          <button className="w-12 h-6 rounded-full bg-[#f59e0b] p-0.5 transition-colors shadow-lg shadow-amber-500/20">
            <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
          </button>
        </div>
      </div>

      {/* Box 3: Profit Booking & Trailing */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#10b981]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-emerald-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
              <Target className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Profit & Trailing</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Target 1 (Partial 50%)</label>
              <input 
                type="number" 
                value={settings.target_pct || 2.0} 
                onChange={(e) => setSettings({...settings, target_pct: parseFloat(e.target.value)})}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#10b981]" 
              />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Trailing Trigger</label>
              <select className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#10b981]">
                <option>At Target 1</option>
                <option>Immediate</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Trailing SL</span>
          <button 
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.trailing_sl ? 'bg-[#10b981] shadow-emerald-500/20' : 'bg-[#151c2c] shadow-none'}`}
            onClick={() => setSettings({...settings, trailing_sl: !settings.trailing_sl})}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.trailing_sl ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

    </div>
  );
}
