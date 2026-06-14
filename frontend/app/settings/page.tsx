"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import {
  User,
  Bell,
  Shield,
  Globe,
  Moon,
  Sun,
  Mail,
  Check,
  Zap,
  Palette,
  Layout,
  Layers,
  Lock,
  RotateCcw
} from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import CustomSwitch from "@/components/custom-switch";

export default function Settings() {
  const { 
    theme, setTheme, 
    accentColor, setAccentColor, 
    density, setDensity, 
    glassEnabled, setGlassEnabled 
  } = useTheme();

  const [customHex, setCustomHex] = useState(accentColor);
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    setCustomHex(accentColor);
  }, [accentColor]);

  const handleHexInput = (raw: string) => {
    const cleanHex = raw.replace(/[^0-9A-Fa-f]/g, '').substring(0, 6);
    const hexWithHash = '#' + cleanHex;
    setCustomHex(hexWithHash);
    if (cleanHex.length === 6) {
      setAccentColor(hexWithHash);
    }
  };

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [credentials, setCredentials] = useState({
    fyers_user_id: "",
    fyers_pin: "",
    fyers_totp_key: ""
  });

  const [filters, setFilters] = useState({
    enable_squeeze_filter: false,
    enable_extension_filter: false,
    enable_cpr_filter: false,
    enable_aggression_filter: false
  });

  const [aiStatus, setAiStatus] = useState({
    is_trained: false,
    last_trained: "Never",
    accuracy: "0.00%"
  });
  const [isRetraining, setIsRetraining] = useState(false);

  useEffect(() => {
    const fetchCredentials = async () => {
      try {
        const res = await fetch('/api/settings');
        if (!res.ok) {
          console.error("Settings API returned error:", res.status);
          return;
        }
        
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
          const data = await res.json();
          setCredentials({
            fyers_user_id: data.fyers_user_id || "",
            fyers_pin: data.fyers_pin || "",
            fyers_totp_key: data.fyers_totp_key || ""
          });
          setFilters({
            enable_squeeze_filter: data.enable_squeeze_filter || false,
            enable_extension_filter: data.enable_extension_filter || false,
            enable_cpr_filter: data.enable_cpr_filter || false,
            enable_aggression_filter: data.enable_aggression_filter || false
          });
        } else {
          const text = await res.text();
          console.error("Expected JSON but got:", text.substring(0, 100));
        }

        const aiRes = await fetch('/api/ai/status');
        if (aiRes.ok) {
          const aiData = await aiRes.json();
          setAiStatus({
            is_trained: aiData.is_trained,
            last_trained: aiData.last_trained,
            accuracy: aiData.accuracy
          });
        }
      } catch (error) {
        console.error("Failed to fetch credentials:", error);
      }
    };
    fetchCredentials();
  }, []);

  const handleSaveCredentials = async () => {
    try {
      setErrorMessage("");
      setSuccessMessage("");
      
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });
      
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        const text = await res.text();
        console.error("Non-JSON response:", text);
        setErrorMessage("Server error! Backend might be down.");
        return;
      }

      const data = await res.json();
      
      if (!res.ok) {
        setErrorMessage(data.detail || data.message || "Unknown error");
        setTimeout(() => setErrorMessage(""), 5000);
        return;
      }
      
      if (data.status === "success" || data.message?.includes("successfully")) {
        setSuccessMessage("Credentials saved and verified successfully!");
        setTimeout(() => setSuccessMessage(""), 5000);
      } else {
        setErrorMessage(data.detail || data.message || "Unknown error");
        setTimeout(() => setErrorMessage(""), 5000);
      }
    } catch (error) {
      console.error("Error saving credentials:", error);
      setErrorMessage("Error saving credentials! Please check connection.");
    }
  };

  const handleStartBot = async () => {
    try {
      const res = await fetch('/api/bot/start', { method: 'POST' });
      const data = await res.json();
      if (data.status === "success") {
        alert("Bot started successfully!");
      } else {
        alert("Failed to start bot: " + data.message);
      }
    } catch (error) {
      console.error("Error starting bot:", error);
      alert("Error starting bot!");
    }
  };

  const handleFilterChange = async (key: string, value: boolean) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      });
    } catch (error) {
      console.error(`Error saving filter ${key}:`, error);
    }
  };

  const handleRetrainAI = async () => {
    setIsRetraining(true);
    try {
      const res = await fetch('/api/ai/retrain', { method: 'POST' });
      const data = await res.json();
      alert(data.message || "Retraining started.");
    } catch (error) {
      alert("Failed to trigger retraining.");
    }
    setTimeout(() => setIsRetraining(false), 3000);
  };

  const [notifications, setNotifications] = useState({
    email: true,
    telegram: true,
    whatsapp: false,
    signals: true
  });

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />

      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div>
            <h1 className="font-display font-bold text-2xl text-foreground">System Settings</h1>
            <p className="text-sm text-muted-foreground">Manage your account, notifications, and application preferences.</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Profile & Security */}
            <div className="lg:col-span-2 space-y-6">
              {/* Live Trading Control */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Live Trading Control</h3>
                  <Zap className="w-4 h-4 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Start or stop the live trading bot. Make sure your credentials are filled in `settings.json`.</p>
                <button 
                  onClick={handleStartBot}
                  className="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 w-fit"
                >
                  <Zap className="w-4 h-4" />
                  Start Live Bot
                </button>
              </div>

              {/* Broker Credentials */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Fyers Credentials</h3>
                  <Shield className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Client ID</label>
                    <input
                      type="text"
                      value={credentials.fyers_user_id || ""}
                      onChange={(e) => setCredentials({...credentials, fyers_user_id: e.target.value})}
                      className="input-field w-full"
                      placeholder="Enter Client ID"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">MPIN</label>
                    <input
                      type="password"
                      value={credentials.fyers_pin || ""}
                      onChange={(e) => setCredentials({...credentials, fyers_pin: e.target.value})}
                      className="input-field w-full"
                      placeholder="Enter 4-digit PIN"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">TOTP Secret Key</label>
                  <input
                    type="password"
                    value={credentials.fyers_totp_key || ""}
                    onChange={(e) => setCredentials({...credentials, fyers_totp_key: e.target.value})}
                    className="input-field w-full"
                    placeholder="Enter TOTP Secret Key"
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <div>
                    <button 
                      onClick={handleSaveCredentials}
                      className="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors"
                    >
                      Save Credentials
                    </button>
                  </div>
                  
                  {errorMessage && (
                    <p className="text-sm text-red-500 font-medium mt-1 flex items-center gap-1">
                      <span>⚠️</span> {errorMessage}
                    </p>
                  )}
                  
                  {successMessage && (
                    <p className="text-sm text-green-500 font-medium mt-1 flex items-center gap-1">
                      <span>✅</span> {successMessage}
                    </p>
                  )}
                </div>
              </div>

              {/* Profile Settings */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Account Profile</h3>
                  <User className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Full Name</label>
                    <input
                      type="text"
                      defaultValue="Institutional Trader"
                      className="input-field w-full"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Email Address</label>
                    <input
                      type="email"
                      defaultValue="trader@quantai.com"
                      className="input-field w-full"
                    />
                  </div>
                </div>

                <button className="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors w-fit mt-2">
                  Update Profile
                </button>
              </div>

              {/* Security */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Security & Password</h3>
                  <Lock className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>

                <div className="space-y-5">
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Current Password</label>
                    <input
                      type="password"
                      defaultValue="••••••••••••"
                      className="input-field w-full"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div>
                      <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">New Password</label>
                      <input
                        type="password"
                        className="input-field w-full"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Confirm New Password</label>
                      <input
                        type="password"
                        className="input-field w-full"
                      />
                    </div>
                  </div>
                </div>

                <button className="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors w-fit">
                  Change Password
                </button>
              </div>

              {/* Advanced Institutional Filters */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Advanced Institutional Filters</h3>
                  <Shield className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>
                <p className="text-xs text-muted-foreground">Select which institutional filters to apply to the live bot signals. These directly impact the live trading engine.</p>
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">Squeeze Filter</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Ensure recent consolidation</p>
                    </div>
                    <CustomSwitch 
                      checked={filters.enable_squeeze_filter} 
                      onChange={(checked) => handleFilterChange("enable_squeeze_filter", checked)} 
                      size="sm"
                    />
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">EMA Extension</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Avoid over-extended entries</p>
                    </div>
                    <CustomSwitch 
                      checked={filters.enable_extension_filter} 
                      onChange={(checked) => handleFilterChange("enable_extension_filter", checked)} 
                      size="sm"
                    />
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">CPR Rejection</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Reject signals near CPR resistance</p>
                    </div>
                    <CustomSwitch 
                      checked={filters.enable_cpr_filter} 
                      onChange={(checked) => handleFilterChange("enable_cpr_filter", checked)} 
                      size="sm"
                    />
                  </div>
                  
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">Candle Aggression</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Require strong close near High/Low</p>
                    </div>
                    <CustomSwitch 
                      checked={filters.enable_aggression_filter} 
                      onChange={(checked) => handleFilterChange("enable_aggression_filter", checked)} 
                      size="sm"
                    />
                  </div>
                </div>
              </div>

              {/* AI Model Management */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">AI Model Retraining</h3>
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-3 w-3">
                      {aiStatus.is_trained && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>}
                      <span className={`relative inline-flex rounded-full h-3 w-3 ${aiStatus.is_trained ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                    </span>
                  </div>
                </div>
                
                <p className="text-xs text-muted-foreground">The model automatically retrains daily at 11:00 PM. You can also manually trigger it.</p>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-background/50 border border-border/40 rounded-lg p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold mb-1">Last Trained</p>
                    <p className="text-sm font-semibold text-foreground">{aiStatus.last_trained}</p>
                  </div>
                  <div className="bg-background/50 border border-border/40 rounded-lg p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold mb-1">Accuracy</p>
                    <p className="text-sm font-semibold text-primary">{aiStatus.accuracy}</p>
                  </div>
                </div>

                <button 
                  onClick={handleRetrainAI} 
                  disabled={isRetraining}
                  className="w-full px-4 py-2 bg-primary/10 text-primary hover:bg-primary hover:text-white border border-primary/20 rounded-lg text-sm font-bold transition-all disabled:opacity-50 flex justify-center items-center gap-2"
                >
                  {isRetraining ? (
                    <>
                      <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                      Triggering Retrain...
                    </>
                  ) : "Trigger Manual Retrain"}
                </button>
              </div>
            </div>

            {/* Right Column: Preferences & Notifications */}
            <div className="space-y-6">
              {/* Notifications */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Notifications</h3>
                  <Bell className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">Email Alerts</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Daily summaries & critical alerts</p>
                    </div>
                    <CustomSwitch 
                      checked={notifications.email} 
                      onChange={(checked) => setNotifications({ ...notifications, email: checked })} 
                      size="sm"
                    />
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">Telegram Channel</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Real-time signal push</p>
                    </div>
                    <CustomSwitch 
                      checked={notifications.telegram} 
                      onChange={(checked) => setNotifications({ ...notifications, telegram: checked })} 
                      size="sm"
                    />
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-bold text-foreground">WhatsApp Bot</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Order execution pings</p>
                    </div>
                    <CustomSwitch 
                      checked={notifications.whatsapp} 
                      onChange={(checked) => setNotifications({ ...notifications, whatsapp: checked })} 
                      size="sm"
                    />
                  </div>
                </div>
              </div>

              {/* Preferences */}
              <div className="stat-card rounded-xl p-6 border border-border/20 space-y-5 shadow-lg group">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground tracking-tight">Preferences</h3>
                  <Globe className="w-5 h-5 text-primary opacity-50 group-hover:opacity-100 transition-opacity" />
                </div>

                <div className="space-y-5">
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">Default Timezone</label>
                    <select className="select-field w-full">
                      <option value="IST">Kolkata (IST) - GMT+5:30</option>
                      <option value="UTC">Coordinated Universal Time (UTC)</option>
                      <option value="EST">New York (EST) - GMT-5:00</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Theme Mode</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setTheme("dark")}
                        className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${theme === "dark" ? "bg-primary text-white" : "bg-muted/30 text-muted-foreground hover:bg-muted/50"
                          }`}
                      >
                        <Moon className="w-4 h-4" />
                        Dark
                      </button>
                      <button
                        onClick={() => setTheme("light")}
                        className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${theme === "light" ? "bg-primary text-white" : "bg-muted/30 text-muted-foreground hover:bg-muted/50"
                          }`}
                      >
                        <Sun className="w-4 h-4" />
                        Light
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Personalization Section */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Personalization</h3>
                  <Palette className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="space-y-4">
                  {/* Accent Color Picker - Advanced */}
                  <div>
                    <div className="flex justify-between items-center mb-2.5">
                      <label className="text-xs font-medium text-muted-foreground">Primary Accent Color</label>
                      <div className="flex items-center gap-2">
                        <button 
                          onClick={() => setAccentColor("#ff4d4d")}
                          className="text-[10px] font-bold text-primary flex items-center gap-1 hover:underline transition-all"
                          title="Restore factory default institutional red"
                        >
                          <RotateCcw className="w-2.5 h-2.5" />
                          RESTORE DEFAULT
                        </button>
                        <span className="text-[10px] font-mono text-muted-foreground bg-muted/30 px-2 py-0.5 rounded">
                          {accentColor.toUpperCase()}
                        </span>
                      </div>
                    </div>

                    {/* Preset Swatches */}
                    <div className="flex gap-2.5 mb-3">
                      {[
                        { name: "Institutional Red", color: "#ff4d4d" },
                        { name: "Classic Blue",      color: "#00d2ff" },
                        { name: "Quantum Purple",    color: "#a855f7" },
                        { name: "Gold Edition",      color: "#fbbf24" },
                        { name: "Emerald Green",     color: "#10b981" },
                        { name: "Hot Pink",          color: "#ec4899" },
                        { name: "Electric Indigo",   color: "#6366f1" },
                      ].map((preset) => (
                        <button
                          key={preset.color}
                          onClick={() => setAccentColor(preset.color)}
                          className={`w-7 h-7 rounded-full transition-all flex items-center justify-center shadow-md ${
                            accentColor === preset.color
                              ? "ring-2 ring-offset-2 ring-offset-background ring-white scale-125"
                              : "hover:scale-110 opacity-70 hover:opacity-100"
                          }`}
                          style={{ backgroundColor: preset.color }}
                          title={preset.name}
                        >
                          {accentColor === preset.color && <Check className="w-3.5 h-3.5 text-white drop-shadow" />}
                        </button>
                      ))}
                    </div>

                    {/* Manual Hex + Native Color Picker */}
                    <div className="flex items-stretch gap-2">
                      {/* Native Color Wheel */}
                      <div className="relative">
                        <div
                          className="w-10 h-10 rounded-lg border-2 border-border/50 overflow-hidden cursor-pointer shadow-inner"
                          style={{ backgroundColor: accentColor }}
                          title="Click to open color picker"
                        >
                          <input
                            type="color"
                            value={accentColor}
                            onChange={(e) => setAccentColor(e.target.value)}
                            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                          />
                        </div>
                      </div>

                      {/* Hex Input */}
                      <div className="flex-1 flex items-center bg-muted/30 border border-border/50 rounded-lg px-3 gap-2">
                        <span className="text-muted-foreground text-xs font-mono font-bold">#</span>
                        <input
                          type="text"
                          value={customHex.replace('#', '')}
                          onChange={(e) => handleHexInput(e.target.value)}
                          maxLength={8}
                          placeholder="ff4d4d"
                          className="flex-1 bg-transparent text-sm font-mono text-foreground focus:outline-none uppercase tracking-widest"
                        />
                      </div>

                      {/* Apply Button */}
                      <button
                        onClick={() => {
                          const cleanHex = customHex.replace(/[^0-9A-Fa-f]/g, '');
                          if (cleanHex.length === 6) {
                            setAccentColor('#' + cleanHex);
                          } else {
                            setCustomHex(accentColor);
                          }
                        }}
                        className="px-3 py-2 bg-primary text-white text-[10px] font-bold rounded-lg hover:opacity-90 transition-opacity uppercase tracking-wider"
                      >
                        Apply
                      </button>
                    </div>

                    {/* Live Preview Strip */}
                    <div className="mt-3 rounded-lg overflow-hidden border border-border/30">
                      <div className="h-2" style={{ background: `linear-gradient(to right, ${accentColor}22, ${accentColor})` }} />
                      <div className="p-2.5 bg-muted/20 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded-full" style={{ backgroundColor: accentColor }} />
                          <span className="text-[10px] font-bold text-foreground">Live Preview</span>
                        </div>
                        <div className="flex gap-1.5">
                          <div className="px-2 py-0.5 rounded text-[9px] font-bold text-white" style={{ backgroundColor: accentColor }}>BUTTON</div>
                          <div className="px-2 py-0.5 rounded text-[9px] font-bold border" style={{ color: accentColor, borderColor: accentColor }}>OUTLINE</div>
                          <div className="px-2 py-0.5 rounded text-[9px] font-bold" style={{ color: accentColor, backgroundColor: accentColor + '20' }}>GHOST</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Layout Density */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-2.5">Layout Density</label>
                    <div className="flex bg-muted/30 p-1 rounded-lg border border-border/50">
                      <button
                        onClick={() => setDensity("compact")}
                        className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-[10px] font-bold transition-all ${density === "compact" ? "bg-background shadow-sm text-primary" : "text-muted-foreground hover:text-foreground"}`}
                      >
                        <Layout className="w-3 h-3" />
                        INSTITUTIONAL
                      </button>
                      <button
                        onClick={() => setDensity("spacious")}
                        className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-[10px] font-bold transition-all ${density === "spacious" ? "bg-background shadow-sm text-primary" : "text-muted-foreground hover:text-foreground"}`}
                      >
                        <Globe className="w-3 h-3" />
                        SPACIOUS
                      </button>
                    </div>
                  </div>

                  {/* UI Effects */}
                  <div className="flex justify-between items-center pt-2">
                    <div>
                      <p className="text-sm font-bold text-foreground">Glassmorphism FX</p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">Premium blur and transparency effects</p>
                    </div>
                    <CustomSwitch 
                      checked={glassEnabled} 
                      onChange={(checked) => setGlassEnabled(checked)} 
                      size="sm"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
