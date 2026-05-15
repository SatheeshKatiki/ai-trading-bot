"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { 
  BarChart2, 
  Play, 
  History, 
  Brain, 
  BookOpen, 
  PieChart, 
  Settings, 
  ShieldCheck, 
  Power,
  TrendingUp,
  Plug,
  Sliders
} from "lucide-react";
import { clsx } from "clsx";

const menuItems = [
  { icon: BarChart2, label: "Dashboard", href: "/" },
  { icon: Play, label: "Live Trading", href: "/live" },
  { icon: History, label: "Backtesting", href: "/backtest" },
  { icon: Brain, label: "AI Signals", href: "/signals" },
  { icon: Sliders, label: "Strategy Settings", href: "/strategy" },
  { icon: BookOpen, label: "Trading Journal", href: "/journal" },
  { icon: PieChart, label: "Analytics", href: "/analytics" },
  { icon: Plug, label: "Broker Settings", href: "/broker" },
  { icon: ShieldCheck, label: "Risk Management", href: "/risk" },
  { icon: Settings, label: "Settings", href: "/settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/health');
        const data = await res.json();
        if (data && data.status === "ok") {
          setIsConnected(true);
        } else {
          setIsConnected(false);
        }
      } catch (error) {
        setIsConnected(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000); // Check every 5 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-64 h-full bg-card/50 backdrop-blur-xl border-r border-border/50 flex flex-col">
      <div className="p-6 flex items-center gap-3 border-b border-border/50">
        <div className="w-8 h-8 rounded-lg bg-[#ff4d4d] flex items-center justify-center">
          <TrendingUp className="w-5 h-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="font-display font-bold text-lg text-foreground">QuantAI</h1>
          <p className="text-xs text-muted-foreground">Institutional Terminal</p>
        </div>
      </div>

      <nav className="flex-1 p-4 flex flex-col gap-1">
        {menuItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                isActive 
                  ? "bg-[#ff4d4d]/10 text-[#ff4d4d]" 
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-border/50 flex flex-col gap-2">
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-success" : "bg-destructive"}`}></div>
            <span className="text-xs font-medium text-foreground">Broker: Fyers</span>
          </div>
          <span className="text-xs text-muted-foreground">{isConnected ? "Connected" : "Disconnected"}</span>
        </div>
        
      </div>
    </div>
  );
}
