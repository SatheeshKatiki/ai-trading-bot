import { create } from 'zustand';

interface LiveSettingsState {
    tradingMode: string;
    autoMode: boolean;
    strategy: string;
    inputMode: 'lots' | 'qty';
    quantity: number;
    stoploss: number;
    timeframe: string;
    lotSizes: Record<string, number>;

    // Filters
    filters: {
        enable_ema_filter: boolean;
        enable_volume_filter: boolean;
        enable_adx_filter: boolean;
        enable_vwap_filter: boolean;
        enable_rsi_filter: boolean;
        enable_squeeze_filter: boolean;
        enable_extension_filter: boolean;
        enable_cpr_filter: boolean;
        enable_aggression_filter: boolean;
    };

    // Engine Settings
    enablePyramiding: boolean;
    scalePct: number;
    maxScales: number;
    trailingSl: boolean;
    trailTrigger: number;
    trailOffset: number;
    donchianPeriod: number;
    maxDailyLossPct: number;
    maxDailyTrades: number;

    // Actions
    setTradingMode: (mode: string) => void;
    setAutoMode: (mode: boolean) => void;
    setStrategy: (strategy: string) => void;
    setInputMode: (mode: 'lots' | 'qty') => void;
    setQuantity: (qty: number) => void;
    setStoploss: (sl: number) => void;
    setTimeframe: (tf: string) => void;
    setLotSizes: (lotSizes: Record<string, number>) => void;
    setFilters: (filters: Partial<LiveSettingsState['filters']>) => void;
    setFilter: (key: keyof LiveSettingsState['filters'], value: boolean) => void;

    setEnablePyramiding: (value: boolean) => void;
    setScalePct: (value: number) => void;
    setMaxScales: (value: number) => void;
    setTrailingSl: (value: boolean) => void;
    setTrailTrigger: (value: number) => void;
    setTrailOffset: (value: number) => void;
    setDonchianPeriod: (value: number) => void;
    setMaxDailyLossPct: (value: number) => void;
    setMaxDailyTrades: (value: number) => void;
}

export const useLiveSettingsStore = create<LiveSettingsState>((set) => ({
    tradingMode: 'paper',
    autoMode: true,
    strategy: 'institutional_momentum',
    inputMode: 'lots',
    quantity: 0,
    stoploss: 1.2,
    timeframe: "5 Min",
    lotSizes: { NIFTY: 65, BANKNIFTY: 15, FINNIFTY: 25, SENSEX: 10, MIDCPNIFTY: 50 },

    filters: {
        enable_ema_filter: true,
        enable_volume_filter: false,
        enable_adx_filter: false,
        enable_vwap_filter: true,
        enable_rsi_filter: true,
        enable_squeeze_filter: false,
        enable_extension_filter: false,
        enable_cpr_filter: false,
        enable_aggression_filter: false
    },

    enablePyramiding: false,
    scalePct: 0.5,
    maxScales: 3,
    trailingSl: true,
    trailTrigger: 0.8,
    trailOffset: 0.2,
    donchianPeriod: 20,
    maxDailyLossPct: 2.0,
    maxDailyTrades: 0,

    setTradingMode: (mode) => set({ tradingMode: mode }),
    setAutoMode: (mode) => set({ autoMode: mode }),
    setStrategy: (strategy) => set({ strategy }),
    setInputMode: (mode) => set({ inputMode: mode }),
    setQuantity: (qty) => set({ quantity: qty }),
    setStoploss: (sl) => set({ stoploss: sl }),
    setTimeframe: (tf) => set({ timeframe: tf }),
    setLotSizes: (lotSizes) => set({ lotSizes }),

    setFilters: (newFilters) => set((state) => ({ filters: { ...state.filters, ...newFilters } })),
    setFilter: (key, value) => set((state) => ({ filters: { ...state.filters, [key]: value } })),

    setEnablePyramiding: (value) => set({ enablePyramiding: value }),
    setScalePct: (value) => set({ scalePct: value }),
    setMaxScales: (value) => set({ maxScales: value }),
    setTrailingSl: (value) => set({ trailingSl: value }),
    setTrailTrigger: (value) => set({ trailTrigger: value }),
    setTrailOffset: (value) => set({ trailOffset: value }),
    setDonchianPeriod: (value) => set({ donchianPeriod: value }),
    setMaxDailyLossPct: (value) => set({ maxDailyLossPct: value }),
    setMaxDailyTrades: (value) => set({ maxDailyTrades: value }),
}));
