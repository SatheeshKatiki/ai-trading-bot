import { create } from 'zustand';
import { toast } from 'sonner';

let reconnectAttempts = 0;
let rAF_id: number | null = null;
let pendingUpdates: Partial<LiveMarketState> = {};
let pendingTickerUpdates: Record<string, TickerData> = {};

export interface TickerData {
    lp: number;
    chp: number;
    vol?: number;
    vol_traded_today?: number;
    last_qty?: number;
    /** Where this price came from: 'fyers' | 'broker' | 'yfinance' | 'pending'.
     *  Absent only on legacy payloads. Never render a price whose provenance
     *  you have not checked -- see FeedStatus below. */
    src?: string;
    /** Epoch seconds at which the price was actually observed upstream. */
    ts?: number;
}

/** Feed health published by the backend broadcaster on every frame.
 *  'live'     - at least one authoritative, fresh, tradeable price
 *  'degraded' - prices exist but none are tradeable (delayed/stale/placeholder)
 *  'down'     - no market data at all
 *  The dashboard must show this. Silently rendering a number from a degraded
 *  feed is exactly the failure this field exists to prevent. */
export interface FeedStatus {
    status: 'live' | 'degraded' | 'down';
    sources: string[];
    symbols: number;
    tradeable_symbols: number;
    market_open: boolean;
    simulated: boolean;
    ts: number;
}

export interface Trade {
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    price: number;
    quantity: number;
    status: string;
    time: string;
}

export interface PositionDetail {
    symbol: string;
    entry_price: number;
    ltp: number;
    qty: number;
    side: number;
    unrealized_pnl: number;
    invested?: number;
    roi?: number;
    sl: number;
    target: number;
}

export interface LiveMarketState {
    tickerData: Record<string, TickerData>;
    /** Backend feed health. null until the first frame arrives. */
    feed: FeedStatus | null;
    currentPrice: number;
    changePercent: number;
    pnl: number;             // Realized P&L (closed trades today)
    unrealizedPnl: number;   // Unrealized P&L (open positions, mark-to-market)
    totalPnl: number;        // total_pnl = realized + unrealized
    marginDeployed: number;  // Dynamic invested margin for active/today's trades
    marginRoi: number;       // (total_pnl / margin_deployed) * 100
    accountRoi: number;      // (total_pnl / equity) * 100
    equity: number;
    openPositionsCount: number;
    positionsDetail: PositionDetail[];
    trades: Trade[];
    aiConfidence: number;
    riskStatus: string;
    isWsConnected: boolean;
    aiCommentary: string;
    lastPingTime: number;
    tradingMode: 'paper' | 'live';   // Fix 7: injected from WS trading_mode field
    sentiment: { score: number; label: string; top_headlines: string[] }; // Fix 2

    // Actions
    setTickerData: (data: Record<string, TickerData> | ((prev: Record<string, TickerData>) => Record<string, TickerData>)) => void;
    setCurrentPrice: (price: number | ((prev: number) => number)) => void;
    setChangePercent: (chp: number | ((prev: number) => number)) => void;
    setPnl: (pnl: number | ((prev: number) => number)) => void;
    setUnrealizedPnl: (pnl: number | ((prev: number) => number)) => void;
    setTotalPnl: (pnl: number | ((prev: number) => number)) => void;
    setMarginDeployed: (val: number | ((prev: number) => number)) => void;
    setMarginRoi: (val: number | ((prev: number) => number)) => void;
    setAccountRoi: (val: number | ((prev: number) => number)) => void;
    setEquity: (equity: number | ((prev: number) => number)) => void;
    setOpenPositionsCount: (count: number) => void;
    setPositionsDetail: (positions: PositionDetail[]) => void;
    setTrades: (trades: Trade[] | ((prev: Trade[]) => Trade[])) => void;
    setAiConfidence: (confidence: number | ((prev: number) => number)) => void;
    setRiskStatus: (status: string | ((prev: string) => string)) => void;
    setIsWsConnected: (connected: boolean | ((prev: boolean) => boolean)) => void;
    setAiCommentary: (commentary: string | ((prev: string) => string)) => void;
    setLastPingTime: (time: number | ((prev: number) => number)) => void;
    setTradingMode: (mode: 'paper' | 'live') => void;  // Fix 7

