"use client";

import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import { toast } from 'sonner';
import { ExecutionFeed } from '@/components/live/execution-feed';
import { MetricsBar } from '@/components/live/metrics-bar';
import { TradeActionPanel } from '@/components/live/trade-action-panel';
import { MergedAiSignal } from '@/components/live/merged-ai-signal';
import { BtstPredictor } from '@/components/btst-predictor';
import { MarketTicker } from '@/components/live/market-ticker';
import { OptionsDesk } from '@/components/options-desk';
import { LivePositions } from '@/components/live/live-positions';
import { useLiveMarketStore } from '@/store/useLiveMarketStore';
import { useLiveSettingsStore } from '@/store/useLiveSettingsStore';
import { NumberInput } from "@/components/number-input";
import NewsTicker from "@/components/news-ticker";
import { ErrorBoundary } from "@/components/error-boundary";
import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
    TrendingUp,
    TrendingDown,
    Clock,
    Zap,
    Shield,
    Target,
    ArrowUpRight,
    ArrowDownRight,
    RefreshCw,
    Layers,
    Globe,
    Briefcase,
    ChevronDown,
    Star,
    Brain,
    Package,
    Maximize2,
    Minimize2,
    Activity,
    Play,
    Square,
    Settings,
    BarChart2,
    CheckCircle2,
    Fingerprint,
    Database,
    Sparkles,
    AlertCircle,
    Bot,
    User
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

declare global {
    interface Window {
        // TradingView is a third-party browser global injected via script tag — must stay as any
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        TradingView: any;
    }
}

// --- Type Definitions ---
interface Trade {
    id?: string | number;
    symbol: string;
    side: 'BUY' | 'SELL';
    price: number;
    time: string;
    status?: string;
    qty?: number;
}

interface Notification {
    id: number;
    message: string;
    type: 'success' | 'danger' | 'warning' | 'info';
}

import dynamic from "next/dynamic";

// Dynamic imports for charts to prevent SSR hydration errors
const NativeChart = dynamic(() => import("@/components/native-chart"), { ssr: false });
const AdvancedChart = dynamic(() => import("@/components/advanced-chart"), { ssr: false });

