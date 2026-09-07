import { create } from 'zustand';

interface LiveSettingsState {
    tradingMode: string;
    autoMode: boolean;
    strategy: string;
    inputMode: 'lots' | 'qty';
    quantity: number;
    // number | string: NumberInput is a fully-controlled input, so the store
    // must be able to hold an in-progress typed value like "0." or "" —
    // rounding those to number on every keystroke would make it impossible
    // to type a decimal point or clear the field.
    stoploss: number | string;
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
    // number | string on the numeric fields for the same reason as
    // `stoploss` above — each is bound to a fully-controlled NumberInput.
    enablePyramiding: boolean;
    scalePct: number | string;
    maxScales: number | string;
    trailingSl: boolean;
    trailTrigger: number | string;
    trailOffset: number | string;
    donchianPeriod: number | string;
    maxDailyLossPct: number | string;
    maxDailyTrades: number | string;

    // Actions
    setTradingMode: (mode: string) => void;
    setAutoMode: (mode: boolean) => void;
    setStrategy: (strategy: string) => void;
    setInputMode: (mode: 'lots' | 'qty') => void;
    setQuantity: (qty: number) => void;
    setStoploss: (sl: number | string) => void;
    setTimeframe: (tf: string) => void;
    setLotSizes: (lotSizes: Record<string, number>) => void;
    setFilters: (filters: Partial<LiveSettingsState['filters']>) => void;
    setFilter: (key: keyof LiveSettingsState['filters'], value: boolean) => void;

    setEnablePyramiding: (value: boolean) => void;
    setScalePct: (value: number | string) => void;
    setMaxScales: (value: number | string) => void;
    setTrailingSl: (value: boolean) => void;
    setTrailTrigger: (value: number | string) => void;
    setTrailOffset: (value: number | string) => void;
    setDonchianPeriod: (value: number | string) => void;
    setMaxDailyLossPct: (value: number | string) => void;
    setMaxDailyTrades: (value: number | string) => void;
}

export const useLiveSettingsStore = create<LiveSettingsState>((set) => ({
    tradingMode: 'paper',
    autoMode: true,
    strategy: 'ema9_rsi_momentum',
    inputMode: 'lots',
    quantity: 0,
    stoploss: 0.6,
    timeframe: "5 Min",
    lotSizes: { NIFTY: 65, BANKNIFTY: 15, FINNIFTY: 25, SENSEX: 10, MIDCPNIFTY: 50 },

    filters: {
        enable_ema_filter: false,
        enable_volume_filter: false,
        enable_adx_filter: false,
        enable_vwap_filter: false,
        enable_rsi_filter: false,
        enable_squeeze_filter: true,
        enable_extension_filter: true,
        enable_cpr_filter: true,
        enable_aggression_filter: true
    },

    enablePyramiding: true,
    scalePct: 0.2,
    maxScales: 2,
    trailingSl: true,
    trailTrigger: 0.6,
    trailOffset: 0.35,
    donchianPeriod: 10,
    maxDailyLossPct: 3.0,
    maxDailyTrades: 3,

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
