"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { 
  BarChart2, 
  Play, 
  History, 
  Brain, 
  BookOpen, 
  PieChart, 
  Settings, 
  ShieldCheck, 
  Plug,
  Sliders,
  LineChart,
  FileText,
  Info
} from "lucide-react";
import { clsx } from "clsx";

const menuItems = [
  { icon: BarChart2, label: "Dashboard", href: "/" },
  { icon: Play, label: "Live Trading", href: "/live" },
  { icon: History, label: "Backtesting", href: "/backtest" },
  { icon: Brain, label: "AI Signals", href: "/signals" },
  { icon: Sliders, label: "Strategy Settings", href: "/strategy" },
  { icon: BookOpen, label: "Trading Journal", href: "/journal" },
  { icon: LineChart, label: "Options Desk", href: "/options" },
  { icon: PieChart, label: "Analytics", href: "/analytics" },
  { icon: Plug, label: "Broker Settings", href: "/broker" },
  { icon: ShieldCheck, label: "Risk Management", href: "/risk" },
  { icon: Settings, label: "Settings", href: "/settings" },
  { icon: FileText, label: "Documentation", href: "/docs" },
  { icon: Info, label: "About", href: "/about" },
];

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, x: -10 },
  show: { opacity: 1, x: 0 }
};

export default function Sidebar() {
  const pathname = usePathname();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          const data = await res.json();
          if (data && data.status === "ok") {
            setIsConnected(true);
          } else {
            setIsConnected(false);
          }
        } else {
          setIsConnected(false);
        }
      } catch {
        setIsConnected(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000); // Check every 5 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-64 h-full bg-card/80 backdrop-blur-xl border-r border-border/50 flex flex-col shadow-2xl relative z-20">
      <div className="px-2 py-8 flex items-center justify-center border-b border-border/50">
        <div className="w-full flex items-center justify-center relative z-10">
          <Image 
            src="/mana-logo-v2.png" 
            alt="Mana AI Logo" 
            width={320} 
            height={150} 
            className="object-contain mix-blend-screen" 
            priority 
          />
        </div>
      </div>

      <motion.nav 
        className="flex-1 p-4 flex flex-col gap-1.5 overflow-y-auto overflow-x-hidden"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {menuItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <motion.div key={item.href} variants={itemVariants}>
              <Link
                href={item.href}
                className={clsx(
                  "group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-300 outline-none",
                  isActive 
                    ? "text-primary font-bold" 
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground hover:translate-x-1"
                )}
              >
                {/* Active Indicator Glow */}
                {isActive && (
                  <motion.div 
                    layoutId="active-nav-bg"
                    className="absolute inset-0 bg-primary/10 rounded-lg border border-primary/20 shadow-[inset_0_0_12px_rgba(59,130,246,0.1)]"
                    initial={false}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
                {/* Active Left Accent Line */}
                {isActive && (
                  <motion.div 
                    layoutId="active-nav-line"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-2/3 bg-primary rounded-r-full shadow-[0_0_8px_var(--primary)]"
                  />
                )}
                <div className="relative z-10 flex items-center gap-3 w-full">
                  <item.icon className={clsx(
                    "w-5 h-5 transition-transform duration-300",
                    isActive ? "text-primary drop-shadow-[0_0_8px_var(--primary)]" : "group-hover:rotate-6 group-hover:scale-110 group-hover:text-foreground"
                  )} />
                  {item.label}
                </div>
              </Link>
            </motion.div>
          );
        })}
      </motion.nav>

      <div className="p-4 border-t border-border/50 flex flex-col gap-3">
        <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border/50 shadow-inner group cursor-default">
          <div className="flex items-center gap-2">
            <div className="relative flex h-2.5 w-2.5">
              {isConnected && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
              )}
              <span className={clsx(
                "relative inline-flex rounded-full h-2.5 w-2.5 transition-colors duration-300",
                isConnected ? "bg-success shadow-[0_0_8px_var(--success)]" : "bg-destructive shadow-[0_0_8px_var(--destructive)]"
              )}></span>
            </div>
            <span className="text-xs font-bold text-foreground tracking-wide">Broker: Fyers</span>
          </div>
          <span className={clsx(
            "text-[10px] uppercase font-bold tracking-wider",
            isConnected ? "text-success" : "text-destructive"
          )}>
            {isConnected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
        
        <div className="text-center">
          <span className="text-[10px] text-muted-foreground/60 font-mono tracking-widest">v2.0 ULTRA</span>
        </div>
      </div>
    </div>
  );
}
