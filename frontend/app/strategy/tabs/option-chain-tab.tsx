"use client";

import { Layers, Zap, ShieldAlert, Activity } from "lucide-react";

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
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#f59e0b]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-amber-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
              <Layers className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Strike Selection</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Strike Type</label>
              <select 
                value={settings.strike_type || "ATM (At The Money)"}
                onChange={(e) => updateSetting("strike_type", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>ATM (At The Money)</option>
                <option>ITM (In The Money)</option>
                <option>OTM (Out of The Money)</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Expiry Selection</label>
              <select 
                value={settings.expiry_selection || "Current Week"}
                onChange={(e) => updateSetting("expiry_selection", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b]"
              >
                <option>Current Week</option>
                <option>Next Week</option>
                <option>Monthly</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Auto-Roll Expiry</span>
          <button 
            onClick={() => updateSetting("auto_roll_expiry", !settings.auto_roll_expiry)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.auto_roll_expiry ? 'bg-[#f59e0b] shadow-amber-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.auto_roll_expiry ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 2: IV Filters */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ec4899]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-pink-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">IV Filters</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Min IV Percentile</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.min_iv_percentile || 30}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={settings.min_iv_percentile || 30}
                onChange={(e) => updateSetting("min_iv_percentile", parseInt(e.target.value))}
                className="w-full accent-[#ec4899]" 
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Max IV Percentile</span>
                <span className="text-[#ec4899] font-extrabold text-sm">{settings.max_iv_percentile || 80}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={settings.max_iv_percentile || 80}
                onChange={(e) => updateSetting("max_iv_percentile", parseInt(e.target.value))}
                className="w-full accent-[#ec4899]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Block High IV Trades</span>
          <button 
            onClick={() => updateSetting("block_high_iv_trades", !settings.block_high_iv_trades)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.block_high_iv_trades ? 'bg-[#ec4899] shadow-pink-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.block_high_iv_trades ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 3: Greeks Thresholds */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#8c52ff]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-purple-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Greeks Thresholds</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Min Delta</label>
              <input 
                type="number" 
                value={settings.min_delta || 0.30} 
                step="0.05"
                onChange={(e) => updateSetting("min_delta", parseFloat(e.target.value))}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff]" 
              />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Theta Decay</label>
              <input 
                type="number" 
                value={settings.max_theta_decay || -10.00} 
                step="0.5"
                onChange={(e) => updateSetting("max_theta_decay", parseFloat(e.target.value))}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Strict Greeks Filter</span>
          <button 
            onClick={() => updateSetting("strict_greeks_filter", !settings.strict_greeks_filter)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.strict_greeks_filter ? 'bg-[#8c52ff] shadow-purple-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.strict_greeks_filter ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 4: Volatility & VIX (Option Buyer's Edge) */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#00f2fe]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-cyan-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#00f2fe]/20 rounded-xl text-[#00f2fe] shadow-lg shadow-cyan-500/10">
              <Activity className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Volatility & VIX</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max India VIX</label>
              <input 
                type="number" 
                value={settings.max_india_vix || 22}
                onChange={(e) => updateSetting("max_india_vix", parseFloat(e.target.value))}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#00f2fe]" 
              />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Min India VIX</label>
              <input 
                type="number" 
                value={settings.min_india_vix || 12}
                onChange={(e) => updateSetting("min_india_vix", parseFloat(e.target.value))}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#00f2fe]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">VIX Trend Filter</span>
          <button 
            onClick={() => updateSetting("vix_trend_filter", !settings.vix_trend_filter)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.vix_trend_filter ? 'bg-[#00f2fe] shadow-cyan-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.vix_trend_filter ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

    </div>
  );
}
