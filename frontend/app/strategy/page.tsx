"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { NumberInput } from "@/components/number-input";
import { useState, useEffect } from "react";
import CustomSlider from "@/components/custom-slider";
import CustomSwitch from "@/components/custom-switch";
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
  Trash2,
  Settings,
  Sparkles,
  FileUp,
  FileDown,
  Cpu,
  Check
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
  const [crossoverSensitivity, setCrossoverSensitivity] = useState(65);
  const [strength, setStrength] = useState(70);
  const [spikeMultiplier, setSpikeMultiplier] = useState(2.0);
  const [relativeThreshold, setRelativeThreshold] = useState(1.5);
  const [selectedStrategy, setSelectedStrategy] = useState("institutional_momentum");
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [toast, setToast] = useState<{ message: string, type: 'success' | 'error' } | null>(null);
  const [strategyParams, setStrategyParams] = useState<any>({});

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const [strategies, setStrategies] = useState([
    { id: "ema_rsi", name: "EMA + RSI (Classic)" },
    { id: "enhanced_ai", name: "Enhanced AI Strategy" },
    { id: "advanced_ai", name: "Advanced AI/ML" },
    { id: "premium", name: "Premium Options Alpha" },
    { id: "institutional_momentum", name: "Institutional Momentum" },
    { id: "ema_crossover", name: "Ultra-EMA Crossover Strategy" },
    { id: "meta_agent_swarm", name: "Meta-Agent AI Swarm (5 Brains)" },
    { id: "ultra_meta_dip_swarm", name: "Ultra Meta-Dip Swarm (6 Brains)" },
    { id: "buy_the_dip", name: "Buy the Dip (Mean Reversion)" },
  ]);

  const defaultSettings: Record<string, any> = {
    ema_rsi: {
      enable_volume_filter: true,
      enable_ema_filter: true,
      enable_vwap_filter: true,
      enable_rsi_filter: true,
      enable_option_chain_filter: false,
      enable_macd_filter: false,
      enable_greeks_filter: false,
    },
    enhanced_ai: {
      enable_volume_filter: false,
      enable_ema_filter: false,
      enable_vwap_filter: false,
      enable_rsi_filter: true,
      enable_option_chain_filter: true,
      enable_macd_filter: true,
      enable_greeks_filter: true,
    },
    premium: {
      enable_volume_filter: true,
      enable_ema_filter: false,
      enable_vwap_filter: true,
      enable_rsi_filter: true,
      enable_option_chain_filter: false,
      enable_macd_filter: true,
      enable_greeks_filter: false,
    },
  };

  const applyDefaults = (strategyId: string) => {
    const defaults = defaultSettings[strategyId];
    if (defaults) {
      setSettings({ ...settings, ...defaults });
      const strategyName = strategies.find(s => s.id === strategyId)?.name || strategyId;
      setToast({ message: `Applied ${strategyName} Defaults Successfully..`, type: 'success' });
    }
  };

  const tabs = [
    "Overview", "Strategy", "Indicators", "AI & Filters",
    "Option Chain", "Risk Management", "Execution", "Advanced", "Notifications"
  ];

  const loadSettings = () => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => setSettings(data))
      .catch(err => console.error('Failed to fetch settings:', err));
  };

  const loadStrategies = () => {
    fetch('/api/strategies')
      .then(res => res.json())
      .then(data => {
        if (data.strategies) {
          const strategyNames: Record<string, string> = {
            "ema_rsi": "EMA + RSI (Classic)",
            "enhanced_ai": "Enhanced AI Strategy",
            "premium": "Premium Options Alpha",
            "advanced_ai": "Advanced AI/ML",
            "institutional_momentum": "Institutional Momentum"
          };
          
          const mapped = data.strategies.map((id: string) => ({
            id: id,
            name: strategyNames[id] || id.split('_').map((word: string) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
          }));
          setStrategies(mapped);
        }
      })
      .catch(err => console.error('Failed to fetch strategies:', err));
  };

  useEffect(() => {
    loadSettings();
    loadStrategies();
  }, []);

  useEffect(() => {
    const activeStrat = settings.active_strategy || selectedStrategy;
    if (activeStrat) {
      fetch(`/api/strategy/parameters?name=${activeStrat}`)
        .then(res => res.json())
        .then(data => {
          if (data.parameters) {
            setStrategyParams(data.parameters);
          }
        })
        .catch(err => console.error('Failed to fetch strategy parameters:', err));
    }
  }, [settings.active_strategy, selectedStrategy]);

  const handleSave = () => {
    setShowSaveConfirm(true);
  };

  const executeSave = async () => {
    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      if (response.ok) {
        console.log('Save successful, setting toast');
        setToast({ message: 'Saved Settings Successfully..', type: 'success' });
      } else {
        setToast({ message: 'Failed to save settings.', type: 'error' });
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      setToast({ message: 'Error saving settings.', type: 'error' });
    }
  };

  const handleExport = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(settings, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", "strategy_settings.json");
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e: any) => {
        try {
          const json = JSON.parse(e.target.result);
          setSettings(json);
          setToast({ message: 'Imported Settings Successfully..', type: 'success' });
        } catch (error) {
          setToast({ message: 'Failed to parse JSON file.', type: 'error' });
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  // AI Confidence value
  const confidence = 0.75; // 75%
  const strokeDasharray = 125.6; // Circumference of semi-circle (PI * R, R=40)
  const strokeDashoffset = strokeDasharray * (1 - confidence);

  return (
    <div className="flex h-screen bg-background text-foreground font-sans">
      <Sidebar />

      <div className="flex-1 flex flex-col overflow-hidden bg-background">
        <Header />

        <main className="flex-1 overflow-y-auto p-8 space-y-8">
          {/* Header & Controls Section */}
          <div className="flex flex-col gap-5 w-full">
            {/* Title Row */}
            <div className="shrink-0">
              <h1 className="font-display font-extrabold text-3xl xl:text-4xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-foreground to-gray-500 whitespace-nowrap">Strategy Settings</h1>
              <p className="text-base text-muted-foreground mt-1">Configure and optimize your trading strategy parameters</p>
            </div>

            {/* Control Bar - Glass Container */}
            <div className="flex flex-wrap lg:flex-nowrap items-center gap-4 w-full glass-card p-4 rounded-2xl overflow-x-auto hide-scrollbar">
              <div className="flex items-center gap-3">
                <label className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Strategy:</label>
                <div className="relative">
                  <Cpu className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary pointer-events-none" />
                  <select
                    value={selectedStrategy}
                    onChange={(e) => {
                      setSelectedStrategy(e.target.value);
                      applyDefaults(e.target.value);
                    }}
                    className="bg-background border border-border rounded-xl pl-10 pr-4 py-2 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                  >
                    {strategies.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={() => applyDefaults(selectedStrategy)}
                  className="px-4 py-2 bg-[#ff4d4d] text-white rounded-xl text-sm font-bold hover:opacity-90 flex items-center gap-2 transition-all duration-200 shadow-lg shadow-red-500/20 hover:scale-[1.02] whitespace-nowrap"
                >
                  <Zap className="w-4 h-4" />
                  Set Defaults
                </button>
              </div>
              <button
                onClick={() => {
                  loadSettings();
                  setToast({ message: 'Reset Settings Successfully..', type: 'success' });
                }}
                className="px-4 py-2 bg-background border border-border rounded-xl text-sm font-bold text-foreground hover:bg-muted hover:border-border flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-primary/5 whitespace-nowrap"
              >
                <RotateCcw className="w-4 h-4 text-muted-foreground" />
                Reset
              </button>
              <button
                onClick={handleImport}
                className="px-4 py-2 bg-background border border-border rounded-xl text-sm font-bold text-foreground hover:bg-muted hover:border-border flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-primary/5 whitespace-nowrap"
              >
                <FileDown className="w-4 h-4 text-muted-foreground" />
                Import
              </button>
              <button
                onClick={handleExport}
                className="px-4 py-2 bg-background border border-border rounded-xl text-sm font-bold text-foreground hover:bg-muted hover:border-border flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-primary/5 whitespace-nowrap"
              >
                <FileUp className="w-4 h-4 text-muted-foreground" />
                Export
              </button>
              <div className="relative ml-auto shrink-0">
                {/* Toast */}
                {toast && (
                  <div className="absolute bottom-full mb-4 right-0 bg-gradient-to-r from-emerald-50 to-green-100 border border-emerald-200 rounded-lg p-2 shadow-2xl z-[100] flex items-center gap-2 text-emerald-900 whitespace-nowrap">
                    <div className="p-1 rounded-full bg-emerald-200 text-emerald-700">
                      <Check className="w-3 h-3" />
                    </div>
                    <span className="text-xs font-bold">{toast.message}</span>
                  </div>
                )}

                {/* Confirmation Popover */}
                {showSaveConfirm && (
                  <div className="absolute top-full mt-2 right-0 bg-card border border-border rounded-2xl p-6 w-[350px] space-y-4 shadow-2xl z-[100] transform transition-all">
                    <div className="flex items-center gap-3 text-yellow-500">
                      <ShieldAlert className="w-5 h-5" />
                      <h3 className="font-display font-extrabold text-base text-foreground">Confirm Save</h3>
                    </div>
                    <p className="text-xs text-muted-foreground font-medium">Are you sure you want to save these settings? This will overwrite the current live strategy configuration.</p>
                    <div className="flex justify-end gap-3 pt-2">
                      <button
                        onClick={() => setShowSaveConfirm(false)}
                        className="px-3 py-2 bg-background border border-border rounded-lg text-xs font-bold text-foreground hover:bg-muted transition-all duration-200"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          setShowSaveConfirm(false);
                          executeSave();
                        }}
                        className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-bold hover:opacity-90 transition-all duration-200 shadow-lg shadow-primary/30"
                      >
                        Save
                      </button>
                    </div>
                  </div>
                )}

                <button
                  onClick={handleSave}
                  className="px-6 py-2 bg-primary text-white rounded-xl text-sm font-bold hover:opacity-90 flex items-center gap-2 transition-all duration-200 shadow-lg shadow-primary/30 hover:scale-[1.02] whitespace-nowrap"
                >
                  <Save className="w-4 h-4" />
                  Save Settings
                </button>
              </div>
            </div>
          </div>

          {/* Tabs Matrix */}
          <div className="flex gap-2 border-b border-border">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-3 text-sm font-bold transition-all duration-200 whitespace-nowrap relative ${activeTab === tab
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
                  }`}
              >
                {tab}
                {activeTab === tab && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary shadow-[0_0_12px_var(--glow-primary)]"></div>
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
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                  {/* === COLUMN 1 === */}
                    {/* Strategy Mode */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
                            <Compass className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">Strategy Mode</h3>
                        </div>

                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Select Strategy Mode</label>
                            <select
                              value={settings.active_strategy || "institutional_momentum"}
                              onChange={(e) => setSettings({ ...settings, active_strategy: e.target.value })}
                              className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                            >
                              <option value="ema_rsi">EMA + RSI (Classic)</option>
                              <option value="enhanced_ai">Enhanced AI Strategy</option>
                              <option value="advanced_ai">Advanced AI/ML</option>
                              <option value="premium">Premium Options Alpha</option>
                              <option value="institutional_momentum">Institutional Momentum</option>
                              <option value="ema_crossover">Ultra-EMA Crossover Strategy</option>
                              <option value="meta_agent_swarm">Meta-Agent AI Swarm (5 Brains)</option>
                              <option value="ultra_meta_dip_swarm">Ultra Meta-Dip Swarm (6 Brains)</option>
                              <option value="buy_the_dip">Buy the Dip (Mean Reversion)</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Timeframe</label>
                            <select
                              value={settings.timeframe || "5 Min"}
                              onChange={(e) => setSettings({ ...settings, timeframe: e.target.value })}
                              className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                            >
                              <option value="1 Min">1 Min</option>
                              <option value="3 Min">3 Min</option>
                              <option value="5 Min">5 Min</option>
                              <option value="15 Min">15 Min</option>
                              <option value="30 Min">30 Min</option>
                              <option value="1 Hour">1 Hour</option>
                              <option value="1 Week">1 Week</option>
                              <option value="1 Month">1 Month</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Max Trades / Day</label>
                          <div className="flex items-center border border-border rounded-lg bg-background overflow-hidden focus-within:ring-2 focus-within:ring-primary transition-all">
                            <button
                              onClick={() => setSettings({ ...settings, max_trades_per_day: Math.max(0, (settings.max_trades_per_day !== undefined ? settings.max_trades_per_day : 0) - 1) })}
                              className="px-4 py-2.5 hover:bg-muted text-muted-foreground transition-colors hover:text-foreground"
                            >
                              <Minus className="w-4 h-4" />
                            </button>
                            <input type="text" value={settings.max_trades_per_day === 0 || settings.max_trades_per_day === undefined ? "Unlimited" : settings.max_trades_per_day} className="w-full bg-transparent text-center text-sm font-extrabold text-foreground focus:outline-none" readOnly />
                            <button
                              onClick={() => setSettings({ ...settings, max_trades_per_day: (settings.max_trades_per_day !== undefined ? settings.max_trades_per_day : 0) + 1 })}
                              className="px-4 py-2.5 hover:bg-muted text-muted-foreground transition-colors hover:text-foreground"
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <div>
                          <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Cooldown (min)</label>
                          <NumberInput defaultValue="15" min={1} step={1} />
                        </div>
                      </div>
                    </div>

                    {/* Volume Settings */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
                            <BarChart2 className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">Volume Settings</h3>
                        </div>

                        <div className="space-y-5 mt-4">
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-muted-foreground">Spike Multiplier</span>
                              <span className="text-[#ec4899] font-extrabold text-sm">{spikeMultiplier.toFixed(1)}x</span>
                            </div>
                            <CustomSlider
                              min={1}
                              max={5}
                              step={0.5}
                              value={spikeMultiplier}
                              onChange={setSpikeMultiplier}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-muted-foreground">Relative Threshold</span>
                              <span className="text-[#ec4899] font-extrabold text-sm">{relativeThreshold.toFixed(1)}x</span>
                            </div>
                            <CustomSlider
                              min={1}
                              max={3}
                              step={0.1}
                              value={relativeThreshold}
                              onChange={setRelativeThreshold}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Volume Filter</span>
                        <CustomSwitch
                          checked={settings.enable_volume_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_volume_filter: checked })}
                        />
                      </div>
                    </div>
                  {/* === COLUMN 2 === */}
                    {/* Strategy Parameters */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#3b82f6]/20 rounded-xl text-[#3b82f6] shadow-lg shadow-blue-500/10">
                            <Sliders className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">Strategy Parameters</h3>
                        </div>

                        <div className="space-y-4 mt-4 overflow-y-auto max-h-full min-h-[250px]">
                          {Object.keys(strategyParams).length > 0 ? (
                            Object.keys(strategyParams).map((paramName) => (
                              <div key={paramName}>
                                <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">{paramName.replace(/_/g, ' ')}</label>
                                <input
                                  type="text"
                                  value={settings[paramName] !== undefined ? settings[paramName] : strategyParams[paramName].default}
                                  onChange={(e) => setSettings({ ...settings, [paramName]: e.target.value })}
                                  className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                                />
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-muted-foreground">No parameters found for this strategy.</p>
                          )}
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Auto-discovered</span>
                        <Zap className="w-4 h-4 text-emerald-500" />
                      </div>
                    </div>

                    {/* VWAP Settings */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#06b6d4]/20 rounded-xl text-[#06b6d4] shadow-lg shadow-cyan-500/10">
                            <Sliders className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">VWAP Settings</h3>
                        </div>

                        <div className="space-y-5 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">VWAP Confirmation</label>
                            <select className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all">
                              <option>Price Above VWAP</option>
                            </select>
                          </div>
                          <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-wider">
                              <span className="text-muted-foreground">Strength</span>
                              <span className="text-[#06b6d4] font-extrabold text-sm">{strength}%</span>
                            </div>
                            <CustomSlider
                              min={10}
                              max={100}
                              value={strength}
                              onChange={setStrength}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable VWAP Filter</span>
                        <CustomSwitch
                          checked={settings.enable_vwap_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_vwap_filter: checked })}
                        />
                      </div>
                    </div>
                  {/* === COLUMN 3 === */}
                    {/* RSI Settings */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
                            <Zap className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">RSI Settings</h3>
                        </div>

                        <div className="space-y-5 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">RSI Period</label>
                            <NumberInput
                              value={settings.rsi_window || 14}
                              onChange={(val) => setSettings({ ...settings, rsi_window: Number(val) })}
                              min={1}
                              step={1}
                            />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Overbought</label>
                              <NumberInput
                                value={settings.rsi_sell || 70}
                                onChange={(val) => setSettings({ ...settings, rsi_sell: Number(val) })}
                                min={1}
                                step={1}
                              />
                            </div>
                            <div>
                              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Oversold</label>
                              <NumberInput
                                value={settings.rsi_buy || 30}
                                onChange={(val) => setSettings({ ...settings, rsi_buy: Number(val) })}
                                min={1}
                                step={1}
                              />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable RSI Filter</span>
                        <CustomSwitch
                          checked={settings.enable_rsi_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_rsi_filter: checked })}
                        />
                      </div>
                    </div>

                    {/* Option Chain Filters */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#f59e0b]/20 rounded-xl text-[#f59e0b] shadow-lg shadow-amber-500/10">
                            <Layers className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">Option Chain</h3>
                        </div>

                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Min OI</label>
                            <NumberInput defaultValue="1000" min={1} step={100} />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">PCR Upper</label>
                              <NumberInput defaultValue="1.20" step={0.05} />
                            </div>
                            <div>
                              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">PCR Lower</label>
                              <NumberInput defaultValue="0.80" step={0.05} />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Option Chain Filter</span>
                        <CustomSwitch
                          checked={settings.enable_option_chain_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_option_chain_filter: checked })}
                        />
                      </div>
                    </div>
                  {/* === COLUMN 4 === */}
                    {/* MACD Settings */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#ff9f43]/20 rounded-xl text-[#ff9f43] shadow-lg shadow-orange-500/10">
                            <Sliders className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">MACD Settings</h3>
                        </div>

                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Fast Length</label>
                            <select className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all">
                              <option>12</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Slow Length</label>
                            <select className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all">
                              <option>26</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable MACD Filter</span>
                        <CustomSwitch
                          checked={settings.enable_macd_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_macd_filter: checked })}
                        />
                      </div>
                    </div>

                    {/* Greeks Filters */}
                    <div className="glass-card p-6 rounded-2xl space-y-5 h-full min-h-[420px] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
                      <div>
                        <div className="flex items-center gap-3 border-b border-border pb-3">
                          <div className="p-2.5 bg-[#8c52ff]/20 rounded-xl text-[#8c52ff] shadow-lg shadow-purple-500/10">
                            <ShieldAlert className="w-5 h-5" />
                          </div>
                          <h3 className="font-display font-extrabold text-base text-foreground">Greeks Filters</h3>
                        </div>

                        <div className="space-y-4 mt-4">
                          <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Delta Range</label>
                            <div className="flex items-center gap-3">
                              <NumberInput defaultValue="0.40" step={0.05} />
                              <span className="text-muted-foreground text-xs">to</span>
                              <NumberInput defaultValue="0.70" step={0.05} />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex justify-between items-center pt-3 border-t border-border">
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Greeks Filter</span>
                        <CustomSwitch
                          checked={settings.enable_greeks_filter || false}
                          onChange={(checked) => setSettings({ ...settings, enable_greeks_filter: checked })}
                        />
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
              <div className="bg-card text-foreground p-6 rounded-2xl shadow-xl space-y-4 border border-border hover:scale-[1.02] transition-transform">
                <div className="flex items-center gap-2 border-b border-border pb-2">
                  <span>👑</span>
                  <h3 className="font-display font-extrabold text-sm uppercase tracking-wider">Strategy Summary</h3>
                </div>
                <div className="space-y-3 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Strategy Mode</span>
                    <span className="font-extrabold">Momentum</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Trade Style</span>
                    <span className="font-extrabold">Intraday</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">AI Confidence</span>
                    <span className="font-extrabold text-emerald-500">≥ 75%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Risk per Trade</span>
                    <span className="font-extrabold">1.00%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Daily Max Loss</span>
                    <span className="font-extrabold">3.00%</span>
                  </div>
                  <div className="flex justify-between items-center pt-2 border-t border-border">
                    <span className="text-muted-foreground">Status</span>
                    <span className="px-3 py-1 bg-emerald-500 text-white font-extrabold rounded-lg text-[10px]">ACTIVE</span>
                  </div>
                </div>
              </div>

              {/* AI Confidence Preview */}
              <div className="bg-card p-6 rounded-2xl border border-border space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-foreground uppercase tracking-wider">AI Confidence</h3>
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
                      stroke="currentColor"
                      className="text-border"
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
                    <span className="font-display font-extrabold text-3xl text-foreground">75%</span>
                    <p className="text-xs text-emerald-400 font-extrabold tracking-wide">EXCELLENT</p>
                  </div>

                  <div className="flex justify-between w-40 text-[10px] text-muted-foreground mt-1">
                    <span>0%</span>
                    <span>100%</span>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-slate-500/50 space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-foreground uppercase tracking-wider">Quick Actions</h3>
                <div className="space-y-2">
                  <button className="w-full text-left px-4 py-3 bg-background hover:bg-muted rounded-xl text-xs font-bold text-foreground flex items-center gap-3 transition-colors border border-border hover:scale-[1.02] transform">
                    <Zap className="w-4 h-4 text-amber-500" />
                    Run Backtest
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-background hover:bg-muted rounded-xl text-xs font-bold text-foreground flex items-center gap-3 transition-colors border border-border hover:scale-[1.02] transform">
                    <BarChart2 className="w-4 h-4 text-[#3b82f6]" />
                    View Performance
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-background hover:bg-muted rounded-xl text-xs font-bold text-foreground flex items-center gap-3 transition-colors border border-border hover:scale-[1.02] transform">
                    <Upload className="w-4 h-4 text-emerald-500" />
                    Load Preset
                  </button>
                  <button className="w-full text-left px-4 py-3 bg-background hover:bg-muted rounded-xl text-xs font-bold text-foreground flex items-center gap-3 transition-colors border border-border hover:scale-[1.02] transform">
                    <Save className="w-4 h-4 text-[#8c52ff]" />
                    Save as Preset
                  </button>
                </div>
              </div>

              {/* Preset Manager */}
              <div className="bg-card p-6 rounded-2xl border border-border space-y-4 shadow-xl">
                <h3 className="font-display font-extrabold text-sm text-foreground uppercase tracking-wider">Preset Manager</h3>
                <div className="flex gap-1.5 items-center">
                  <select className="flex-1 min-w-0 bg-background border border-border rounded-lg px-2 py-2 text-xs font-bold text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent">
                    <option>My Momentum Setup</option>
                    <option>Conservative Grid</option>
                  </select>
                  <button className="p-2 bg-background hover:bg-muted border border-border rounded-lg text-muted-foreground hover:text-foreground transition-colors shrink-0">
                    <Eye className="w-4 h-4" />
                  </button>
                  <button className="p-2 bg-background hover:bg-muted border border-border rounded-lg text-red-500 hover:text-red-400 transition-colors shrink-0">
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
