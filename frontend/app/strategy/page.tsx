"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import { 
  Compass, 
  BarChart2, 
  LineChart, 
  Sliders, 
  Zap, 
  Layers, 
  ShieldAlert, 
  Minus, 
  Plus,
  RotateCcw,
  Upload,
  Download,
  Save,
  Eye,
  Trash2
} from "lucide-react";

// Import Tab Components
import StrategyTab from "./tabs/strategy-tab";
import IndicatorsTab from "./tabs/indicators-tab";
import AIFiltersTab from "./tabs/ai-filters-tab";
import OptionChainTab from "./tabs/option-chain-tab";
import RiskManagementTab from "./tabs/risk-management-tab";
import ExecutionTab from "./tabs/execution-tab";
import AdvancedTab from "./tabs/advanced-tab";
import NotificationsTab from "./tabs/notifications-tab";

export default function StrategySettings() {
  const [activeTab, setActiveTab] = useState("Overview");
  const [settings, setSettings] = useState<any>({});

  const tabs = [
    "Overview", "Strategy", "Indicators", "AI & Filters", 
    "Option Chain", "Risk Management", "Execution", "Advanced", "Notifications"
  ];

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => setSettings(data))
      .catch(err => console.error('Failed to fetch settings:', err));
  }, []);

  const handleSave = async () => {
    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      if (response.ok) {
        alert('Settings saved successfully!');
      } else {
        alert('Failed to save settings.');
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert('Error saving settings.');
    }
  };

  // AI Confidence value
  const confidence = 0.75; // 75%
  const strokeDasharray = 125.6; // Circumference of semi-circle (PI * R, R=40)
  const strokeDashoffset = strokeDasharray * (1 - confidence);

  return (
    <div className="flex h-screen bg-[#060814] text-white font-sans">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden bg-[#060814]">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-8 space-y-8">
          {/* Header */}
          <div className="flex justify-between items-center bg-[#0b0f19]/50 p-6 rounded-2xl border border-[#1f293d]/30 backdrop-blur-xl">
            <div>
              <h1 className="font-display font-extrabold text-4xl text-white tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-500">Strategy Settings</h1>
              <p className="text-base text-gray-400 mt-1">Configure and optimize your trading strategy parameters</p>
            </div>
            <div className="flex items-center gap-3">
              <button className="px-4 py-2.5 bg-[#151c2c] border border-[#242e42] rounded-xl text-sm font-bold text-white hover:bg-[#1b2234] hover:border-[#2e374d] flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-indigo-500/5">
                <RotateCcw className="w-4 h-4 text-gray-400" />
                Reset
              </button>
              <button className="px-4 py-2.5 bg-[#151c2c] border border-[#242e42] rounded-xl text-sm font-bold text-white hover:bg-[#1b2234] hover:border-[#2e374d] flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-indigo-500/5">
                <Upload className="w-4 h-4 text-gray-400" />
                Import
              </button>
              <button className="px-4 py-2.5 bg-[#151c2c] border border-[#242e42] rounded-xl text-sm font-bold text-white hover:bg-[#1b2234] hover:border-[#2e374d] flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-indigo-500/5">
                <Download className="w-4 h-4 text-gray-400" />
                Export
              </button>
              <button 
                onClick={handleSave}
                className="px-6 py-2.5 bg-[#4f46e5] text-white rounded-xl text-sm font-bold hover:bg-[#4338ca] flex items-center gap-2 transition-all duration-200 shadow-lg shadow-indigo-500/30 hover:scale-[1.02]"
              >
                <Save className="w-4 h-4" />
                Save Settings
              </button>
            </div>
          </div>

          {/* Tabs Matrix */}
          <div className="flex gap-2 border-b border-[#1f293d]/50">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-3 text-sm font-bold transition-all duration-200 whitespace-nowrap relative ${
                  activeTab === tab 
                    ? "text-[#4f46e5] dark:text-indigo-400" 
                    : "text-gray-500 hover:text-white"
                }`}
              >
                {tab}
                {activeTab === tab && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#4f46e5] shadow-lg shadow-indigo-500/50"></div>
                )}
              </button>
            ))}
          </div>

          {/* Main Grid Content */}
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-8">
            
            {/* Left Area: The Control Boxes (Takes 4 columns) */}
            <div className="xl:col-span-4">
              
              {/* Overview Tab Content (The 8 Boxes) */}
              {activeTab === "Overview" && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  
                  {/* === COLUMN 1 === */}
                  <div className="space-y-6">
                    {/* Strategy Mode */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#4f46e5]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-indigo-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
                            <Compass className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">Strategy Mode</h3>
                        </div>
                        
                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Select Strategy Mode</label>
                            <select 
                              value={settings.active_strategy || "ema_rsi"}
                              onChange={(e) => setSettings({...settings, active_strategy: e.target.value})}
                              className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#4f46e5] focus:border-transparent transition-all"
                            >
                              <option value="ema_rsi">EMA + RSI Momentum</option>
                              <option value="breakout">Breakout Strategy</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Timeframe</label>
                            <select 
                              value={settings.timeframe || "5 Min"}
                              onChange={(e) => setSettings({...settings, timeframe: e.target.value})}
                              className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#4f46e5] focus:border-transparent transition-all"
                            >
                              <option>1 Min</option>
                              <option>5 Min</option>
                              <option>15 Min</option>
                              <option>1 Hour</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Max Trades / Day</label>
                          <div className="flex items-center border border-[#242e42] rounded-lg bg-[#151c2c] overflow-hidden focus-within:ring-2 focus-within:ring-[#4f46e5] transition-all">
                            <button 
                              onClick={() => setSettings({...settings, max_trades_per_day: Math.max(1, (settings.max_trades_per_day || 5) - 1)})}
                              className="px-4 py-2.5 hover:bg-[#1b2234] text-gray-400 transition-colors hover:text-white"
                            >
                              <Minus className="w-4 h-4" />
                            </button>
                            <input type="text" value={settings.max_trades_per_day || 5} className="w-full bg-transparent text-center text-sm font-extrabold text-white focus:outline-none" readOnly />
                            <button 
                              onClick={() => setSettings({...settings, max_trades_per_day: (settings.max_trades_per_day || 5) + 1})}
                              className="px-4 py-2.5 hover:bg-[#1b2234] text-gray-400 transition-colors hover:text-white"
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <div>
                          <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Cooldown (min)</label>
                          <input type="number" defaultValue="15" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#4f46e5] focus:border-transparent transition-all" />
                        </div>
                      </div>
                    </div>

                    {/* Volume Settings */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ec4899]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-pink-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
                            <BarChart2 className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">Volume Settings</h3>
                        </div>
                        
                        <div className="space-y-5 mt-4">
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-gray-400">Spike Multiplier</span>
                              <span className="text-[#ec4899] font-extrabold text-sm">2.0x</span>
                            </div>
                            <input type="range" min="1" max="5" step="0.5" defaultValue="2" className="w-full accent-[#ec4899]" />
                          </div>
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-gray-400">Relative Threshold</span>
                              <span className="text-[#ec4899] font-extrabold text-sm">1.5x</span>
                            </div>
                            <input type="range" min="1" max="3" step="0.1" defaultValue="1.5" className="w-full accent-[#ec4899]" />
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Volume Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#ec4899] p-0.5 transition-colors shadow-lg shadow-pink-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* === COLUMN 2 === */}
                  <div className="space-y-6">
                    {/* EMA Settings */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#3b82f6]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-blue-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
                            <LineChart className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">EMA Settings</h3>
                        </div>
                        
                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">EMA Fast</label>
                            <input 
                              type="number" 
                              value={settings.ema_fast || 9} 
                              onChange={(e) => setSettings({...settings, ema_fast: parseInt(e.target.value)})}
                              className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent transition-all" 
                            />
                          </div>
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">EMA Slow</label>
                            <input 
                              type="number" 
                              value={settings.ema_slow || 21} 
                              onChange={(e) => setSettings({...settings, ema_slow: parseInt(e.target.value)})}
                              className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:border-transparent transition-all" 
                            />
                          </div>
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-gray-400">Crossover Sensitivity</span>
                              <span className="text-[#3b82f6] font-extrabold text-sm">65%</span>
                            </div>
                            <input type="range" min="10" max="100" defaultValue="65" className="w-full accent-[#3b82f6]" />
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable EMA Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#3b82f6] p-0.5 transition-colors shadow-lg shadow-blue-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>

                    {/* VWAP Settings */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#06b6d4]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-cyan-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#06b6d4]/20 rounded-xl text-[#06b6d4] shadow-lg shadow-cyan-500/10">
                            <Sliders className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">VWAP Settings</h3>
                        </div>
                        
                        <div className="space-y-5 mt-4">
                          <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-white uppercase tracking-wider">Enable VWAP Filter</span>
                            <button className="w-12 h-6 rounded-full bg-[#06b6d4] p-0.5 transition-colors shadow-lg shadow-cyan-500/20">
                              <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                            </button>
                          </div>
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">VWAP Confirmation</label>
                            <select className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#06b6d4] focus:border-transparent transition-all">
                              <option>Price Above VWAP</option>
                            </select>
                          </div>
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-gray-400">Strength</span>
                              <span className="text-[#06b6d4] font-extrabold text-sm">70%</span>
                            </div>
                            <input type="range" min="10" max="100" defaultValue="70" className="w-full accent-[#06b6d4]" />
                          </div>
                        </div>
                      </div>
                      <div></div>
                    </div>
                  </div>

                  {/* === COLUMN 3 === */}
                  <div className="space-y-6">
                    {/* RSI Settings */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#10b981]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-emerald-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
                            <Zap className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">RSI Settings</h3>
                        </div>
                        
                        <div className="space-y-5 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">RSI Period</label>
                            <input 
                              type="number" 
                              value={settings.rsi_window || 14} 
                              onChange={(e) => setSettings({...settings, rsi_window: parseInt(e.target.value)})}
                              className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#10b981] focus:border-transparent transition-all" 
                            />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Overbought</label>
                              <input 
                                type="number" 
                                value={settings.rsi_sell || 70} 
                                onChange={(e) => setSettings({...settings, rsi_sell: parseInt(e.target.value)})}
                                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#10b981] focus:border-transparent transition-all" 
                              />
                            </div>
                            <div>
                              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Oversold</label>
                              <input 
                                type="number" 
                                value={settings.rsi_buy || 30} 
                                onChange={(e) => setSettings({...settings, rsi_buy: parseInt(e.target.value)})}
                                className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#10b981] focus:border-transparent transition-all" 
                              />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable RSI Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#10b981] p-0.5 transition-colors shadow-lg shadow-emerald-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>

                    {/* Option Chain Filters */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#f59e0b]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-amber-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
                            <Layers className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">Option Chain</h3>
                        </div>
                        
                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Min OI</label>
                            <input type="number" defaultValue="1000" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b] focus:border-transparent transition-all" />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">PCR Upper</label>
                              <input type="number" defaultValue="1.20" step="0.05" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b] focus:border-transparent transition-all" />
                            </div>
                            <div>
                              <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">PCR Lower</label>
                              <input type="number" defaultValue="0.80" step="0.05" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#f59e0b] focus:border-transparent transition-all" />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Option Chain Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#f59e0b] p-0.5 transition-colors shadow-lg shadow-amber-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* === COLUMN 4 === */}
                  <div className="space-y-6">
                    {/* MACD Settings */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#ff9f43]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-orange-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#ff9f43]/20 rounded-xl text-[#ff9f43] shadow-lg shadow-orange-500/10">
                            <Sliders className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">MACD Settings</h3>
                        </div>
                        
                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Fast Length</label>
                            <select className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#ff9f43] focus:border-transparent transition-all">
                              <option>12</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Slow Length</label>
                            <select className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#ff9f43] focus:border-transparent transition-all">
                              <option>26</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable MACD Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#ff9f43] p-0.5 transition-colors shadow-lg shadow-orange-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>

                    {/* Greeks Filters */}
                    <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#8c52ff]/20 space-y-5 h-[420px] flex flex-col justify-between shadow-xl hover:shadow-purple-500/5 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-[#1f293d]/50 pb-3">
                          <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
                            <ShieldAlert className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-white">Greeks Filters</h3>
                        </div>
                        
                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-gray-400 block mb-1.5 uppercase tracking-wider">Delta Range</label>
                            <div className="flex items-center gap-3">
                              <input type="number" defaultValue="0.40" step="0.05" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff] focus:border-transparent transition-all" />
                              <span className="text-gray-500 text-xs">to</span>
                              <input type="number" defaultValue="0.70" step="0.05" className="w-full bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2.5 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#8c52ff] focus:border-transparent transition-all" />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-[#1f293d]/50">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Enable Greeks Filter</span>
                        <button className="w-12 h-6 rounded-full bg-[#8c52ff] p-0.5 transition-colors shadow-lg shadow-purple-500/20">
                          <div className="w-5 h-5 rounded-full bg-white translate-x-6 transition-transform"></div>
                        </button>
                      </div>
                    </div>
                  </div>

                </div>
              )}

              {/* Strategy Tab */}
              {activeTab === "Strategy" && <StrategyTab settings={settings} setSettings={setSettings} />}

              {/* Indicators Tab */}
              {activeTab === "Indicators" && <IndicatorsTab settings={settings} setSettings={setSettings} />}

              {/* AI & Filters Tab */}
              {activeTab === "AI & Filters" && <AIFiltersTab settings={settings} setSettings={setSettings} />}

              {/* Option Chain Tab */}
              {activeTab === "Option Chain" && <OptionChainTab settings={settings} setSettings={setSettings} />}

              {/* Risk Management Tab */}
              {activeTab === "Risk Management" && <RiskManagementTab settings={settings} setSettings={setSettings} />}

              {/* Execution Tab */}
              {activeTab === "Execution" && <ExecutionTab settings={settings} setSettings={setSettings} />}

              {/* Advanced Tab */}
              {activeTab === "Advanced" && <AdvancedTab settings={settings} setSettings={setSettings} />}

              {/* Notifications Tab */}
              {activeTab === "Notifications" && <NotificationsTab settings={settings} setSettings={setSettings} />}

            </div>

            {/* Right Area: The Sidebar Cards (Takes 1 column) */}
            <div className="space-y-6">
              {/* Strategy Summary */}
              <div className="bg-gradient-to-br from-[#8c52ff] to-[#4f46e5] text-white p-6 rounded-2xl shadow-xl space-y-4 border border-white/5 hover:scale-[1.02] transition-transform">
                <div className="flex items-center gap-2 border-b border-white/10 pb-2">
                  <span>👑</span>
                  <h3 className="font-display font-extrabold text-sm uppercase tracking-wider">Strategy Summary</h3>
                </div>
                <div className="space-y-3 text-xs">
                  <div className="flex justify-between">
                    <span className="text-white/70">Strategy Mode</span>
                    <span className="font-extrabold">Momentum</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">Trade Style</span>
                    <span className="font-extrabold">Intraday</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">AI Confidence</span>
                    <span className="font-extrabold text-emerald-300">≥ 75%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">Risk per Trade</span>
                    <span className="font-extrabold">1.00%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">Daily Max Loss</span>
                    <span className="font-extrabold">3.00%</span>
                  </div>
                  <div className="flex justify-between items-center pt-2 border-t border-white/10">
                    <span className="text-white/70">Status</span>
                    <span className="px-3 py-1 bg-emerald-400 text-[#0f172a] font-extrabold rounded-lg text-[10px]">ACTIVE</span>
                  </div>
                </div>
              </div>

              {/* AI Confidence Preview */}
              <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#1f293d]/50 space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-white uppercase tracking-wider">AI Confidence</h3>
                <div className="relative w-full flex flex-col items-center justify-center">
                  
                  {/* Perfect SVG Gauge */}
                  <svg viewBox="0 0 100 55" className="w-40 h-24">
                    <defs>
                      <linearGradient id="confidence-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#8c52ff" />
                        <stop offset="50%" stopColor="#00f2fe" />
                        <stop offset="100%" stopColor="#10b981" />
                      </linearGradient>
                    </defs>
                    {/* Background Track */}
                    <path 
                      d="M 10 50 A 40 40 0 0 1 90 50" 
                      fill="none" 
                      stroke="#1f293d" 
                      strokeWidth="8" 
                      strokeLinecap="round"
                    />
                    {/* Active Gradient Track */}
                    <path 
                      d="M 10 50 A 40 40 0 0 1 90 50" 
                      fill="none" 
                      stroke="url(#confidence-grad)" 
                      strokeWidth="8" 
                      strokeLinecap="round"
                      strokeDasharray="125.6"
                      strokeDashoffset={strokeDashoffset}
                      className="transition-all duration-1000 ease-in-out"
                    />
                  </svg>

                  {/* Absolute Centered Text */}
                  <div className="text-center absolute bottom-2">
                    <span className="font-display font-extrabold text-3xl text-white">75%</span>
                    <p className="text-xs text-emerald-400 font-extrabold tracking-wide">EXCELLENT</p>
                  </div>
                  
                  <div className="flex justify-between w-40 text-[10px] text-gray-500 mt-1">
                    <span>0%</span>
                    <span>100%</span>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#1f293d]/50 space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-white uppercase tracking-wider">Quick Actions</h3>
                <div className="space-y-2">
                  <button className="w-full text-left px-4 py-3 bg-[#151c2c] hover:bg-[#1b2234] rounded-xl text-xs font-bold text-white flex items-center gap-3 transition-colors border border-transparent hover:border-[#242e42] hover:scale-[1.02] transform">
                    <Zap className="w-4 h-4 text-amber-500" />
                    Run Backtest
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-[#151c2c] hover:bg-[#1b2234] rounded-xl text-xs font-bold text-white flex items-center gap-3 transition-colors border border-transparent hover:border-[#242e42] hover:scale-[1.02] transform">
                    <BarChart2 className="w-4 h-4 text-[#3b82f6]" />
                    View Performance
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-[#151c2c] hover:bg-[#1b2234] rounded-xl text-xs font-bold text-white flex items-center gap-3 transition-colors border border-transparent hover:border-[#242e42] hover:scale-[1.02] transform">
                    <Upload className="w-4 h-4 text-emerald-500" />
                    Load Preset
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-[#151c2c] hover:bg-[#1b2234] rounded-xl text-xs font-bold text-white flex items-center gap-3 transition-colors border border-transparent hover:border-[#242e42] hover:scale-[1.02] transform">
                    <Save className="w-4 h-4 text-[#8c52ff]" />
                    Save as Preset
                  </button>
                </div>
              </div>

              {/* Preset Manager */}
              <div className="bg-[#0b0f19] p-6 rounded-2xl border border-[#1f293d]/50 space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-white uppercase tracking-wider">Preset Manager</h3>
                <div className="flex gap-2">
                  <select className="flex-1 bg-[#151c2c] border border-[#242e42] rounded-lg px-3 py-2 text-xs font-bold text-white focus:outline-none focus:ring-1 focus:ring-[#4f46e5] focus:border-transparent">
                    <option>My Momentum Setup</option>
                    <option>Conservative Grid</option>
                  </select>
                  <button className="p-2.5 bg-[#151c2c] hover:bg-[#1b2234] border border-[#242e42] rounded-lg text-gray-400 hover:text-white transition-colors">
                    <Eye className="w-4 h-4" />
                  </button>
                  <button className="p-2.5 bg-[#151c2c] hover:bg-[#1b2234] border border-[#242e42] rounded-lg text-red-500 hover:text-red-400 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

          </div>
        </main>
      </div>
    </div>
  );
}
