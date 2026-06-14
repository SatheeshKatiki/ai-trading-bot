"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { useState, useEffect } from "react";
import { 
  Plug, 
  Key, 
  Shield, 
  Check, 
  X, 
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  Lock,
  Eye,
  EyeOff
} from "lucide-react";

const brokers = [
  { id: "fyers", name: "Fyers", status: "Connected" },
  { id: "zerodha", name: "Zerodha Kite", status: "Disconnected" },
  { id: "angel", name: "Angel One", status: "Disconnected" },
];

export default function BrokerSettings() {
  const [selectedBroker, setSelectedBroker] = useState("fyers");
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<"success" | "error" | null>(null);
  
  // States for requested features
  const [showClientId, setShowClientId] = useState(false);
  
  const [clientId, setClientId] = useState("FY78492-PRO");
  const [secretKey, setSecretKey] = useState("supersecretkey12345");
  
  const [isSaved, setIsSaved] = useState(false);
  const [isModified, setIsModified] = useState(false);
  
  // New state for showing the success message only after an active click
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [realBalance, setRealBalance] = useState<number | null>(null);

  // Persist state across refreshes safely in Next.js
  useEffect(() => {
    setIsMounted(true);
    const savedState = localStorage.getItem("broker_is_saved");
    if (savedState === "true") {
      setIsSaved(true);
    }
  }, []);

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    setRealBalance(null);
    try {
      const response = await fetch("http://127.0.0.1:8000/api/test_connection");
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setTestResult("success");
        setRealBalance(data.balance);
      } else {
        setTestResult("error");
      }
    } catch (error) {
      console.error("Test connection failed:", error);
      setTestResult("error");
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = () => {
    setIsSaved(true);
    setIsModified(false);
    setShowSuccessMessage(true); // Only show on active user click!
    localStorage.setItem("broker_is_saved", "true");
  };

  const handleInputChange = (type: "client" | "secret", value: string) => {
    setIsModified(true);
    setIsSaved(false); // Reset saved state on modification
    setShowSuccessMessage(false); // Hide message when editing
    localStorage.setItem("broker_is_saved", "false");
    if (type === "client") setClientId(value);
    if (type === "secret") setSecretKey(value);
  };

  const handleBrokerLogin = async () => {
    try {
      const res = await fetch('/api/broker-login'); // GET method we added
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          window.open(data.url, '_blank');
        } else {
          alert("Failed to get login URL");
        }
      } else {
        alert("Failed to connect to backend");
      }
    } catch (error) {
      console.error("Failed to start broker login:", error);
      alert("Error starting login");
    }
  };

  // High standard dynamic instructions based on selected broker
  const getInstructions = () => {
    switch (selectedBroker) {
      case "fyers":
        return [
          "Log in to the Fyers API Dashboard (api.fyers.in).",
          "Create a new app and configure your App Name and Description.",
          "Set the Redirect URL to your application's authorized callback listener.",
          "Copy the generated App ID and Secret Key into the fields on the left."
        ];
      case "zerodha":
        return [
          "Log in to the Kite Connect Developer Portal (kite.trade).",
          "Create a new application (requires an active developer subscription).",
          "Specify your Redirect URL and target app parameters.",
          "Copy the generated API Key and API Secret into the fields on the left."
        ];
      case "angel":
        return [
          "Log in to the Angel One SmartAPI Portal (smartapi.angelbroking.com).",
          "Create a new app to generate your API Key and Client ID.",
          "Enable TOTP (Time-Based One-Time Password) in your Angel One mobile app settings.",
          "Use the generated TOTP code along with your credentials to connect."
        ];
      default:
        return [
          "Go to your broker's developer portal and create a new app.",
          "Set the redirect URL to your application's callback path.",
          "Copy the Client ID and Secret Key and paste them here."
        ];
    }
  };

  // Dynamic documentation URLs based on selected broker
  const getDocUrl = () => {
    switch (selectedBroker) {
      case "fyers":
        return "https://api-connect-docs.fyers.in/docs/"; // Updated URL
      case "zerodha":
        return "https://kite.trade/docs/connect/v3/";
      case "angel":
        return "https://smartapi.angelbroking.com/docs";
      default:
        return "#";
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div>
            <h1 className="font-display font-bold text-2xl text-foreground">Broker Configuration</h1>
            <p className="text-sm text-muted-foreground">Manage your broker API connections and credentials securely.</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Broker Selection & Form */}
            <div className="lg:col-span-2 space-y-6">
              {/* Selector */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <h3 className="font-display font-bold text-lg text-foreground">Select Active Broker</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {brokers.map((broker) => (
                    <button 
                      key={broker.id}
                      onClick={() => setSelectedBroker(broker.id)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all duration-200 text-left w-full block focus:outline-none focus:ring-1 focus:ring-primary ${
                        selectedBroker === broker.id 
                          ? "bg-primary/10 border-primary" 
                          : "bg-muted/30 border-border/50 hover:bg-muted/50"
                      }`}
                    >
                      <div className="flex justify-between items-center mb-2">
                        <span className="font-display font-bold text-foreground">{broker.name}</span>
                        {broker.status === "Connected" && (
                          <div className="w-2 h-2 bg-success rounded-full"></div>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{broker.status}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Form */}
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-display font-bold text-lg text-foreground">API Credentials</h3>
                  <div className="flex items-center gap-1.5 text-xs text-success font-medium">
                    <Shield className="w-3.5 h-3.5" />
                    Encrypted Storage
                  </div>
                </div>

                <div className="space-y-4">
                  {/* Client ID Field with Toggle */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Client ID / App Key</label>
                    <div className="relative">
                      <Plug className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                      <input
                        type={showClientId ? "text" : "password"}
                        value={clientId}
                        onChange={(e) => handleInputChange("client", e.target.value)}
                        className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-10 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      />
                      <button 
                        type="button"
                        onClick={() => setShowClientId(!showClientId)}
                        className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {showClientId ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Secret Key Field: Visible while entering, hidden after saving */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Secret Key</label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
                      <input
                        type={isSaved && !isModified ? "password" : "text"}
                        value={secretKey}
                        onChange={(e) => handleInputChange("secret", e.target.value)}
                        className="w-full bg-muted/30 border border-border/50 rounded-lg pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      />
                    </div>
                  </div>

                  {selectedBroker === "angel" && (
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1.5">TOTP Token</label>
                      <input
                        type="text"
                        placeholder="Enter TOTP Token"
                        className="w-full bg-muted/30 border border-border/50 rounded-lg px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
                      />
                    </div>
                  )}

                  <div className="flex flex-col md:flex-row gap-3 pt-2">
                    <button 
                      onClick={handleBrokerLogin}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm font-medium transition-colors"
                    >
                      <Shield className="w-4 h-4" />
                      Login to Fyers
                    </button>

                    <button 
                      onClick={handleTestConnection}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-muted/50 hover:bg-muted/70 border border-border/50 rounded-lg text-sm font-medium transition-colors"
                    >
                      {isTesting ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Plug className="w-4 h-4" />
                      )}
                      {isTesting ? "Testing..." : "Test Connection"}
                    </button>
                    
                    {/* Always visible but conditionally disabled Save button */}
                    <button 
                      onClick={handleSave}
                      disabled={!isMounted || (isSaved && !isModified)}
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                        !isMounted || (isSaved && !isModified)
                          ? "bg-muted/50 text-muted-foreground cursor-not-allowed" 
                          : "bg-primary text-primary-foreground hover:bg-primary/90"
                      }`}
                    >
                      <Shield className="w-4 h-4" />
                      Save & Activate
                    </button>
                  </div>

                  {showSuccessMessage && (
                    <div className="p-3 rounded-lg bg-success/10 border border-success/20 flex items-center gap-2 text-[#4ade80] text-sm font-medium">
                      <Check className="w-4 h-4" />
                      Configuration saved successfully!
                    </div>
                  )}

                  {testResult === "success" && (
                    <div className="p-3 rounded-lg bg-success/10 border border-success/20 flex items-center gap-2 text-[#4ade80] text-sm font-medium">
                      <Check className="w-4 h-4" />
                      Connection successful! Fetched balance: ₹{realBalance !== null ? realBalance.toLocaleString() : "0.00"}
                    </div>
                  )}

                  {testResult === "error" && (
                    <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-2 text-[#ef4444] text-sm font-medium">
                      <X className="w-4 h-4" />
                      Connection failed! Please check credentials or log in via terminal.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right Column: Dynamic Instructions */}
            <div className="space-y-6">
              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-4">
                <h3 className="font-display font-bold text-lg text-foreground">Setup Instructions</h3>
                
                <div className="space-y-4 text-sm text-muted-foreground">
                  {getInstructions().map((instruction, index) => (
                    <div key={index} className="flex gap-3">
                      <div className="w-6 h-6 rounded-full bg-muted/50 flex items-center justify-center text-xs font-bold text-foreground shrink-0 mt-0.5">
                        {index + 1}
                      </div>
                      <p>{instruction}</p>
                    </div>
                  ))}
                </div>

                <div className="pt-2">
                  <a 
                    href={getDocUrl()} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                  >
                    Read full {brokers.find(b => b.id === selectedBroker)?.name} documentation
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>

              <div className="glass-card rounded-xl p-6 border border-border/20 space-y-2 bg-warning/5 border-warning/10">
                <div className="flex items-center gap-2 text-warning font-medium">
                  <AlertTriangle className="w-4 h-4" />
                  <h4 className="text-sm">Risk Warning</h4>
                </div>
                <p className="text-xs text-muted-foreground">
                  Never share your API keys or secret keys with anyone. QuantAI encrypts these keys locally on your machine.
                </p>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
