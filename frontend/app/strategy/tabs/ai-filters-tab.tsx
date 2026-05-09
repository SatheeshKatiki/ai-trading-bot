"use client";

import { Cpu, ShieldCheck, Zap, BarChart } from "lucide-react";

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
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#8c52ff]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-purple-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Model Selection</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Active ML Model</label>
              <select 
                value={settings.active_ml_model || "XGBoost Classifier"}
                onChange={(e) => updateSetting("active_ml_model", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              >
                <option>XGBoost Classifier</option>
                <option>Random Forest</option>
                <option>LSTM Neural Network</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Training Data Lookback</label>
              <select 
                value={settings.training_data_lookback || "Last 12 Months"}
                onChange={(e) => updateSetting("training_data_lookback", e.target.value)}
                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff]"
              >
                <option>Last 12 Months</option>
                <option>Last 3 Years</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Real-Time Learning</span>
          <button 
            onClick={() => updateSetting("enable_real_time_learning", !settings.enable_real_time_learning)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.enable_real_time_learning ? 'bg-[#8c52ff] shadow-purple-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.enable_real_time_learning ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 2: Confidence Thresholds */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#00f2fe]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-cyan-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#00f2fe]/20 rounded-xl text-[#00f2fe] shadow-lg shadow-cyan-500/10">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Thresholds</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Min Confidence</span>
                <span className="text-[#00f2fe] font-extrabold text-sm">{settings.min_confidence || 75}%</span>
              </div>
              <input 
                type="range" 
                min="50" 
                max="95" 
                value={settings.min_confidence || 75}
                onChange={(e) => updateSetting("min_confidence", parseInt(e.target.value))}
                className="w-full accent-[#00f2fe]" 
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Extreme Signal Filter</span>
                <span className="text-[#00f2fe] font-extrabold text-sm">{settings.extreme_signal_filter || 90}%</span>
              </div>
              <input 
                type="range" 
                min="80" 
                max="99" 
                value={settings.extreme_signal_filter || 90}
                onChange={(e) => updateSetting("extreme_signal_filter", parseInt(e.target.value))}
                className="w-full accent-[#00f2fe]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Block Low Confidence</span>
          <button 
            onClick={() => updateSetting("block_low_confidence", !settings.block_low_confidence)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.block_low_confidence ? 'bg-[#00f2fe] shadow-cyan-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.block_low_confidence ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

      {/* Box 3: Feature Weights */}
      <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ff9f43]/20 space-y-5 h-[400px] flex flex-col justify-between shadow-xl hover:shadow-orange-500/5 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
            <div className="p-2.5 bg-[#ff9f43]/20 rounded-xl text-[#ff9f43] shadow-lg shadow-orange-500/10">
              <BarChart className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-white">Feature Weights</h3>
          </div>
          
          <div className="space-y-4 mt-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Technical Indicators</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_tech_indicators || 40}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={settings.weight_tech_indicators || 40}
                onChange={(e) => updateSetting("weight_tech_indicators", parseInt(e.target.value))}
                className="w-full accent-[#ff9f43]" 
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Order Flow</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_order_flow || 30}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={settings.weight_order_flow || 30}
                onChange={(e) => updateSetting("weight_order_flow", parseInt(e.target.value))}
                className="w-full accent-[#ff9f43]" 
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                <span className="text-gray-400">Sentiment Analysis</span>
                <span className="text-[#ff9f43] font-extrabold text-sm">{settings.weight_sentiment || 30}%</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                value={settings.weight_sentiment || 30}
                onChange={(e) => updateSetting("weight_sentiment", parseInt(e.target.value))}
                className="w-full accent-[#ff9f43]" 
              />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Auto-Optimize Weights</span>
          <button 
            onClick={() => updateSetting("auto_optimize_weights", !settings.auto_optimize_weights)}
            className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.auto_optimize_weights ? 'bg-[#ff9f43] shadow-orange-500/20' : 'bg-[#151c2c] border border-[#242e42]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.auto_optimize_weights ? 'translate-x-6' : 'translate-x-0'}`}></div>
          </button>
        </div>
      </div>

    </div>
  );
}
