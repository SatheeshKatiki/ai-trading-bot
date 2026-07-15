import { create } from 'zustand';

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
    
    ws: null,
    connectWs: (urlSymbol: string) => {
        const currentWs = get().ws;
        if (currentWs) {
            currentWs.onclose = null;
            currentWs.close();
        }

        const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
        const isProd = process.env.NODE_ENV === 'production';
        const wsUrl = isProd 
            ? `wss://${typeof window !== 'undefined' ? window.location.host : 'localhost'}/ws/live` 
            : `ws://${host}:8000/ws/live`;
            
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            set({ isWsConnected: true, ws });
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.NIFTY) {
                    set((state) => ({
                        tickerData: {
                            ...state.tickerData,
                            NIFTY: data.NIFTY,
                            SENSEX: data.SENSEX || state.tickerData.SENSEX,
                            BANKNIFTY: data.BANKNIFTY || state.tickerData.BANKNIFTY
                        }
                    }));
                }
                
                if (data[urlSymbol]) {
                    set({
                        currentPrice: data[urlSymbol].lp,
                        changePercent: data[urlSymbol].chp
                    });
                }
                
                const updates: Partial<LiveMarketState> = {};
                if (data.pnl !== undefined) updates.pnl = data.pnl;
                if (data.equity !== undefined) updates.equity = data.equity;
                if (data.trades) updates.trades = data.trades;
                
                if (data.signalsData && data.signalsData.confidence !== undefined) {
                    updates.aiConfidence = data.signalsData.confidence;
                    updates.riskStatus = data.signalsData.status;
                }
                
                if (Object.keys(updates).length > 0) {
                    set(updates);
                }
            } catch (err) {
                // Ignore parse errors
            }
        };
        
        ws.onclose = () => {
            set({ isWsConnected: false, ws: null });
            // Attempt reconnect after 3 seconds
            setTimeout(() => get().connectWs(urlSymbol), 3000);
        };
    },
    
    disconnectWs: () => {
        const currentWs = get().ws;
        if (currentWs) {
            currentWs.onclose = null; // Prevent reconnect loop
            currentWs.close();
            set({ ws: null, isWsConnected: false });
        }
    }
}));
