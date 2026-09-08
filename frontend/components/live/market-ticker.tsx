"use client";
import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import type { FeedStatus } from '@/store/useLiveMarketStore';

interface TickerData {
    lp?: number;
    chp?: number;
    /** 'fyers' | 'broker' = authoritative. 'yfinance' = delayed. 'pending' = no price. */
    src?: string;
    ts?: number;
}

interface MarketTickerProps {
    isWsConnected: boolean;
    tickerData: Record<string, TickerData>;
    feed?: FeedStatus | null;
}

/** Sources the backend considers authoritative (mirrors TRADEABLE_SOURCES). */
const AUTHORITATIVE = new Set(['fyers', 'broker']);

/** How a single index quote should be rendered, given its provenance.
 *
 *  The point of this function: before 2026-09-09 this component rendered
 *  `tickerData.NIFTY?.lp ?? 0`, so a missing or fabricated price became a
 *  confident-looking "₹0.00" with a green up-arrow. A trader cannot act on a
 *  number they cannot trust, so an untrustworthy price is shown as such --
 *  never silently coerced into a plausible one. */
function quoteState(tick: TickerData | undefined) {
    if (!tick || typeof tick.lp !== 'number' || tick.lp <= 0) {
        return { kind: 'none' as const, label: 'NO FEED', title: 'No market data received for this index.' };
    }
    if (tick.src && !AUTHORITATIVE.has(tick.src)) {
        return {
            kind: 'delayed' as const,
            label: tick.src.toUpperCase(),
            title: `Delayed / non-tradeable quote from "${tick.src}". Shown for reference only — the trading engine ignores it.`,
        };
    }
    return { kind: 'live' as const, label: '', title: 'Live tick from the broker feed.' };
}

function Quote({ name, tick }: { name: string; tick: TickerData | undefined }) {
    const state = quoteState(tick);

    if (state.kind === 'none') {
        return (
            <div className="flex items-center gap-2 flex-shrink-0 group cursor-default" title={state.title}>
                <span className="text-muted-foreground">{name}</span>
                <span className="text-muted-foreground/60">—</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-muted/40 text-muted-foreground uppercase tracking-wider">
                    {state.label}
                </span>
            </div>
        );
    }

    const chp = tick?.chp ?? 0;
    const up = chp >= 0;
    // A delayed quote is deliberately rendered in a muted, non-directional
    // colour: green/red on a stale price reads as a live move that isn't one.
    const priceClass = state.kind === 'delayed'
        ? 'text-muted-foreground'
        : (up ? 'text-success' : 'text-destructive');
    const badgeClass = state.kind === 'delayed'
        ? 'bg-muted/40 text-muted-foreground'
        : (up ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive');

    return (
        <div className="flex items-center gap-2 flex-shrink-0 group cursor-default" title={state.title}>
            <span className="text-foreground group-hover:text-primary transition-colors">{name}</span>
            <span className={`transition-colors ${priceClass}`}>
                ₹{(tick!.lp as number).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {state.kind === 'delayed' ? (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-md uppercase tracking-wider ${badgeClass}`}>
                    {state.label} · DELAYED
                </span>
            ) : (
                <span className={`flex items-center text-[10px] px-1.5 py-0.5 rounded-md ${badgeClass}`}>
                    {up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                    {Math.abs(chp).toFixed(2)}%
                </span>
            )}
        </div>
    );
}

function MarketTickerComponent({ isWsConnected, tickerData, feed }: MarketTickerProps) {
    // The socket being up says nothing about whether real prices are flowing
    // through it — the 2026-08-12 zombie-feed incident was exactly that. Show
    // the backend's own feed verdict, not just the transport state.
    const feedDown = feed ? feed.status === 'down' : false;
    const feedDegraded = feed ? feed.status === 'degraded' : false;
    const healthy = isWsConnected && !feedDown && !feedDegraded;

    let dotClass = 'bg-destructive';
    let dotLabel = 'DATA FEED OFFLINE';
    if (healthy) {
        dotClass = 'bg-success';
        dotLabel = 'LIVE DATA FEED';
    } else if (isWsConnected && feedDegraded) {
        dotClass = 'bg-amber-500';
        dotLabel = `DEGRADED — no tradeable prices${feed?.sources?.length ? ` (source: ${feed.sources.join(', ')})` : ''}`;
    } else if (isWsConnected && feedDown) {
        dotClass = 'bg-destructive';
        dotLabel = 'NO MARKET DATA';
    }

    return (
        <div className="flex-1 flex items-center px-4 py-2 bg-muted/20 border border-border/50 rounded-xl overflow-hidden relative">
            <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none"></div>
            <div className="flex items-center gap-2 z-20 mr-4 border-r border-border/50 pr-4">
                {/* Feed health indicator */}
                <div className="relative flex items-center justify-center w-3 h-3 group">
                    {healthy ? (
                        <>
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                        </>
                    ) : (
                        <span className={`relative inline-flex rounded-full h-2 w-2 ${dotClass}`}></span>
                    )}
                    <div className="absolute -top-8 bg-black/80 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                        {dotLabel}
                    </div>
                </div>
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider hidden sm:inline-block">Indices</span>
            </div>

            {/* Marquee Content */}
            <div className="flex-1 overflow-hidden">
                <div className="flex items-center gap-8 animate-marquee whitespace-nowrap text-sm font-mono font-bold">
                    <Quote name="NIFTY" tick={tickerData.NIFTY} />
                    <Quote name="SENSEX" tick={tickerData.SENSEX} />
                    <Quote name="BANKNIFTY" tick={tickerData.BANKNIFTY} />
                </div>
            </div>
            <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none"></div>
        </div>
    );
}

export const MarketTicker = React.memo(MarketTickerComponent);
