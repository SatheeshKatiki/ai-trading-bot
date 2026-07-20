import { create } from 'zustand';
import { toast } from 'sonner';

let reconnectAttempts = 0;
let rAF_id: number | null = null;
let pendingUpdates: Partial<LiveMarketState> = {};
let pendingTickerUpdates: Record<string, TickerData> = {};

export interface TickerData {
    lp: number;
    chp: number;
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

export interface LiveMarketState {
    tickerData: Record<string, TickerData>;
    currentPrice: number;
    changePercent: number;
    pnl: number;
    equity: number;
    trades: Trade[];
    aiConfidence: number;
    riskStatus: string;
    isWsConnected: boolean;
    aiCommentary: string;
    lastPingTime: number;
    
    // Actions
    setTickerData: (data: Record<string, TickerData> | ((prev: Record<string, TickerData>) => Record<string, TickerData>)) => void;
    setCurrentPrice: (price: number | ((prev: number) => number)) => void;
    setChangePercent: (chp: number | ((prev: number) => number)) => void;
    setPnl: (pnl: number | ((prev: number) => number)) => void;
    setEquity: (equity: number | ((prev: number) => number)) => void;
    setTrades: (trades: Trade[] | ((prev: Trade[]) => Trade[])) => void;
    setAiConfidence: (confidence: number | ((prev: number) => number)) => void;
    setRiskStatus: (status: string | ((prev: string) => string)) => void;
    setIsWsConnected: (connected: boolean | ((prev: boolean) => boolean)) => void;
    setAiCommentary: (commentary: string | ((prev: string) => string)) => void;
    setLastPingTime: (time: number | ((prev: number) => number)) => void;
    
