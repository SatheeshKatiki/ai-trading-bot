"use client";

import { Compass, Target, ArrowRightCircle, Repeat, Clock, ShieldCheck, Minus, Plus } from "lucide-react";

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
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#4f46e5]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-indigo-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
              <Compass className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Entry Conditions</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Primary Trigger</label>
              <select 
                value={settings.primary_trigger || "Candle Breakout"}
                onChange={(e) => updateSetting("primary_trigger", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
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
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              >
                <option>Volume + Price Action</option>
                <option>Option Chain Open Interest</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Strict Entry Mode</span>
          <button 
            onClick={() => updateSetting("strict_entry_mode", !settings.strict_entry_mode)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.strict_entry_mode ? 'bg-[#4f46e5] shadow-indigo-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.strict_entry_mode ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 2: Exit Conditions */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ec4899]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-pink-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <Target className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Exit Conditions</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Primary Exit Signal</label>
              <select 
                value={settings.primary_exit_signal || "Opposite Signal"}
                onChange={(e) => updateSetting("primary_exit_signal", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
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
              <input 
                type="range" 
                min="10" 
                max="100" 
                value={settings.partial_profit_target || 50}
                onChange={(e) => updateSetting("partial_profit_target", parseInt(e.target.value))}
                className="w-full accent-[#ec4899]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Auto-Exit</span>
          <button 
            onClick={() => updateSetting("enable_auto_exit", !settings.enable_auto_exit)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.enable_auto_exit ? 'bg-[#ec4899] shadow-pink-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.enable_auto_exit ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 3: Position Sizing & Pyramiding */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#3b82f6]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-blue-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
              <ArrowRightCircle className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Position Sizing</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Sizing Method</label>
              <select 
                value={settings.sizing_method || "Fixed Percentage"}
                onChange={(e) => updateSetting("sizing_method", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#3b82f6]"
              >
                <option>Fixed Percentage</option>
                <option>Kelly Criterion</option>
                <option>Volatility Adjusted</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Pyramid Levels</label>
              <div className="flex items-center border border-[#242e42] rounded-lg bg-[#151c2c] overflow-hidden">
                <button 
                  onClick={() => updateSetting("max_pyramid_levels", Math.max(1, (settings.max_pyramid_levels || 3) - 1))}
                  className="px-4 py-2.5 hover:bg-[#1b2234] text-gray-400"
                >
                  <Minus className="w-4 h-4" />
                </button>
                <input type="text" value={settings.max_pyramid_levels || 3} className="w-full bg-transparent text-center text-sm font-extrabold text-white focus:outline-none" readOnly />
                <button 
                  onClick={() => updateSetting("max_pyramid_levels", (settings.max_pyramid_levels || 3) + 1)}
                  className="px-4 py-2.5 hover:bg-[#1b2234] text-gray-400"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Allow Pyramiding</span>
          <button 
            onClick={() => updateSetting("allow_pyramiding", !settings.allow_pyramiding)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.allow_pyramiding ? 'bg-[#3b82f6] shadow-blue-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.allow_pyramiding ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 4: Time Filters */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#06b6d4]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-cyan-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#06b6d4]/20 rounded-xl text-[#06b6d4] shadow-lg shadow-cyan-500/10">
              <Clock className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Time Filters</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Start Time</label>
                <input 
                  type="time" 
                  value={settings.start_time || "09:15"}
                  onChange={(e) => updateSetting("start_time", e.target.value)}
                  className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#06b6d4]" 
                />
              </div>
              <div>
                <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">End Time</label>
                <input 
                  type="time" 
                  value={settings.end_time || "15:15"}
                  onChange={(e) => updateSetting("end_time", e.target.value)}
                  className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#06b6d4]" 
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
                      className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-extrabold transition-colors ${isActive ? 'bg-[#ff4d4d]/20 text-[#ff4d4d]' : 'bg-[#151c2c] text-gray-400 hover:bg-[#242e42] hover:text-white'}`}
                    >
                      {day}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Intraday Square-off</span>
          <button 
            onClick={() => updateSetting("intraday_square_off", !settings.intraday_square_off)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.intraday_square_off ? 'bg-[#06b6d4] shadow-cyan-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.intraday_square_off ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

    </div>
  );
}
