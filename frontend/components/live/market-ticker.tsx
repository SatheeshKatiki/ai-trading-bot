import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface TickerData {
    lp?: number;
    chp: number;
}

interface MarketTickerProps {
    isWsConnected: boolean;
    tickerData: Record<string, TickerData>;
}

export function MarketTicker({ isWsConnected, tickerData }: MarketTickerProps) {
    return (
        <div className="flex-1 flex items-center px-4 py-2 bg-muted/20 border border-border/50 rounded-xl overflow-hidden relative">
            <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none"></div>
            <div className="flex items-center gap-2 z-20 mr-4 border-r border-border/50 pr-4">
                {/* WS Connection Indicator */}
                <div className="relative flex items-center justify-center w-3 h-3 group">
                    {isWsConnected ? (
                        <>
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                        </>
                    ) : (
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-destructive"></span>
                    )}
                    {/* Tooltip on hover */}
                    <div className="absolute -top-8 bg-black/80 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                        {isWsConnected ? "LIVE DATA FEED" : "DATA FEED OFFLINE"}
                    </div>
                </div>
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider hidden sm:inline-block">Indices</span>
            </div>

            {/* Marquee Content */}
            <div className="flex-1 overflow-hidden">
                <div className="flex items-center gap-8 animate-marquee whitespace-nowrap text-sm font-mono font-bold">
                    {/* NIFTY */}
                    <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                        <span className="text-foreground group-hover:text-primary transition-colors">NIFTY</span>
                        <span className={`transition-colors ${(tickerData.NIFTY?.chp ?? 0) >= 0 ? 'text-success ' : 'text-destructive '}`}>
                            ₹{(tickerData.NIFTY?.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                        <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${(tickerData.NIFTY?.chp ?? 0) >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                            {(tickerData.NIFTY?.chp ?? 0) >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                            {Math.abs(tickerData.NIFTY?.chp ?? 0).toFixed(2)}%
                        </span>
                    </div>

                    {/* SENSEX */}
                    <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                        <span className="text-foreground group-hover:text-primary transition-colors">SENSEX</span>
                        <span className={`transition-colors ${(tickerData.SENSEX?.chp ?? 0) >= 0 ? 'text-success ' : 'text-destructive '}`}>
                            ₹{(tickerData.SENSEX?.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                        <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${(tickerData.SENSEX?.chp ?? 0) >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                            {(tickerData.SENSEX?.chp ?? 0) >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                            {Math.abs(tickerData.SENSEX?.chp ?? 0).toFixed(2)}%
                        </span>
                    </div>

                    {/* BANKNIFTY */}
                    <div className="flex items-center gap-2 flex-shrink-0 group cursor-default">
                        <span className="text-foreground group-hover:text-primary transition-colors">BANKNIFTY</span>
                        <span className={`transition-colors ${(tickerData.BANKNIFTY?.chp ?? 0) >= 0 ? 'text-success ' : 'text-destructive '}`}>
                            ₹{(tickerData.BANKNIFTY?.lp ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                        <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${(tickerData.BANKNIFTY?.chp ?? 0) >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                            {(tickerData.BANKNIFTY?.chp ?? 0) >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                            {Math.abs(tickerData.BANKNIFTY?.chp ?? 0).toFixed(2)}%
                        </span>
                    </div>
                </div>
            </div>
            <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none"></div>
        </div>
    );
}