    // WebSocket
    ws: WebSocket | null;
    connectWs: (urlSymbol: string) => void;
    disconnectWs: () => void;
}

export const useLiveMarketStore = create<LiveMarketState>((set, get) => ({
    tickerData: {
        NIFTY: { lp: 23820.35, chp: -1.49 },
        SENSEX: { lp: 76015.28, chp: -1.70 },
        BANKNIFTY: { lp: 51000.00, chp: 0.0 }
    },
    currentPrice: 0,
    changePercent: 0,
    pnl: 0,
    equity: 100000.00,
    trades: [],
    aiConfidence: 0,
    riskStatus: "ACTIVE",
    isWsConnected: false,
    aiCommentary: "System armed. Analyzing market structure...",
    lastPingTime: Date.now(),
    
    setTickerData: (data) => set((state) => ({ tickerData: { ...state.tickerData, ...(typeof data === 'function' ? data(state.tickerData) : data) } })),
    setCurrentPrice: (price) => set((state) => ({ currentPrice: typeof price === 'function' ? price(state.currentPrice) : price })),
    setChangePercent: (chp) => set((state) => ({ changePercent: typeof chp === 'function' ? chp(state.changePercent) : chp })),
    setPnl: (pnl) => set((state) => ({ pnl: typeof pnl === 'function' ? pnl(state.pnl) : pnl })),
    setEquity: (equity) => set((state) => ({ equity: typeof equity === 'function' ? equity(state.equity) : equity })),
    setTrades: (trades) => set((state) => ({ trades: typeof trades === 'function' ? trades(state.trades) : trades })),
    setAiConfidence: (confidence) => set((state) => ({ aiConfidence: typeof confidence === 'function' ? confidence(state.aiConfidence) : confidence })),
    setRiskStatus: (status) => set((state) => ({ riskStatus: typeof status === 'function' ? status(state.riskStatus) : status })),
    setIsWsConnected: (connected) => set((state) => ({ isWsConnected: typeof connected === 'function' ? connected(state.isWsConnected) : connected })),
    setAiCommentary: (commentary) => set((state) => ({ aiCommentary: typeof commentary === 'function' ? commentary(state.aiCommentary) : commentary })),
    setLastPingTime: (time) => set((state) => ({ lastPingTime: typeof time === 'function' ? time(state.lastPingTime) : time })),
    
    ws: null,
    connectWs: (urlSymbol: string) => {
        const currentWs = get().ws;
        if (currentWs) {
            currentWs.onclose = null;
            currentWs.onmessage = null; // Prevent ghost messages
            currentWs.onerror = null;
            currentWs.close();
        }

        const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
        const isProd = process.env.NODE_ENV === 'production';
        const wsUrl = isProd 
            ? `wss://${typeof window !== 'undefined' ? window.location.host : 'localhost'}/ws/live` 
            : `ws://${host}:8000/ws/live`;
            
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            if (reconnectAttempts > 0) {
                toast.success('Live connection restored.');
            }
            reconnectAttempts = 0;
            set({ isWsConnected: true, ws });
        };
        
        ws.onmessage = (event) => {
            // Ignore messages from ghost connections if a new WS was created
            if (get().ws !== ws) return;
            
            try {
                const data = JSON.parse(event.data);
                
                // Update ping time
                get().setLastPingTime(Date.now());
                
                if (data.NIFTY) {
                    pendingTickerUpdates.NIFTY = data.NIFTY;
                    if (data.SENSEX) pendingTickerUpdates.SENSEX = data.SENSEX;
                    if (data.BANKNIFTY) pendingTickerUpdates.BANKNIFTY = data.BANKNIFTY;
                }
                
                if (data[urlSymbol]) {
                    pendingUpdates.currentPrice = data[urlSymbol].lp;
                    pendingUpdates.changePercent = data[urlSymbol].chp;
                }
                
                if (data.pnl !== undefined) pendingUpdates.pnl = data.pnl;
                if (data.equity !== undefined) pendingUpdates.equity = data.equity;
                if (data.trades) pendingUpdates.trades = data.trades;
                
                if (data.signalsData && data.signalsData.confidence !== undefined) {
                    pendingUpdates.aiConfidence = data.signalsData.confidence;
                    // Fix: Do not overwrite riskStatus with AI Signal Status
                }
                
                // Throttle React state updates to 1 frame (approx 16ms)
                if (typeof window !== 'undefined' && !rAF_id) {
                    rAF_id = window.requestAnimationFrame(() => {
                        const state = get();
                        set({
                            ...pendingUpdates,
                            tickerData: Object.keys(pendingTickerUpdates).length > 0 ? {
                                ...state.tickerData,
                                ...pendingTickerUpdates
                            } : state.tickerData
                        });
                        
                        pendingUpdates = {};
                        pendingTickerUpdates = {};
                        rAF_id = null;
                    });
                } else if (typeof window === 'undefined') {
                    // Fallback for SSR/Node environment
                    set({
                        ...pendingUpdates,
                        tickerData: Object.keys(pendingTickerUpdates).length > 0 ? {
                            ...get().tickerData,
                            ...pendingTickerUpdates
                        } : get().tickerData
                    });
                    pendingUpdates = {};
                    pendingTickerUpdates = {};
                }
            } catch (err) {
                // Ignore parse errors
            }
        };
        
        ws.onclose = () => {
            if (get().ws === ws) {
                set({ isWsConnected: false, ws: null });
            }
            
            // Exponential backoff
            reconnectAttempts++;
            const backoffTime = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 30000); // 1s, 2s, 4s... max 30s
            
            if (reconnectAttempts === 1) {
                toast.error('Connection lost. Reconnecting...');
            }
            
            setTimeout(() => {
                if (!get().isWsConnected) {
                    get().connectWs(urlSymbol);
                }
            }, backoffTime);
        };
    },
    
    disconnectWs: () => {
        const currentWs = get().ws;
        if (currentWs) {
            currentWs.onclose = null; // Prevent reconnect loop
            currentWs.onmessage = null;
            currentWs.close();
            set({ ws: null, isWsConnected: false });
        }
    }
}));
