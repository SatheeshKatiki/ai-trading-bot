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
  Lock,
  Smartphone,
  Check,
  Zap
} from "lucide-react";

export default function Settings() {
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") || "dark";
    setTheme(savedTheme);
    if (savedTheme === "light") {
      document.documentElement.classList.add("light");
    } else {
      document.documentElement.classList.remove("light");
    }
  }, []);

  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme);
    localStorage.setItem("theme", newTheme);
    if (newTheme === "light") {
      document.documentElement.classList.add("light");
    } else {
      document.documentElement.classList.remove("light");
    }
  };

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [credentials, setCredentials] = useState({
    fyers_user_id: "",
    fyers_pin: "",
    fyers_totp_key: ""
  });

  useEffect(() => {
    const fetchCredentials = async () => {
      try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        setCredentials({
          fyers_user_id: data.fyers_user_id || "",
          fyers_pin: data.fyers_pin || "",
          fyers_totp_key: data.fyers_totp_key || ""
        });
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
                  className="px-4 py-2 bg-success text-white rounded-lg text-sm font-medium hover:bg-success/90 transition-colors flex items-center gap-2"
                >
                  <Zap className="w-4 h-4" />
                  Start Live Bot
                </button>
              </div>

              {/* Broker Credentials */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Fyers Credentials</h3>
                  <Shield className="w-4 h-4 text-muted-foreground" />
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Client ID</label>
                    <input
                      type="text"
                      value={credentials.fyers_user_id || ""}
                      onChange={(e) => setCredentials({...credentials, fyers_user_id: e.target.value})}
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      placeholder="Enter Client ID"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">MPIN</label>
                    <input
                      type="password"
                      value={credentials.fyers_pin || ""}
                      onChange={(e) => setCredentials({...credentials, fyers_pin: e.target.value})}
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      placeholder="Enter 4-digit PIN"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">TOTP Secret Key</label>
                  <input
                    type="text"
                    value={credentials.fyers_totp_key || ""}
                    onChange={(e) => setCredentials({...credentials, fyers_totp_key: e.target.value})}
                    className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
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
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Account Profile</h3>
                  <User className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Full Name</label>
                    <input
                      type="text"
                      defaultValue="Institutional Trader"
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Email Address</label>
                    <input
                      type="email"
                      defaultValue="trader@quantai.com"
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                    />
                  </div>
                </div>

                <button className="px-4 py-2 bg-[#ff4d4d] text-white hover:bg-[#ff4d4d]/90 rounded-lg text-sm font-medium transition-colors">
                  Update Profile
                </button>
              </div>

              {/* Security */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Security & Password</h3>
                  <Lock className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Current Password</label>
                    <input
                      type="password"
                      defaultValue="••••••••••••"
                      className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1.5">New Password</label>
                      <input
                        type="password"
                        className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1.5">Confirm New Password</label>
                      <input
                        type="password"
                        className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      />
                    </div>
                  </div>
                </div>

                <button className="px-4 py-2 bg-muted hover:bg-muted/70 text-foreground rounded-lg text-sm font-medium transition-colors border border-border/50">
                  Change Password
                </button>
              </div>
            </div>

            {/* Right Column: Preferences & Notifications */}
            <div className="space-y-6">
              {/* Notifications */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Notifications</h3>
                  <Bell className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-medium text-foreground">Email Alerts</p>
                      <p className="text-xs text-muted-foreground">Daily summaries & critical alerts</p>
                    </div>
                    <button
                      onClick={() => setNotifications({ ...notifications, email: !notifications.email })}
                      className={`w-10 h-6 rounded-full p-1 transition-colors ${notifications.email ? "bg-primary" : "bg-muted"}`}
                    >
                      <div className={`w-4 h-4 rounded-full bg-white transition-transform ${notifications.email ? "translate-x-4" : ""}`}></div>
                    </button>
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-medium text-foreground">Telegram Channel</p>
                      <p className="text-xs text-muted-foreground">Real-time signal push</p>
                    </div>
                    <button
                      onClick={() => setNotifications({ ...notifications, telegram: !notifications.telegram })}
                      className={`w-10 h-6 rounded-full p-1 transition-colors ${notifications.telegram ? "bg-primary" : "bg-muted"}`}
                    >
                      <div className={`w-4 h-4 rounded-full bg-white transition-transform ${notifications.telegram ? "translate-x-4" : ""}`}></div>
                    </button>
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm font-medium text-foreground">WhatsApp Bot</p>
                      <p className="text-xs text-muted-foreground">Order execution pings</p>
                    </div>
                    <button
                      onClick={() => setNotifications({ ...notifications, whatsapp: !notifications.whatsapp })}
                      className={`w-10 h-6 rounded-full p-1 transition-colors ${notifications.whatsapp ? "bg-primary" : "bg-muted"}`}
                    >
                      <div className={`w-4 h-4 rounded-full bg-white transition-transform ${notifications.whatsapp ? "translate-x-4" : ""}`}></div>
                    </button>
                  </div>
                </div>
              </div>

              {/* Preferences */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">Preferences</h3>
                  <Globe className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Default Timezone</label>
                    <select className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent">
                      <option value="IST">Kolkata (IST) - GMT+5:30</option>
                      <option value="UTC">Coordinated Universal Time (UTC)</option>
                      <option value="EST">New York (EST) - GMT-5:00</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Theme Mode</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => handleThemeChange("dark")}
                        className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${theme === "dark" ? "bg-[#ff4d4d] text-white" : "bg-muted/30 text-muted-foreground hover:bg-muted/50"
                          }`}
                      >
                        <Moon className="w-4 h-4" />
                        Dark
                      </button>
                      <button
                        onClick={() => handleThemeChange("light")}
                        className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${theme === "light" ? "bg-[#ff4d4d] text-white" : "bg-muted/30 text-muted-foreground hover:bg-muted/50"
                          }`}
                      >
                        <Sun className="w-4 h-4" />
                        Light
                      </button>
                    </div>
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
