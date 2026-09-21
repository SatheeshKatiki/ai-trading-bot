"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Sliders,
  Eye,
  Palette,
  Clock,
  RotateCcw,
  Check,
  ChevronDown,
  Layers,
  BarChart3,
  Activity,
  Sparkles,
  Info,
  BookOpen,
  ExternalLink
} from "lucide-react";
import {
  IndicatorSettingsData,
  defaultIndicatorSettings
} from "@/components/indicator-settings";

export type IndicatorType = "smc" | "frvp" | "rsi";

interface TradingViewIndicatorModalProps {
  isOpen: boolean;
  indicator: IndicatorType | null;
  onClose: () => void;
  onSave?: (indicator: IndicatorType, settings: IndicatorSettingsData) => void;
  onOpenDocs?: (indicator: IndicatorType) => void;
}

export default function TradingViewIndicatorModal({
  isOpen,
  indicator,
  onClose,
  onSave,
  onOpenDocs,
}: TradingViewIndicatorModalProps) {
  const [activeTab, setActiveTab] = useState<"inputs" | "style" | "visibility">("inputs");
  const [settings, setSettings] = useState<IndicatorSettingsData>(defaultIndicatorSettings);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [showDefaultsMenu, setShowDefaultsMenu] = useState(false);

  // Load latest settings on open
  useEffect(() => {
    if (!isOpen) return;

    setActiveTab("inputs");
    setShowDefaultsMenu(false);

    const loadSettings = async () => {
      try {
        const local = localStorage.getItem("mana_indicator_settings");
        if (local) {
          try {
            const parsed = JSON.parse(local);
            setSettings((prev) => ({ ...prev, ...parsed }));
          } catch {}
        }

        const res = await fetch("/api/settings");
        if (res.ok) {
          const data = await res.json();
          if (data.indicator_settings) {
            setSettings((prev) => ({ ...prev, ...data.indicator_settings }));
          }
        }
      } catch (e) {
        console.error("Failed to load indicator settings:", e);
      }
    };
    loadSettings();
  }, [isOpen, indicator]);

  if (!isOpen || !indicator) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      localStorage.setItem("mana_indicator_settings", JSON.stringify(settings));

      // Dispatch custom event so open charts update immediately in real-time
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("indicatorSettingsChanged", {
            detail: { indicator, settings },
          })
        );
      }

      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indicator_settings: settings }),
      });

      if (onSave) {
        onSave(indicator, settings);
      }

      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
        onClose();
      }, 400);
    } catch (e) {
      console.error("Error saving indicator settings:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (indicator === "smc") {
      setSettings((prev) => ({ ...prev, smc: defaultIndicatorSettings.smc }));
    } else if (indicator === "frvp") {
      setSettings((prev) => ({ ...prev, frvp: defaultIndicatorSettings.frvp }));
    } else if (indicator === "rsi") {
      setSettings((prev) => ({ ...prev, rsi: defaultIndicatorSettings.rsi }));
    }
    setShowDefaultsMenu(false);
  };

  // Institutional Indicator Metadata (Author: Mana AI)
  const indicatorMetadata = {
    smc: {
      title: "Smart Money Concepts (SMC Pro)",
      subtitle: "Author: Mana AI • Institutional Structure & Order Flow Engine",
      icon: <Layers className="w-4 h-4 text-emerald-400" />,
      hasVisibilityTab: true,
      docUrl: "/docs?tab=chart-indicators#smc",
    },
    frvp: {
      title: "Fixed Range Volume Profile (FRVP)",
      subtitle: "Author: Mana AI • Institutional Auction Volume Engine",
      icon: <BarChart3 className="w-4 h-4 text-amber-400" />,
      hasVisibilityTab: false,
      docUrl: "/docs?tab=chart-indicators#volume-profile",
    },
    rsi: {
      title: "Momentum RSI Divergence Engine (MDE Pro)",
      subtitle: "Author: Mana AI • Wilder RSI 14 + Signal EMA 20 + Divergences",
      icon: <Activity className="w-4 h-4 text-purple-400" />,
      hasVisibilityTab: false,
      docUrl: "/docs?tab=chart-indicators#rsi-divergence",
    },
  };

  const meta = indicatorMetadata[indicator];

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 sm:p-6 bg-black/65 backdrop-blur-sm animate-in fade-in duration-150">
      {/* Modal Container: Styled in Mana Dark Luxury Theme */}
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.15 }}
        className="w-full max-w-[620px] bg-[#1e222d] border border-[#2a2e39] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-[#d1d4dc] font-sans select-none"
      >
        {/* Indicator Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#2a2e39] bg-[#1e222d]">
          <div className="flex items-center gap-2.5">
            <div className="p-1 rounded bg-[#2a2e39]">{meta.icon}</div>
            <div>
              <h2 className="text-sm font-bold text-[#f0f3fa] tracking-tight flex items-center gap-2">
                {meta.title}
                <span className="text-[9px] tracking-wider uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  MANA AI
                </span>
              </h2>
              <p className="text-[10px] text-[#787b86] font-mono mt-0.5">{meta.subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Documentation Link Button */}
            <button
              type="button"
              onClick={() => {
                if (onOpenDocs) {
                  onOpenDocs(indicator);
                } else if (typeof window !== "undefined") {
                  window.open(meta.docUrl, "_blank");
                }
              }}
              className="px-2.5 py-1 rounded text-[11px] font-semibold text-[#38bdf8] hover:text-white hover:bg-[#38bdf8]/20 transition-colors flex items-center gap-1.5 border border-[#38bdf8]/40"
              title="View Full Indicator Documentation"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Documentation</span>
              <ExternalLink className="w-2.5 h-2.5 opacity-70" />
            </button>

            <button
              onClick={onClose}
              className="text-[#787b86] hover:text-[#f0f3fa] p-1.5 rounded-lg hover:bg-[#2a2e39] transition-colors"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* TradingView Tab Navigation */}
        <div className="flex items-center px-5 border-b border-[#2a2e39] bg-[#171b26] gap-7">
          <button
            type="button"
            onClick={() => setActiveTab("inputs")}
            className={`py-2.5 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
              activeTab === "inputs"
                ? "border-[#2962ff] text-[#f0f3fa]"
                : "border-transparent text-[#787b86] hover:text-[#d1d4dc]"
            }`}
          >
            <Sliders className="w-3 h-3" />
            Inputs
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("style")}
            className={`py-2.5 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
              activeTab === "style"
                ? "border-[#2962ff] text-[#f0f3fa]"
                : "border-transparent text-[#787b86] hover:text-[#d1d4dc]"
            }`}
          >
            <Palette className="w-3 h-3" />
            Style
          </button>
          {meta.hasVisibilityTab && (
            <button
              type="button"
              onClick={() => setActiveTab("visibility")}
              className={`py-2.5 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
                activeTab === "visibility"
                  ? "border-[#2962ff] text-[#f0f3fa]"
                  : "border-transparent text-[#787b86] hover:text-[#d1d4dc]"
              }`}
            >
              <Clock className="w-3 h-3" />
              Visibility
            </button>
          )}
        </div>

        {/* TradingView Form Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6 bg-[#131722] custom-scrollbar text-xs">
          {/* ========================================================= */}
          {/* 1. LUXALGO SMART MONEY CONCEPTS (SMC)                     */}
          {/* ========================================================= */}
          {indicator === "smc" && activeTab === "inputs" && (
            <div className="space-y-6">
              {/* Mode & Coloring */}
              <div className="space-y-3">
                <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                  General Mode & Coloring
                </h4>
                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Mode</span>
                  <select
                    value={settings.smc.mode}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, mode: e.target.value as any },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  >
                    <option value="Present">Present (Active Only)</option>
                    <option value="Historical">Historical</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Style</span>
                  <select
                    value={settings.smc.style}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, style: e.target.value as any },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  >
                    <option value="Colored">Colored</option>
                    <option value="Monochrome">Monochrome</option>
                  </select>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Color Candles by Order Flow</span>
                  <input
                    type="checkbox"
                    checked={settings.smc.color_candles}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, color_candles: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
              </div>

              {/* Internal Structure */}
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b border-[#2a2e39] pb-1">
                  <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86]">
                    Real-Time Internal Structure
                  </h4>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_internal_structure}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_internal_structure: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
                {settings.smc.show_internal_structure && (
                  <>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Internal Structure Colors</span>
                      <div className="flex items-center gap-3">
                        <input
                          type="color"
                          value={settings.smc.internal_bullish_color}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              smc: { ...settings.smc, internal_bullish_color: e.target.value },
                            })
                          }
                          className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                          title="Bullish Color"
                        />
                        <input
                          type="color"
                          value={settings.smc.internal_bearish_color}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              smc: { ...settings.smc, internal_bearish_color: e.target.value },
                            })
                          }
                          className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                          title="Bearish Color"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-[#d1d4dc]">Confluence Filter</span>
                      <input
                        type="checkbox"
                        checked={settings.smc.internal_confluence_filter}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: {
                              ...settings.smc,
                              internal_confluence_filter: e.target.checked,
                            },
                          })
                        }
                        className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                      />
                    </div>
                  </>
                )}
              </div>

              {/* Real-Time Swing Structure */}
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b border-[#2a2e39] pb-1">
                  <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86]">
                    Real-Time Swing Structure
                  </h4>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_swing_structure}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_swing_structure: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
                {settings.smc.show_swing_structure && (
                  <>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Swing Points Length</span>
                      <input
                        type="number"
                        min="5"
                        max="200"
                        value={settings.smc.swing_points_length}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: {
                              ...settings.smc,
                              swing_points_length: parseInt(e.target.value) || 50,
                            },
                          })
                        }
                        className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Swing Colors</span>
                      <div className="flex items-center gap-3">
                        <input
                          type="color"
                          value={settings.smc.swing_bullish_color}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              smc: { ...settings.smc, swing_bullish_color: e.target.value },
                            })
                          }
                          className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                          title="Swing Bullish Color"
                        />
                        <input
                          type="color"
                          value={settings.smc.swing_bearish_color}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              smc: { ...settings.smc, swing_bearish_color: e.target.value },
                            })
                          }
                          className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                          title="Swing Bearish Color"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-[#d1d4dc]">Show Swing Points</span>
                      <input
                        type="checkbox"
                        checked={settings.smc.show_swing_points}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, show_swing_points: e.target.checked },
                          })
                        }
                        className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                      />
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-[#d1d4dc]">Show Strong/Weak High & Low</span>
                      <input
                        type="checkbox"
                        checked={settings.smc.show_strong_weak_high_low}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: {
                              ...settings.smc,
                              show_strong_weak_high_low: e.target.checked,
                            },
                          })
                        }
                        className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                      />
                    </div>
                  </>
                )}
              </div>

              {/* Order Blocks (OB) */}
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b border-[#2a2e39] pb-1">
                  <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86]">
                    Order Blocks (OB)
                  </h4>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_order_blocks}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_order_blocks: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
                {settings.smc.show_order_blocks && (
                  <>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Internal Order Blocks Count</span>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={settings.smc.internal_ob_count}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: {
                              ...settings.smc,
                              internal_ob_count: parseInt(e.target.value) || 3,
                            },
                          })
                        }
                        className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Swing Order Blocks Count</span>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={settings.smc.swing_ob_count}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: {
                              ...settings.smc,
                              swing_ob_count: parseInt(e.target.value) || 3,
                            },
                          })
                        }
                        className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">OB Filter Method</span>
                      <select
                        value={settings.smc.ob_filter}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, ob_filter: e.target.value as any },
                          })
                        }
                        className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                      >
                        <option value="ATR">ATR Filter</option>
                        <option value="Cumulative Volume">Cumulative Volume</option>
                        <option value="None">None</option>
                      </select>
                    </div>
                    <div className="grid grid-cols-2 gap-4 items-center">
                      <span className="text-[#d1d4dc]">Mitigation Trigger</span>
                      <select
                        value={settings.smc.ob_mitigation}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, ob_mitigation: e.target.value as any },
                          })
                        }
                        className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                      >
                        <option value="High/Low">High/Low Wicks</option>
                        <option value="Close">Close Price</option>
                      </select>
                    </div>
                  </>
                )}
              </div>

              {/* Fair Value Gaps & EQH/EQL */}
              <div className="space-y-3">
                <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                  Liquidity: FVG & Equal Highs/Lows
                </h4>
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Show Fair Value Gaps (FVG)</span>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_fvg}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_fvg: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
                {settings.smc.show_fvg && (
                  <div className="grid grid-cols-2 gap-4 items-center">
                    <span className="text-[#d1d4dc]">Extend FVG (Bars)</span>
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={settings.smc.fvg_extend}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          smc: { ...settings.smc, fvg_extend: parseInt(e.target.value) || 20 },
                        })
                      }
                      className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                    />
                  </div>
                )}
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Show Equal High / Low (EQH/EQL)</span>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_equal_high_low}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_equal_high_low: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
              </div>

              {/* MTF & Premium / Discount */}
              <div className="space-y-3">
                <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                  Multi-Timeframe & Zones
                </h4>
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Show Daily/Weekly/Monthly High & Low</span>
                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.smc.mtf_daily}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, mtf_daily: e.target.checked },
                          })
                        }
                        className="w-3.5 h-3.5 accent-[#2962ff]"
                      />
                      <span className="text-[11px] text-[#787b86]">D</span>
                    </label>
                    <label className="flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.smc.mtf_weekly}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, mtf_weekly: e.target.checked },
                          })
                        }
                        className="w-3.5 h-3.5 accent-[#2962ff]"
                      />
                      <span className="text-[11px] text-[#787b86]">W</span>
                    </label>
                    <label className="flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.smc.mtf_monthly}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            smc: { ...settings.smc, mtf_monthly: e.target.checked },
                          })
                        }
                        className="w-3.5 h-3.5 accent-[#2962ff]"
                      />
                      <span className="text-[11px] text-[#787b86]">M</span>
                    </label>
                  </div>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Show Premium & Discount Zones</span>
                  <input
                    type="checkbox"
                    checked={settings.smc.show_premium_discount}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        smc: { ...settings.smc, show_premium_discount: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {indicator === "smc" && activeTab === "style" && (
            <div className="space-y-4">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                Visual Graphic Objects
              </h4>
              <div className="space-y-2.5">
                {[
                  { key: "plot_candles", label: "Plot Candles" },
                  { key: "show_boxes", label: "Boxes (Order Blocks & FVG)" },
                  { key: "show_panel_labels", label: "Panel Labels (BOS / CHoCH)" },
                  { key: "show_lines", label: "Lines (Equilibrium / MTF High-Low)" },
                  { key: "labels_on_price_scale", label: "Labels on Price Scale" },
                  { key: "values_in_status_line", label: "Values in Status Line" },
                  { key: "inputs_in_status_line", label: "Inputs in Status Line" },
                ].map((item) => (
                  <div key={item.key} className="flex items-center justify-between py-1">
                    <span className="text-[#d1d4dc]">{item.label}</span>
                    <input
                      type="checkbox"
                      checked={(settings.smc as any)[item.key]}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          smc: { ...settings.smc, [item.key]: e.target.checked },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {indicator === "smc" && activeTab === "visibility" && (
            <div className="space-y-4">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                Timeframe Visibility
              </h4>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { key: "vis_seconds", label: "Seconds (1s - 59s)" },
                  { key: "vis_minutes", label: "Minutes (1m - 59m)" },
                  { key: "vis_hours", label: "Hours (1h - 24h)" },
                  { key: "vis_days", label: "Days (1D - 366D)" },
                  { key: "vis_weeks", label: "Weeks (1W - 52W)" },
                  { key: "vis_months", label: "Months (1M - 12M)" },
                ].map((tf) => (
                  <div key={tf.key} className="flex items-center justify-between p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                    <span className="text-[#d1d4dc] text-[11px]">{tf.label}</span>
                    <input
                      type="checkbox"
                      checked={(settings.smc as any)[tf.key]}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          smc: { ...settings.smc, [tf.key]: e.target.checked },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ========================================================= */}
          {/* 2. FIXED RANGE VOLUME PROFILE (FRVP)                      */}
          {/* ========================================================= */}
          {indicator === "frvp" && activeTab === "inputs" && (
            <div className="space-y-5">
              <div className="flex items-center justify-between border-b border-[#2a2e39] pb-2">
                <span className="text-sm font-semibold text-[#f0f3fa]">Enable Fixed Range Profile</span>
                <input
                  type="checkbox"
                  checked={settings.frvp.enabled}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      frvp: { ...settings.frvp, enabled: e.target.checked },
                    })
                  }
                  className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                />
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Row Bins Count</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="10"
                      max="200"
                      value={settings.frvp.num_bins}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          frvp: { ...settings.frvp, num_bins: parseInt(e.target.value) || 50 },
                        })
                      }
                      className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff] w-24"
                    />
                    <span className="text-[11px] text-[#787b86]">Bins</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Value Area Volume %</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="50"
                      max="90"
                      value={settings.frvp.value_area_pct}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          frvp: { ...settings.frvp, value_area_pct: parseInt(e.target.value) || 70 },
                        })
                      }
                      className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff] w-24"
                    />
                    <span className="text-[11px] text-[#787b86]">%</span>
                  </div>
                </div>

                <div className="flex items-center justify-between py-1">
                  <span className="text-[#d1d4dc]">Volume Delta Split (Buyers vs Sellers)</span>
                  <input
                    type="checkbox"
                    checked={settings.frvp.show_volume_delta}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        frvp: { ...settings.frvp, show_volume_delta: e.target.checked },
                      })
                    }
                    className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {indicator === "frvp" && activeTab === "style" && (
            <div className="space-y-4">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                Profile Levels & Colors
              </h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={settings.frvp.show_poc}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          frvp: { ...settings.frvp, show_poc: e.target.checked },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                    <span className="text-[#d1d4dc]">Point of Control (POC)</span>
                  </div>
                  <input
                    type="color"
                    value={settings.frvp.poc_color}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        frvp: { ...settings.frvp, poc_color: e.target.value },
                      })
                    }
                    className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                  />
                </div>

                <div className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={settings.frvp.show_value_area}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          frvp: { ...settings.frvp, show_value_area: e.target.checked },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                    <span className="text-[#d1d4dc]">Value Area High & Low (VAH / VAL)</span>
                  </div>
                  <input
                    type="color"
                    value={settings.frvp.vah_color}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        frvp: {
                          ...settings.frvp,
                          vah_color: e.target.value,
                          val_color: e.target.value,
                        },
                      })
                    }
                    className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                  />
                </div>

                <div className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={settings.frvp.show_hvn_lvn}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          frvp: { ...settings.frvp, show_hvn_lvn: e.target.checked },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                    <span className="text-[#d1d4dc]">High & Low Volume Nodes (HVN / LVN)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================= */}
          {/* 3. RSI DIVERGENCE & MOMENTUM ENGINE                       */}
          {/* ========================================================= */}
          {indicator === "rsi" && activeTab === "inputs" && (
            <div className="space-y-5">
              <div className="flex items-center justify-between border-b border-[#2a2e39] pb-2">
                <span className="text-sm font-semibold text-[#f0f3fa]">Enable RSI Divergence Engine</span>
                <input
                  type="checkbox"
                  checked={settings.rsi.enabled}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      rsi: { ...settings.rsi, enabled: e.target.checked },
                    })
                  }
                  className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                />
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">RSI Period (Wilder's)</span>
                  <input
                    type="number"
                    min="2"
                    max="100"
                    value={settings.rsi.period}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        rsi: { ...settings.rsi, period: parseInt(e.target.value) || 14 },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Signal EMA Length</span>
                  <input
                    type="number"
                    min="2"
                    max="100"
                    value={settings.rsi.ma_length}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        rsi: { ...settings.rsi, ma_length: parseInt(e.target.value) || 20 },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Overbought Threshold</span>
                  <input
                    type="number"
                    min="50"
                    max="95"
                    value={settings.rsi.overbought}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        rsi: { ...settings.rsi, overbought: parseInt(e.target.value) || 70 },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4 items-center">
                  <span className="text-[#d1d4dc]">Oversold Threshold</span>
                  <input
                    type="number"
                    min="5"
                    max="50"
                    value={settings.rsi.oversold}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        rsi: { ...settings.rsi, oversold: parseInt(e.target.value) || 30 },
                      })
                    }
                    className="bg-[#2a2e39] text-[#f0f3fa] border border-[#363a45] rounded px-2.5 py-1.5 outline-none focus:border-[#2962ff]"
                  />
                </div>

                <div className="pt-2 border-t border-[#2a2e39] space-y-2">
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[#d1d4dc]">Detect Regular Bullish / Bearish (Reversal)</span>
                    <input
                      type="checkbox"
                      checked={settings.rsi.detect_regular_bullish}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          rsi: {
                            ...settings.rsi,
                            detect_regular_bullish: e.target.checked,
                            detect_regular_bearish: e.target.checked,
                          },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[#d1d4dc]">Detect Hidden Bullish / Bearish (Continuation)</span>
                    <input
                      type="checkbox"
                      checked={settings.rsi.detect_hidden_bullish}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          rsi: {
                            ...settings.rsi,
                            detect_hidden_bullish: e.target.checked,
                            detect_hidden_bearish: e.target.checked,
                          },
                        })
                      }
                      className="w-4 h-4 rounded accent-[#2962ff] cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {indicator === "rsi" && activeTab === "style" && (
            <div className="space-y-4">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-[#787b86] border-b border-[#2a2e39] pb-1">
                Visual Line & Plots
              </h4>
              <div className="flex items-center justify-between py-1">
                <span className="text-[#d1d4dc]">RSI Plot Line Color</span>
                <input
                  type="color"
                  value={settings.rsi.color}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      rsi: { ...settings.rsi, color: e.target.value },
                    })
                  }
                  className="w-6 h-6 rounded cursor-pointer border border-[#363a45] bg-transparent"
                />
              </div>
            </div>
          )}
        </div>

        {/* TradingView Bottom Action Bar */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[#2a2e39] bg-[#1e222d]">
          {/* Defaults Button */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowDefaultsMenu(!showDefaultsMenu)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold text-[#787b86] hover:text-[#f0f3fa] hover:bg-[#2a2e39] transition-colors"
            >
              Defaults
              <ChevronDown className="w-3 h-3" />
            </button>

            {showDefaultsMenu && (
              <div className="absolute bottom-full left-0 mb-1.5 w-44 bg-[#1e222d] border border-[#2a2e39] rounded-md shadow-xl py-1 z-50 text-xs">
                <button
                  type="button"
                  onClick={handleReset}
                  className="w-full text-left px-3 py-1.5 hover:bg-[#2962ff] hover:text-white transition-colors flex items-center gap-2"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset Settings
                </button>
              </div>
            )}
          </div>

          {/* Action Buttons: Cancel and Ok */}
          <div className="flex items-center gap-2.5">
            {savedSuccess && (
              <span className="text-xs font-medium text-emerald-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Saved
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded text-xs font-semibold text-[#d1d4dc] bg-[#2a2e39] hover:bg-[#363a45] transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-1.5 rounded text-xs font-bold text-white bg-[#2962ff] hover:bg-[#1e53e5] active:bg-[#1848cc] transition-all shadow-md disabled:opacity-50"
            >
              {saving ? "Saving..." : "Ok"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