    // WebSocket
    ws: WebSocket | null;
    connectWs: (urlSymbol: string) => void;
    disconnectWs: () => void;
}

export const useLiveMarketStore = create<LiveMarketState>((set, get) => ({
    // Deliberately EMPTY. This used to be seeded with hardcoded index prices
    // (NIFTY 23820.35, ...) which rendered as a live quote until the first
    // real WebSocket frame arrived -- the client-side half of the same
    // fabricated-market-data defect fixed in api_bridge.py on 2026-09-09.
    // Consumers must handle "no price yet" rather than being handed a fiction.
    tickerData: {},
    feed: null,
    currentPrice: 0,
    changePercent: 0,
    pnl: 0,
    unrealizedPnl: 0,
    totalPnl: 0,
    marginDeployed: 0,
    marginRoi: 0,
    accountRoi: 0,
    equity: 100000.00,
    openPositionsCount: 0,
    positionsDetail: [],
    trades: [],
    aiConfidence: 0,
    riskStatus: "ACTIVE",
    isWsConnected: false,
    aiCommentary: "System armed. Analyzing market structure...",
    lastPingTime: Date.now(),
    tradingMode: 'paper',   // default safe: paper until backend confirms live
    sentiment: { score: 0.0, label: 'Neutral', top_headlines: [] },

    setTickerData: (data) => set((state) => ({ tickerData: { ...state.tickerData, ...(typeof data === 'function' ? data(state.tickerData) : data) } })),
    setCurrentPrice: (price) => set((state) => ({ currentPrice: typeof price === 'function' ? price(state.currentPrice) : price })),
    setChangePercent: (chp) => set((state) => ({ changePercent: typeof chp === 'function' ? chp(state.changePercent) : chp })),
    setPnl: (pnl) => set((state) => ({ pnl: typeof pnl === 'function' ? pnl(state.pnl) : pnl })),
    setUnrealizedPnl: (pnl) => set((state) => ({ unrealizedPnl: typeof pnl === 'function' ? pnl(state.unrealizedPnl) : pnl })),
    setTotalPnl: (pnl) => set((state) => ({ totalPnl: typeof pnl === 'function' ? pnl(state.totalPnl) : pnl })),
    setMarginDeployed: (val) => set((state) => ({ marginDeployed: typeof val === 'function' ? val(state.marginDeployed) : val })),
    setMarginRoi: (val) => set((state) => ({ marginRoi: typeof val === 'function' ? val(state.marginRoi) : val })),
    setAccountRoi: (val) => set((state) => ({ accountRoi: typeof val === 'function' ? val(state.accountRoi) : val })),
    setEquity: (equity) => set((state) => ({ equity: typeof equity === 'function' ? equity(state.equity) : equity })),
    setOpenPositionsCount: (count) => set({ openPositionsCount: count }),
    setPositionsDetail: (positions) => set({ positionsDetail: positions }),
    setTrades: (trades) => set((state) => ({ trades: typeof trades === 'function' ? trades(state.trades) : trades })),
    setAiConfidence: (confidence) => set((state) => ({ aiConfidence: typeof confidence === 'function' ? confidence(state.aiConfidence) : confidence })),
    setRiskStatus: (status) => set((state) => ({ riskStatus: typeof status === 'function' ? status(state.riskStatus) : status })),
    setIsWsConnected: (connected) => set((state) => ({ isWsConnected: typeof connected === 'function' ? connected(state.isWsConnected) : connected })),
    setAiCommentary: (commentary) => set((state) => ({ aiCommentary: typeof commentary === 'function' ? commentary(state.aiCommentary) : commentary })),
    setLastPingTime: (time) => set((state) => ({ lastPingTime: typeof time === 'function' ? time(state.lastPingTime) : time })),
    setTradingMode: (mode) => set({ tradingMode: mode }),  // Fix 7

    ws: null,
    connectWs: (urlSymbol: string) => {
        const currentWs = get().ws;
        if (currentWs && (currentWs.readyState === WebSocket.OPEN || currentWs.readyState === WebSocket.CONNECTING)) {
            return; // Connection is already active, don't tear it down!
        }
        if (currentWs) {
            currentWs.onclose = null;
            currentWs.onmessage = null;
            currentWs.onerror = null;
            currentWs.close();
        }

        // The backend requires a session token on /ws/live (a WebSocket
        // handshake can't carry our httpOnly cookie — different origin,
        // and browsers don't attach custom headers to WS connections
        // anyway), so fetch one from our own server-side route first.
        fetch('/api/ws-token')
            .then((res) => (res.ok ? res.json() : Promise.reject(new Error('not authenticated'))))
            .then(({ token }: { token: string }) => {
                // Another connectWs() call may have already succeeded while
                // this fetch was in flight — don't open a duplicate socket.
                const existing = get().ws;
                if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
                    return;
                }

                const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
                const isProd = process.env.NODE_ENV === 'production';
                const wsUrl = isProd
                    ? `wss://${typeof window !== 'undefined' ? window.location.host : 'localhost'}/ws/live?token=${encodeURIComponent(token)}`
                    : `ws://${host}:8000/ws/live?token=${encodeURIComponent(token)}`;

                openSocket(wsUrl);
            })
            .catch(() => {
                // Not logged in (yet) or the token endpoint failed — the
                // dashboard's own auth gate handles redirecting to login;
                // there's nothing useful to connect to without a session.
            });

        function openSocket(wsUrl: string) {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                if (reconnectAttempts > 0) {
                    toast.success('Live connection restored.');
                }
                reconnectAttempts = 0;
                set({ isWsConnected: true, ws });
            };

            ws.onmessage = (event) => {
                if (get().ws !== ws) return;

                try {
                    const data = JSON.parse(event.data);

                    get().setLastPingTime(Date.now());

                    // Feed health first: everything below is only meaningful
                    // in the context of whether the feed can be trusted.
                    if (data.feed) pendingUpdates.feed = data.feed as FeedStatus;

                    if (data.NIFTY || data["NSE:NIFTY50-INDEX"]) {
                        const nVal = data.NIFTY || data["NSE:NIFTY50-INDEX"];
                        pendingTickerUpdates.NIFTY = nVal;
                        pendingTickerUpdates["NSE:NIFTY50-INDEX"] = nVal;
                        if (data.SENSEX || data["BSE:SENSEX-INDEX"]) {
                            const sVal = data.SENSEX || data["BSE:SENSEX-INDEX"];
                            pendingTickerUpdates.SENSEX = sVal;
                            pendingTickerUpdates["BSE:SENSEX-INDEX"] = sVal;
                        }
                        if (data.BANKNIFTY || data["NSE:NIFTYBANK-INDEX"]) {
                            const bVal = data.BANKNIFTY || data["NSE:NIFTYBANK-INDEX"];
                            pendingTickerUpdates.BANKNIFTY = bVal;
                            pendingTickerUpdates["NSE:NIFTYBANK-INDEX"] = bVal;
                        }
                    }

                    const symTick = data[urlSymbol] || data[urlSymbol.replace('NSE:', '').replace('BSE:', '').replace('-INDEX', '')] || data.NIFTY;
                    if (symTick) {
                        pendingUpdates.currentPrice = symTick.lp;
                        pendingUpdates.changePercent = symTick.chp;
                    }

                    // ── Real-time P&L fields (from backend broadcaster) ──────────
                    if (data.pnl !== undefined)                  pendingUpdates.pnl                = data.pnl;
                    if (data.unrealized_pnl !== undefined)       pendingUpdates.unrealizedPnl      = data.unrealized_pnl;
                    if (data.total_pnl !== undefined)            pendingUpdates.totalPnl           = data.total_pnl;
                    if (data.margin_deployed !== undefined)      pendingUpdates.marginDeployed     = data.margin_deployed;
                    if (data.margin_roi !== undefined)           pendingUpdates.marginRoi          = data.margin_roi;
                    if (data.account_roi !== undefined)          pendingUpdates.accountRoi         = data.account_roi;
                    if (data.equity !== undefined)               pendingUpdates.equity             = data.equity;
                    if (data.open_positions_count !== undefined) pendingUpdates.openPositionsCount = data.open_positions_count;
                    if (data.positions_detail)                   pendingUpdates.positionsDetail    = data.positions_detail;
                    if (data.trades)                             pendingUpdates.trades             = data.trades;

                    if (data.signalsData && data.signalsData.confidence !== undefined) {
                        pendingUpdates.aiConfidence = data.signalsData.confidence;
                    }

                    // Fix 7: trading mode from WS payload
                    if (data.trading_mode !== undefined) {
                        pendingUpdates.tradingMode = data.trading_mode === 'live' ? 'live' : 'paper';
                    }

                    // Fix 2: sentiment from WS payload
                    if (data.sentiment !== undefined) {
                        pendingUpdates.sentiment = data.sentiment;
                    }

                    // Throttle React state updates to 1 animation frame (~16ms)
                    if (typeof window !== 'undefined' && !rAF_id) {
                        rAF_id = window.requestAnimationFrame(() => {
                            const state = get();
                            set({
                                ...pendingUpdates,
                                tickerData: Object.keys(pendingTickerUpdates).length > 0
                                    ? { ...state.tickerData, ...pendingTickerUpdates }
                                    : state.tickerData
                            });
                            pendingUpdates = {};
                            pendingTickerUpdates = {};
                            rAF_id = null;
                        });
                    } else if (typeof window === 'undefined') {
                        set({
                            ...pendingUpdates,
                            tickerData: Object.keys(pendingTickerUpdates).length > 0
                                ? { ...get().tickerData, ...pendingTickerUpdates }
                                : get().tickerData
                        });
                        pendingUpdates = {};
                        pendingTickerUpdates = {};
                    }
                } catch {
                    // Ignore parse errors
                }
            };

            ws.onclose = () => {
                if (get().ws === ws) {
                    set({ isWsConnected: false, ws: null });
                }
                reconnectAttempts++;
                const backoffTime = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 30000);
                if (reconnectAttempts === 1) {
                    toast.error('Connection lost. Reconnecting...');
                }
                setTimeout(() => {
                    if (!get().isWsConnected) {
                        get().connectWs(urlSymbol);
                    }
                }, backoffTime);
            };
        }

        // ── Active HTTP Polling Fallback (syncs every 3s) ───────────────────
        if (typeof window !== 'undefined') {
            const pollState = async () => {
                try {
                    const res = await fetch('/api/state', { cache: 'no-store' });
                    if (res.ok) {
                        const s = await res.json();
                        set(state => ({
                            equity: s.capital ?? state.equity,
                            pnl: s.day_pnl ?? state.pnl,
                            trades: s.trades ?? state.trades,
                            openPositionsCount: s.open_positions ?? state.openPositionsCount
                        }));
                    }
                } catch {}
            };
            pollState();
            const pollTimer = setInterval(pollState, 3000);
            (window as any).__liveStatePollTimer = pollTimer;
        }
    },

    disconnectWs: () => {
        if (typeof window !== 'undefined' && (window as any).__liveStatePollTimer) {
            clearInterval((window as any).__liveStatePollTimer);
            (window as any).__liveStatePollTimer = null;
        }
        const currentWs = get().ws;
        if (currentWs) {
            currentWs.onclose = null;
            currentWs.onmessage = null;
            currentWs.close();
            set({ ws: null, isWsConnected: false });
        }
    }
}));