function formatTradeDisplay(symbol: string, price: number, side: string, qty?: number) {
    // Parse options symbol like "NSE:NIFTY26DEC2424000CE"
    const match = symbol.match(/^(NSE|BSE):([A-Z0-9]+?)(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$/i);
    if (match) {
        const [_, exchange, inst, expiry, strike, optType] = match;
        const instName = inst.toUpperCase().startsWith('NIFTY') ? (inst.toUpperCase() === 'NIFTY' ? 'NIFTY50' : inst.toUpperCase()) : inst.toUpperCase();
        const exchName = exchange.toUpperCase() === 'NSE' ? 'NSE' : exchange.toUpperCase();

        // lot calculation
        // Since LOT_SIZES might not be hoisted, we can just safely search it manually or use the robust method
        const baseInst = inst.toUpperCase();
        let baseQty = 1;
        for (const [key, value] of Object.entries(LOT_SIZES)) {
            if (baseInst.includes(key)) {
                baseQty = value;
                break;
            }
        }
        const lotQty = qty ? Math.round(qty / baseQty) : 1;

        // Format: NSE: NIFTY50 26DEC24 ATM 24000 120 CE BUY (Lot Qty: xx)
        return `${exchName}: ${instName} ${expiry} ATM ${strike} ${price} ${optType} ${side} (Lot Qty: ${lotQty})`;
    }
    return `${symbol}`;
}

// Helper to check if Indian market is open
function isMarketOpen() {
    const now = new Date();
    const options = { timeZone: 'Asia/Kolkata', hour12: false, hour: 'numeric', minute: 'numeric', weekday: 'short' } as const;
    const formatter = new Intl.DateTimeFormat('en-US', options);
    const parts = formatter.formatToParts(now);

    const hourStr = parts.find(p => p.type === 'hour')?.value || '0';
    const minStr = parts.find(p => p.type === 'minute')?.value || '0';
    const weekday = parts.find(p => p.type === 'weekday')?.value || '';

    if (weekday === 'Sat' || weekday === 'Sun') return false;

    const hour = parseInt(hourStr, 10);
    const minute = parseInt(minStr, 10);

    const currentMins = hour * 60 + minute;
    return currentMins >= 555 && currentMins < 930; // 09:15 AM to 03:30 PM IST
}

function IsolatedMarketTicker() {
    const isWsConnected = useLiveMarketStore(state => state.isWsConnected);
    const tickerData = useLiveMarketStore(state => state.tickerData);
    return <MarketTicker isWsConnected={isWsConnected} tickerData={tickerData} />;
}

export default function LiveTrading() {
    return (
        <Suspense fallback={
            <div className="flex h-screen bg-background text-foreground items-center justify-center">
                <TradeNotifications />
                <div className="flex-1 overflow-auto bg-gradient-to-br from-background via-background to-muted/10 pb-20 center justify-center">
                    <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                    <span className="ml-2">Loading Terminal...</span>
                </div>
            </div>
        }>
            <LiveTradingContent />
        </Suspense>
    );
}

const LOT_SIZES: Record<string, number> = {
    "NIFTY": 65,
    "BANKNIFTY": 15,
    "FINNIFTY": 25,
    "MIDCPNIFTY": 50,
    "SENSEX": 10,
    "AARTIIND": 1000,
    "ABB": 250,
    "ABBOTINDIA": 40,
    "ABCAPITAL": 5400,
    "ABFRL": 2600,
    "ACC": 300,
    "ADANIENT": 300,
    "ADANIPORTS": 400,
    "ALKEM": 200,
    "AMBUJACEM": 1800,
    "APOLLOHOSP": 125,
    "APOLLOTYRE": 1700,
    "ASHOKLEY": 5000,
    "ASIANPAINT": 200,
    "ASTRAL": 348,
    "ATUL": 75,
    "AUBANK": 1000,
    "AUROPHARMA": 1050,
    "AXISBANK": 625,
    "BAJAJ-AUTO": 125,
    "BAJAJFINSV": 500,
    "BAJFINANCE": 125,
    "BALKRISIND": 300,
    "BALRAMCHIN": 1600,
    "BANDHANBNK": 2500,
    "BANKBARODA": 5850,
    "BATAINDIA": 375,
    "BEL": 5700,
    "BERGEPAINT": 1100,
    "BHARATFORG": 500,
    "BHARTIARTL": 950,
    "BHEL": 5250,
    "BIOCON": 2500,
    "BOSCHLTD": 50,
    "BPCL": 1800,
    "BRITANNIA": 200,
    "BSOFT": 1000,
    "CANBK": 2700,
    "CANFINHOME": 975,
    "CHAMBLFERT": 1900,
    "CHOLAFIN": 1250,
    "CIPLA": 650,
    "COALINDIA": 2100,
    "COFORGE": 150,
    "COLPAL": 350,
    "CONCOR": 1000,
    "COROMANDEL": 700,
    "CROMPTON": 1800,
    "CUB": 5000,
    "CUMMINSIND": 300,
    "DABUR": 1250,
    "DALBHARAT": 250,
    "DEEPAKNTR": 300,
    "DIVISLAB": 200,
    "DIXON": 100,
    "DLF": 1650,
    "DRREDDY": 125,
    "EICHERMOT": 175,
    "ESCORTS": 275,
    "EXIDEIND": 3600,
    "FEDERALBNK": 5000,
    "GAIL": 4050,
    "GLENMARK": 700,
    "GMRINFRA": 11250,
    "GNFC": 1300,
    "GODREJCP": 500,
    "GODREJPROP": 175,
    "GRANULES": 2000,
    "GRASIM": 250,
    "GUJGASLTD": 1250,
    "HAL": 300,
    "HAVELLS": 500,
    "HCLTECH": 700,
    "HDFCAMC": 150,
    "HDFCBANK": 550,
    "HDFCLIFE": 1100,
    "HEROMOTOCO": 300,
    "HINDALCO": 1400,
    "HINDCOPPER": 4300,
    "HINDPETRO": 2700,
    "HINDUNILVR": 300,
    "ICICIBANK": 700,
    "ICICIGI": 500,
    "ICICIPRULI": 1500,
    "IDEA": 80000,
    "IDFC": 10000,
    "IDFCFIRSTB": 15000,
    "IEX": 3750,
    "IGL": 1375,
    "INDHOTEL": 2000,
    "INDIACEM": 2900,
    "INDIAMART": 150,
    "INDIGO": 300,
    "INDUSINDBK": 500,
    "INDUSTOWER": 3400,
    "INFY": 400,
    "IOC": 9750,
    "IPCALAB": 650,
    "IRCTC": 875,
    "ITC": 1600,
    "JINDALSTEL": 1250,
    "JKCEMENT": 250,
    "JSWSTEEL": 675,
    "JUBLFOOD": 1250,
    "KOTAKBANK": 400,
    "L&TFH": 4462,
    "LALPATHLAB": 250,
    "LAURUSLABS": 1700,
    "LICHSGFIN": 2000,
    "LT": 300,
    "LTIM": 150,
    "LTTS": 200,
    "LUPIN": 850,
    "M&M": 350,
    "M&MFIN": 2000,
    "MANAPPURAM": 3000,
    "MARICO": 1200,
    "MARUTI": 50,
    "MCDOWELL-N": 700,
    "MCX": 200,
    "METROPOLIS": 400,
    "MFSL": 800,
    "MGL": 800,
    "MOTHERSON": 7100,
    "MPHASIS": 275,
    "MRF": 10,
    "MUTHOOTFIN": 550,
    "NATIONALUM": 7500,
    "NAUKRI": 150,
    "NAVINFLUOR": 150,
    "NESTLEIND": 400,
    "NMDC": 4500,
    "NTPC": 3000,
    "OBEROIRLTY": 700,
    "OFSS": 100,
    "ONGC": 3850,
    "PAGEIND": 15,
    "PEL": 750,
    "PERSISTENT": 200,
    "PETRONET": 3000,
    "PFC": 3875,
    "PIDILITIND": 250,
    "PIIND": 250,
    "PNB": 8000,
    "POLYCAB": 100,
    "POWERGRID": 3600,
    "PVRINOX": 407,
    "RAMCOCEM": 850,
    "RBLBANK": 2500,
    "RECLTD": 2000,
    "RELIANCE": 250,
    "SAIL": 8000,
    "SBICARD": 800,
    "SBILIFE": 750,
    "SBIN": 750,
    "SHREECEM": 25,
    "SHRIRAMFIN": 300,
    "SIEMENS": 125,
    "SRF": 375,
    "SUNTV": 1500,
    "SUNPHARMA": 700,
    "SYNGENE": 1000,
    "TATACHEM": 550,
    "TATACOMM": 500,
    "TATACONSUM": 900,
    "TATAMOTORS": 1425,
    "TATAPOWER": 3375,
    "TATASTEEL": 5500,
    "TCS": 175,
    "TECHM": 600,
    "TITAN": 175,
    "TORNTPHARM": 500,
    "TRENT": 400,
    "TVSMOTOR": 700,
    "UBL": 400,
    "ULTRACEMCO": 100,
    "UPL": 1300,
    "VEDL": 3150,
    "VOLTAS": 600,
    "WIPRO": 1500,
    "ZEEL": 3000,
    "ZYDUSLIFE": 900,
};

export const getBaseQty = (sym: string): number => {
    const upperSym = sym.toUpperCase();
    
    // First check dynamic lot sizes from settings
    const { lotSizes } = useLiveSettingsStore.getState();
    const dynamicKeys = Object.keys(lotSizes || {}).sort((a, b) => b.length - a.length);
    for (const key of dynamicKeys) {
        if (upperSym.includes(key)) return lotSizes[key];
    }
    
    // Fallback to hardcoded list
    const keys = Object.keys(LOT_SIZES).sort((a, b) => b.length - a.length);
    for (const key of keys) {
        if (upperSym.includes(key)) return LOT_SIZES[key];
    }
    return 1;
};

const ALL_TIMEFRAMES = ["1 Min", "3 Min", "5 Min", "15 Min", "30 Min", "1 Hour", "1 Week", "1 Month"];

// --- Isolated Components for Performance Optimization ---
// By moving volatile state here, we prevent the heavy LiveTradingContent (and Charts) from re-rendering 20 times a second.

function TradeNotifications() {
    const trades = useLiveMarketStore(state => state.trades);
    const prevTradesRef = useRef<Trade[]>([]);
    const isInitialFetch = useRef<boolean>(true);
    
    useEffect(() => {
        if (isInitialFetch.current && trades.length > 0) {
            isInitialFetch.current = false;
            prevTradesRef.current = trades;
            return;
        }
        if (trades.length > prevTradesRef.current.length) {
            const newTrades = trades.filter(t => !prevTradesRef.current.some(pt => pt.id === t.id));
            newTrades.forEach(t => {
                let message = "";
                let type: 'success' | 'danger' | 'warning' | 'info' = 'info';
                if (t.side === 'BUY') { message = `🔵 BUY Order Executed: ${t.symbol} @ ₹${t.price.toFixed(2)}`; type = 'success'; }
                else if (t.side === 'SELL') { message = `🔴 SELL Order Executed: ${t.symbol} @ ₹${t.price.toFixed(2)}`; type = 'danger'; }
                else if (t.status === 'Target') { message = `🎯 Target Hit: ${t.symbol} @ ₹${t.price.toFixed(2)}`; type = 'success'; }
                else if (t.status === 'SL') { message = `🛡️ Stop Loss Hit: ${t.symbol} @ ₹${t.price.toFixed(2)}`; type = 'warning'; }
                else { message = `📝 Trade Update: ${t.symbol} status is ${t.status}`; type = 'info'; }
                toast[type === 'danger' ? 'error' : type](message);
            });
            prevTradesRef.current = trades;
        }
    }, [trades]);

    return null; // Invisible component
}

function AiCommentaryPanel({ urlSymbol, timeframe }: { urlSymbol: string, timeframe: string }) {
    const pnl = useLiveMarketStore(state => state.pnl);
    const changePercent = useLiveMarketStore(state => state.changePercent);
    const aiConfidence = useLiveMarketStore(state => state.aiConfidence);
    const isWsConnected = useLiveMarketStore(state => state.isWsConnected);
    const aiCommentary = useLiveMarketStore(state => state.aiCommentary);
    const setAiCommentary = useLiveMarketStore(state => state.setAiCommentary);

    useEffect(() => {
        if (!isWsConnected) {
            setAiCommentary("Awaiting secure connection to market data feed...");
            return;
        }
        const buildCommentary = () => {
            if (pnl > 500) return `Session P&L: +₹${pnl.toFixed(2)}. Risk engine actively protecting profits.`;
            else if (pnl < -300) return `Session P&L: -₹${Math.abs(pnl).toFixed(2)}. Max loss guard monitoring threshold.`;
            else if (changePercent > 0.5) return `${urlSymbol} up ${changePercent.toFixed(2)}% — Bullish momentum on ${timeframe}. Scanning for high-probability entries.`;
            else if (changePercent < -0.5) return `${urlSymbol} down ${changePercent.toFixed(2)}% — Bearish pressure on ${timeframe}. Evaluating short setups.`;
            else if (aiConfidence > 75) return `AI signal confidence: ${aiConfidence.toFixed(0)}% — High conviction setup detected on ${urlSymbol}.`;
            else if (aiConfidence > 50) return `AI signal confidence: ${aiConfidence.toFixed(0)}% — Neutral market. Waiting for clearer directional signal.`;
            else return `Monitoring ${urlSymbol} on ${timeframe}. No actionable signal yet. System on standby.`;
        };
        setAiCommentary(buildCommentary());
        const interval = setInterval(() => setAiCommentary(buildCommentary()), 8000);
        return () => clearInterval(interval);
    }, [isWsConnected, urlSymbol, aiConfidence, pnl, changePercent, timeframe, setAiCommentary]);

    return (
        <motion.div
            variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
            initial="hidden" animate="show"
            className="stat-card mt-6 p-4 relative overflow-hidden flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-muted/10 border-blue-500/20"
        >
            <div className="absolute left-0 top-0 w-1 h-full bg-gradient-to-b from-blue-500 to-cyan-500 rounded-l-lg"></div>
            <div className="p-3 bg-blue-500/10 rounded-xl border border-blue-500/20 shrink-0">
                <Brain className="w-6 h-6 text-blue-500 animate-pulse" />
            </div>
            <div className="flex-1">
                <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                        </span>
                        AI Live Analyst
                    </span>
                </div>
                <div className="text-sm font-mono text-foreground font-medium flex items-center gap-2">
                    <span className="text-blue-500">{">"}</span>
                    <span className="text-foreground/90">{aiCommentary}</span>
                    <span className="w-1.5 h-4 bg-blue-500 animate-pulse inline-block ml-1"></span>
                </div>
            </div>
        </motion.div>
    );
}

function LiveTradingContent() {
    const searchParams = useSearchParams();
    const urlSymbol = searchParams.get('symbol') || 'NIFTY';
    const defaultBaseQty = getBaseQty(urlSymbol);

    const [favoriteTimeframes, setFavoriteTimeframes] = useState<string[]>(['1 Min', '5 Min', '15 Min']);
    const [showAllTimeframes, setShowAllTimeframes] = useState(false);

    // Removed heavy state subscriptions to prevent entire page re-rendering at 20 FPS
    
    // Zustand Setters (needed for HTTP polling fallback)
    const setTradingMode = useLiveSettingsStore(state => state.setTradingMode);
    const tradingMode = useLiveSettingsStore(state => state.tradingMode);
    
    const connectWs = useLiveMarketStore(state => state.connectWs);
    const disconnectWs = useLiveMarketStore(state => state.disconnectWs);

    const [isLoading, setIsLoading] = useState(true);
    const [isChartFullScreen, setIsChartFullScreen] = useState(false);
    const [showDynamicTrend, setShowDynamicTrend] = useState(false);
    const [chartMode, setChartMode] = useState<"native" | "ultra">("native");
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [showLiveGuard, setShowLiveGuard] = useState(false);

    // Live Settings from Zustand
    const {
        autoMode, setAutoMode,
        timeframe, setTimeframe,
        strategy, setStrategy,
        stoploss, setStoploss, setQuantity,
        setLotSizes, setFilters,
        setEnablePyramiding, setTrailingSl, setDonchianPeriod,
        setScalePct, setMaxScales, maxDailyLossPct, setMaxDailyLossPct, setMaxDailyTrades,
        setTrailTrigger, setTrailOffset
    } = useLiveSettingsStore();
    const dismissNotification = (id: number) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    // WebSocket Connection for Live Tick Data via Zustand
    useEffect(() => {
        connectWs(urlSymbol);
        return () => {
            disconnectWs();
        };
    }, [urlSymbol, connectWs, disconnectWs]);

    // Escape key closes fullscreen chart
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isChartFullScreen) setIsChartFullScreen(false);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isChartFullScreen]);

    // Fetch Settings (to get trading mode and strategy)
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const res = await fetch('/api/settings');
                if (res.ok) {
                    const data = await res.json();
                    const mode = data.live_trading_mode ? "live" : "paper";
                    setTradingMode(mode);
                    setAutoMode(data.auto_trade_enabled ?? true);
                    if (typeof window !== 'undefined') {
                        localStorage.setItem('tradingMode', mode);
                    }
                    setStrategy(data.active_strategy || "institutional_momentum");
                    if (data.stoploss !== undefined) {
                        setStoploss(data.stoploss);
                    }
                    if (data.lot_sizes) {
                        setLotSizes(data.lot_sizes);
                    }
                    // Initialize from settings ONLY if it's a multiple of our baseQty (to avoid 65/20 = 3.25 lots)
                    if (data.quantity && data.quantity % defaultBaseQty === 0) {
                        setQuantity(data.quantity);
                    }
                    setFilters({
                        enable_ema_filter: data.enable_ema_filter ?? true,
                        enable_volume_filter: data.enable_volume_filter ?? false,
                        enable_adx_filter: data.enable_adx_filter ?? false,
                        enable_vwap_filter: data.enable_vwap_filter ?? true,
                        enable_rsi_filter: data.enable_rsi_filter ?? true,
                        enable_squeeze_filter: data.enable_squeeze_filter || false,
                        enable_extension_filter: data.enable_extension_filter || false,
                        enable_cpr_filter: data.enable_cpr_filter || false,
                        enable_aggression_filter: data.enable_aggression_filter || false
                    });

                    if (data.enable_pyramiding !== undefined) setEnablePyramiding(data.enable_pyramiding);
                    if (data.trailing_sl !== undefined) setTrailingSl(data.trailing_sl);
                    if (data.donchian_period !== undefined) setDonchianPeriod(data.donchian_period);
                    if (data.scale_pct !== undefined) setScalePct(data.scale_pct);
                    if (data.max_scales !== undefined) setMaxScales(data.max_scales);
                    if (data.max_daily_loss_pct !== undefined) setMaxDailyLossPct(data.max_daily_loss_pct);
                    if (data.max_daily_trades !== undefined) setMaxDailyTrades(data.max_daily_trades);
                    if (data.trail_trigger !== undefined) setTrailTrigger(data.trail_trigger);
                    if (data.trail_offset !== undefined) setTrailOffset(data.trail_offset);
                }
            } catch (error) {
                console.error("Failed to fetch settings:", error);
            }
        };
        fetchSettings();
    }, [defaultBaseQty]);

    // Reset to 1 Lot when the symbol changes
    useEffect(() => {
        setQuantity(defaultBaseQty);
    }, [urlSymbol, defaultBaseQty]);

    // applyTradingModeChange declared first so toggleTradingMode can call it
    const applyTradingModeChange = async (newMode: string) => {
        const isLive = newMode === 'live';
        setTradingMode(newMode);
        if (typeof window !== 'undefined') localStorage.setItem('tradingMode', newMode);
        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ live_trading_mode: isLive })
            });
            if (!res.ok) {
                setTradingMode(tradingMode); // Revert on failure
            }
        } catch {
            setTradingMode(tradingMode);
        }
    };

    // Toggle Trading Mode (Live/Paper) — with guard for Live mode
    const toggleTradingMode = () => {
        if (tradingMode === 'paper') {
            // Going to Live — show confirmation guard
            setShowLiveGuard(true);
        } else {
            // Going to Paper — no guard needed
            applyTradingModeChange('paper');
        }
    };

    // Toggle Auto/Manual Mode
    const toggleAutoMode = async () => {
        const newMode = !autoMode;
        setAutoMode(newMode);
        toast.success(`${newMode ? 'Auto' : 'Manual'} Mode Activated`);

        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_trade_enabled: newMode })
            });

            if (!res.ok) {
                console.error("Failed to update auto mode on server");
                setAutoMode(autoMode); // Revert UI
            }
        } catch (error) {
            console.error("Error updating auto mode:", error);
            setAutoMode(autoMode); // Revert UI
        }
    };

    // Fetch State (P&L, Equity, etc.) fallback for HTTP polling
    useEffect(() => {
        let isMounted = true;
        let timeoutId: NodeJS.Timeout;

        const fetchState = async () => {
            try {
                const res = await fetch(`/api/state?symbol=${urlSymbol}&live=${tradingMode === 'live'}`, { cache: 'no-store' });
                if (!isMounted) return;
                const data = await res.json();
                
                const store = useLiveMarketStore.getState();

                // Only use fallback polling for trades/pnl if WS is disconnected
                if (!store.isWsConnected) {
                    store.setEquity(data.equity);
                    store.setPnl(data.pnl);
                    store.setTrades(data.trades || []);

                    if (data.signalsData && data.signalsData.confidence) {
                        store.setAiConfidence(data.signalsData.confidence);
                    }

                    if (data.tickerData && Object.keys(data.tickerData).length > 0) {
                        store.setTickerData((prev: any) => ({
                            ...prev,
                            ...data.tickerData
                        }));
                    }
                }

                const parsedPrice = Number(data.currentPrice);
                if (!store.isWsConnected || store.currentPrice === 0) {
                    if (parsedPrice && parsedPrice !== 0) {
                        store.setCurrentPrice((prev: number) => (isMarketOpen() || prev === 0) ? parsedPrice : prev);
                    }
                    if (data.changePercent) {
                        store.setChangePercent((prev: number) => (isMarketOpen() || prev === 0) ? data.changePercent : prev);
                    }
                }

                setIsLoading(false);
            } catch (error) {
                if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
                } else {
                    console.warn("State polling issue:", error);
                }
                if (isMounted) setIsLoading(false);
            } finally {
                if (isMounted) {
                    const wsConnected = useLiveMarketStore.getState().isWsConnected;
                    timeoutId = setTimeout(fetchState, wsConnected ? 5000 : 1500);
                }
            }
        };

        fetchState();
        return () => {
            isMounted = false;
            clearTimeout(timeoutId);
        };
    }, [urlSymbol, tradingMode]);






    return (
        <div className="flex h-screen bg-background text-foreground">
            <Sidebar />

            {/* Live Mode Guard Modal */}
            {showLiveGuard && (
                <div className="fixed inset-0 z-[300] flex items-center justify-center">
                    <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setShowLiveGuard(false)} />
                    <div className="relative z-10 bg-card border border-destructive/40 rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4">
                        <div className="flex items-start gap-3 mb-4">
                            <div className="p-3 bg-destructive/15 rounded-xl shrink-0">
                                <AlertCircle className="w-6 h-6 text-destructive" />
                            </div>
                            <div>
                                <h4 className="font-bold text-foreground text-lg">⚠️ Switching to LIVE Trading</h4>
                                <p className="text-sm text-muted-foreground mt-2">Real money will be at risk. Please confirm the current settings before proceeding.</p>
                                <div className="mt-3 p-3 bg-muted/50 rounded-xl text-xs space-y-1 font-mono">
                                    <p>Strategy: {strategy}</p>
                                    <p>SL: {stoploss}%</p>
                                    <p>Max Daily Loss: {maxDailyLossPct}%</p>
                                </div>
                            </div>
                        </div>
                        <div className="flex gap-3 mt-5">
                            <button onClick={() => setShowLiveGuard(false)} className="flex-1 px-4 py-2 rounded-xl border border-border bg-background text-sm font-semibold text-foreground hover:bg-muted transition-colors">
                                Cancel
                            </button>
                            <button
                                onClick={() => { setShowLiveGuard(false); applyTradingModeChange('live'); }}
                                className="flex-1 px-4 py-2 rounded-xl bg-destructive hover:bg-destructive/90 text-white text-sm font-bold transition-colors"
                            >
                                I Understand — Go Live
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <div className="flex-1 flex flex-col overflow-hidden">
                <Header />

                <main className="flex-1 overflow-y-auto p-6 space-y-6">
                    {/* Ticker Tape & Broker Login Row */}
                    <div className="flex justify-between items-center gap-4">
                        {/* Ticker Tape - Glassmorphism Marquee */}
                        <IsolatedMarketTicker />
                    </div>

                    {/* Header & Controls Section */}
                    <div className="flex flex-col gap-5 w-full">
                        {/* Title Row & Toggle Switch */}
                        <div className="flex justify-between items-start shrink-0 w-full">
                            <div className="whitespace-nowrap">
                                <h1 className="font-display font-bold text-3xl text-foreground tracking-tight">Live Trading Terminal</h1>
                                <p className="text-sm text-muted-foreground mt-1">Monitor real-time executions and account equity.</p>
                            </div>

                            {/* Toggles Container */}
                            <div className="flex items-center gap-6 mt-1">
                                {/* Auto / Manual Mode Toggle */}
                                <div className="flex items-center gap-3 bg-muted/20 px-4 py-2 rounded-xl border border-border/10">
                                    <span className={`text-xs font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${autoMode ? 'text-blue-500' : 'text-muted-foreground/40'}`}>
                                        <Bot className="w-5 h-5" />
                                        Auto
                                    </span>

                                    <button
                                        onClick={toggleAutoMode}
                                        className={`cursor-pointer relative w-12 h-6 rounded-full transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background ${autoMode ? 'bg-blue-500 focus:ring-blue-500' : 'bg-muted-foreground/40 focus:ring-muted-foreground/40'}`}
                                    >
                                        <motion.div
                                            className="absolute top-1 left-1 w-4 h-4 bg-white rounded-full flex items-center justify-center"
                                            animate={{ x: autoMode ? 0 : 24 }}
                                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                        >
                                            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white to-gray-200"></div>
                                        </motion.div>
                                    </button>

                                    <span className={`text-xs font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${!autoMode ? 'text-amber-500' : 'text-muted-foreground/40'}`}>
                                        <User className="w-5 h-5" />
                                        Manual
                                    </span>
                                </div>

                                {/* Premium Animated Toggle Switch */}
                                <div className="flex items-center gap-3 bg-muted/20 px-4 py-2 rounded-xl border border-border/10 shrink-0">
                                    <span className={`text-xs font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${tradingMode === 'live' ? 'text-success' : 'text-muted-foreground/40'}`}>
                                        <Globe className="w-5 h-5" />
                                        Live
                                    </span>

                                    <button
                                        onClick={toggleTradingMode}
                                        className={`cursor-pointer relative w-12 h-6 rounded-full transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background ${tradingMode === 'live' ? 'bg-success focus:ring-success' : 'bg-primary focus:ring-primary'}`}
                                    >
                                        <motion.div
                                            className="absolute top-1 left-1 w-4 h-4 bg-white rounded-full flex items-center justify-center"
                                            animate={{ x: tradingMode === 'paper' ? 24 : 0 }}
                                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                        >
                                            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white to-gray-200"></div>
                                        </motion.div>
                                    </button>

                                    <span className={`text-xs font-bold flex items-center gap-1.5 transition-colors uppercase tracking-wider ${tradingMode === 'paper' ? 'text-primary ' : 'text-muted-foreground/40'}`}>
                                        <Briefcase className="w-5 h-5" />
                                        Paper
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Settings Unified Interface */}
                        <div className="flex flex-col w-full mt-2 gap-4">
                            <div className="grid grid-cols-2 gap-4">
                                <ErrorBoundary title="AI Signal Error">
                                    <MergedAiSignal symbol={urlSymbol} />
                                </ErrorBoundary>
                                <ErrorBoundary title="BTST Predictor Error">
                                    <BtstPredictor symbol={urlSymbol} />
                                </ErrorBoundary>
                            </div>
                            <ErrorBoundary title="Trade Panel Error">
                                <TradeActionPanel urlSymbol={urlSymbol} defaultBaseQty={defaultBaseQty} />
                            </ErrorBoundary>

                            {/* --- NEWS TICKER --- */}
                            <div className="w-full border border-border/40 bg-card rounded-2xl overflow-hidden shadow-sm">
                                <div className="p-1.5 w-full">
                                    <NewsTicker />
                                </div>
                            </div>
                        </div>

                        {/* TradingView & Orders Row */}
                        <ErrorBoundary title="Metrics Error">
                            <MetricsBar isLoading={isLoading} isMarketOpen={isMarketOpen()} />
                        </ErrorBoundary>

                        {/* AI Live Analyst Panel isolated */}
                        <AiCommentaryPanel urlSymbol={urlSymbol} timeframe={timeframe} />

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Native Custom Chart built with Lightweight-Charts */}
                            <div className={`transition-all duration-300 flex flex-col ${isChartFullScreen ? 'fixed inset-4 z-[100] glass-card rounded-2xl p-6 border border-border/20 shadow-2xl flex flex-col' : 'lg:col-span-2 glass-card rounded-xl p-6 border border-border/20 h-[600px]'}`}>
                                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-2">
                                    <div>
                                        <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
                                            <span className="w-2 h-2 rounded-full bg-success animate-pulse"></span>
                                            Active Market Chart: {urlSymbol}
                                        </h3>
                                        <p className="text-xs text-muted-foreground">Native Institutional Candlestick Chart (Live Feed)</p>
                                    </div>

                                    {/* Timeframe Selector (TradingView Style) & Chart Mode Toggle */}
                                    <div className="flex items-center gap-4">
                                        {/* Chart Mode Toggle */}
                                        <div className="flex items-center bg-muted/30 rounded-lg p-1 border border-border/50">
                                            <button
                                                onClick={() => setChartMode('native')}
                                                className={`cursor-pointer px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${chartMode === 'native' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                                            >
                                                Basic
                                            </button>
                                            <button
                                                onClick={() => setChartMode('ultra')}
                                                className={`cursor-pointer px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${chartMode === 'ultra' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                                            >
                                                Pro
                                            </button>
                                        </div>

                                        <div className="flex items-center bg-muted/30 rounded-lg p-1 border border-border/50 relative">
                                            {/* Starred Timeframes */}
                                            <div className="flex items-center">
                                                {ALL_TIMEFRAMES.filter(tf => favoriteTimeframes.includes(tf) || tf === timeframe).map((tf) => (
                                                    <button
                                                        key={`fav-${tf}`}
                                                        onClick={() => setTimeframe(tf)}
                                                        className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${timeframe === tf ? "bg-primary text-primary-foreground " : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
                                                    >
                                                        {tf}
                                                    </button>
                                                ))}
                                            </div>

                                            {/* Dropdown Toggle */}
                                            <div className="relative border-l border-border/50 ml-1 pl-1">
                                                <button
                                                    onClick={() => setShowAllTimeframes(!showAllTimeframes)}
                                                    className="cursor-pointer p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors flex items-center justify-center"
                                                >
                                                    <ChevronDown className="w-4 h-4" />
                                                </button>

                                                {/* Dropdown Menu */}
                                                <AnimatePresence>
                                                    {showAllTimeframes && (
                                                        <motion.div
                                                            initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                                            exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                                            transition={{ duration: 0.15 }}
                                                            className="absolute right-0 top-full mt-2 w-48 bg-card border border-border/50 rounded-xl overflow-hidden z-50"
                                                        >
                                                            <div className="p-2 space-y-1">
                                                                {ALL_TIMEFRAMES.map((tf) => (
                                                                    <div key={`all-${tf}`} className="flex items-center justify-between group">
                                                                        <button
                                                                            onClick={() => { setTimeframe(tf); setShowAllTimeframes(false); }}
                                                                            className={`cursor-pointer flex-1 text-left px-3 py-2 text-sm rounded-lg transition-colors ${timeframe === tf ? "bg-primary/20 text-primary font-bold" : "text-foreground hover:bg-muted/80"}`}
                                                                        >
                                                                            {tf}
                                                                        </button>
                                                                        <button
                                                                            onClick={(e) => {
                                                                                e.stopPropagation();
                                                                                if (favoriteTimeframes.includes(tf)) {
                                                                                    setFavoriteTimeframes(prev => prev.filter(t => t !== tf));
                                                                                } else {
                                                                                    setFavoriteTimeframes(prev => [...prev, tf]);
                                                                                }
                                                                            }}
                                                                            className="cursor-pointer p-2 opacity-50 group-hover:opacity-100 hover:text-warning transition-all"
                                                                        >
                                                                            <Star className={`w-4 h-4 ${favoriteTimeframes.includes(tf) ? "fill-warning text-warning" : ""}`} />
                                                                        </button>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </motion.div>
                                                    )}
                                                </AnimatePresence>
                                            </div>

                                            <div className="relative border-l border-border/50 ml-1 pl-2 flex items-center gap-1">
                                                {/* Dynamic Trend Toggle */}
                                                {chartMode === 'native' && (
                                                    <button
                                                        onClick={() => setShowDynamicTrend(!showDynamicTrend)}
                                                        className={`cursor-pointer p-1.5 rounded-md transition-colors flex items-center justify-center ${showDynamicTrend ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                                                        title={showDynamicTrend ? "Disable Dynamic Trend Candles" : "Enable Dynamic Trend Candles"}
                                                    >
                                                        <Activity className="w-4 h-4" />
                                                    </button>
                                                )}

                                                {/* Full Screen Toggle */}
                                                <button
                                                    onClick={() => setIsChartFullScreen(!isChartFullScreen)}
                                                    className="cursor-pointer p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors flex items-center justify-center"
                                                    title={isChartFullScreen ? "Exit Full Screen" : "Full Screen"}
                                                >
                                                    {isChartFullScreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Container for Native Chart */}
                                <div
                                    key={`${urlSymbol}-${timeframe}-${chartMode}`}
                                    className={`w-full flex-1 min-h-0 rounded-lg overflow-hidden flex flex-col`}
                                >
                                    <ErrorBoundary title="Chart Module Error">
                                        {chartMode === 'native' ? (
                                            <NativeChart symbol={urlSymbol} livePrice={0} timeframe={timeframe} showDynamicTrend={showDynamicTrend} lastTick={Date.now()} />
                                        ) : (
                                            <AdvancedChart symbol={urlSymbol} livePrice={0} timeframe={timeframe} />
                                        )}
                                    </ErrorBoundary>
                                </div>
                            </div>

                            {/* Right Column: Execution Feed */}
                            <div className="h-[600px] overflow-hidden flex flex-col relative z-[90]">
                                <ErrorBoundary title="Execution Feed Error">
                                    <ExecutionFeed />
                                </ErrorBoundary>
                            </div>
                        </div>

                        {/* Options Desk Section */}
                        <div className="mt-6 w-full">
                            <ErrorBoundary title="Options Desk Error">
                                <OptionsDesk symbol={urlSymbol} />
                            </ErrorBoundary>
                        </div>
                        {/* Live Positions & Orders Section */}
                        <div className="mt-6 w-full pb-10">
                            <ErrorBoundary title="Live Positions Error">
                                <LivePositions urlSymbol={urlSymbol} />
                            </ErrorBoundary>
                        </div>
                    </div>
                </main>
            </div>

            {/* Live Notifications — dismissable */}
            <div className="fixed top-20 right-6 z-50 space-y-3 pointer-events-none">
                <AnimatePresence>
                    {notifications.map(n => (
                        <motion.div
                            key={n.id}
                            initial={{ opacity: 0, y: -20, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95, filter: "blur(4px)" }}
                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                            className={`p-4 rounded-xl flex items-start gap-3 text-white font-medium border pointer-events-auto ${n.type === 'success' ? 'bg-emerald-600/90 border-emerald-500/50 ' : n.type === 'danger' ? 'bg-rose-600/90 border-rose-500/50 ' : n.type === 'warning' ? 'bg-amber-600/90 border-amber-500/50 ' : 'bg-blue-600/90 border-blue-500/50 '}`}
                        >
                            <div className="mt-0.5 opacity-90">
                                {n.type === 'success' ? <TrendingUp className="w-5 h-5" /> :
                                    n.type === 'danger' ? <TrendingDown className="w-5 h-5" /> :
                                        n.type === 'warning' ? <Shield className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
                            </div>
                            <div className="flex-1">
                                <p className="text-sm leading-tight">{n.message}</p>
                            </div>
                            {/* Dismiss button */}
                            <button
                                onClick={() => dismissNotification(n.id)}
                                className="opacity-70 hover:opacity-100 transition-opacity ml-1"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
}
