"use client";

import { useState, useEffect } from "react";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

export default function LiveTicker() {
  const [tickerData, setTickerData] = useState<any>({
    "NIFTY": { lp: 23820.35, chp: -1.49, up: false },
    "BANKNIFTY": { lp: 51000.00, chp: 0.08, up: true },
    "SENSEX": { lp: 76015.28, chp: -1.70, up: false },
    "RELIANCE": { lp: 2950.00, chp: 0.12, up: true },
    "TCS": { lp: 3950.00, chp: -0.45, up: false },
  });
  const [lastPrices, setLastPrices] = useState<any>({});
  const [flashes, setFlashes] = useState<any>({});

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimer: NodeJS.Timeout;

    const connect = () => {
      const wsUrl = `ws://${window.location.hostname}:8000/ws/live`;
      ws = new WebSocket(wsUrl);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        setLastPrices((prev: any) => {
          const next = { ...prev };
          const newFlashes: any = {};
          
          Object.keys(data).forEach(key => {
            if (data[key] !== null && typeof data[key] === 'object' && data[key].lp) {
              if (prev[key] && data[key].lp !== prev[key]) {
                newFlashes[key] = data[key].lp > prev[key] ? "up" : "down";
              }
              next[key] = data[key].lp;
            }
          });
          
          if (Object.keys(newFlashes).length > 0) {
            setFlashes(newFlashes);
            setTimeout(() => setFlashes({}), 800);
          }
          return next;
        });

        setTickerData((prev: any) => ({
          ...prev,
          ...Object.fromEntries(
            Object.entries(data).filter(([_, v]) => v !== null)
          ),
          "NIFTY": data.NIFTY ?? prev.NIFTY,
          "BANKNIFTY": data.BANKNIFTY ?? prev.BANKNIFTY,
          "SENSEX": data.SENSEX ?? prev.SENSEX
        }));
      };

      ws.onerror = (error) => {
        console.warn('WebSocket connection error.', error);
      };

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  return (
    <div className="bg-card/50 backdrop-blur-md border border-border/50 rounded-xl overflow-hidden h-10 flex items-center shadow-inner group">
      <div className="bg-primary/20 text-primary px-3 h-full flex items-center text-xs font-extrabold uppercase tracking-tighter border-r border-border/50 z-10">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></div>
          Live Markets
        </div>
      </div>
      <div className="flex-1 overflow-hidden relative">
        <div className="flex whitespace-nowrap animate-marquee-slower gap-12 items-center px-4 hover:pause">
          {Object.keys(tickerData).filter(k => k !== "trades" && k !== "signalsData").map((symbol, i) => {
            const data = tickerData[symbol];
            if (!data || typeof data !== 'object') return null;
            const isUp = data.chp >= 0;
            const flashClass = flashes[symbol] === "up" ? "bg-success/20 animate-pulse" : flashes[symbol] === "down" ? "bg-destructive/20 animate-pulse" : "";
            
            return (
              <div key={i} className={`flex items-center gap-3 px-2 py-1 rounded-md transition-all duration-300 ${flashClass}`}>
                <span className="text-xs font-bold text-foreground/90 tracking-tight">{symbol}</span>
                <span className="text-xs font-mono font-medium text-foreground">
                  {data.lp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
                <div className={`flex items-center text-[10px] font-bold ${isUp ? "text-success" : "text-destructive"}`}>
                  {isUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}
                  {Math.abs(data.chp).toFixed(2)}%
                </div>
              </div>
            );
          })}
          {/* Duplicate for seamless loop */}
          {Object.keys(tickerData).filter(k => k !== "trades" && k !== "signalsData").map((symbol, i) => {
            const data = tickerData[symbol];
            if (!data || typeof data !== 'object') return null;
            const isUp = data.chp >= 0;
            return (
              <div key={`dup-${i}`} className="flex items-center gap-3 px-2 py-1">
                <span className="text-xs font-bold text-foreground/90 tracking-tight">{symbol}</span>
                <span className="text-xs font-mono font-medium text-foreground">
                  {data.lp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
                <div className={`flex items-center text-[10px] font-bold ${isUp ? "text-success" : "text-destructive"}`}>
                  {isUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}
                  {Math.abs(data.chp).toFixed(2)}%
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
