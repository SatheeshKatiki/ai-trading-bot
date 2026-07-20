import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface ChartSettingsState {
    ema1Length: number;
    ema1Color: string;
    ema1LineWidth: number;
    ema1LineStyle: number; // 0 = Solid, 1 = Dotted, 2 = Dashed, 3 = LargeDashed

    ema2Length: number;
    ema2Color: string;
    ema2LineWidth: number;
    ema2LineStyle: number;

    showVolume: boolean;

    showRsi: boolean;
    rsiLength: number;
    rsiColor: string;
    rsiLineWidth: number;
    rsiLineStyle: number;
    rsiOverbought: number;
    rsiOversold: number;

    showSmartTrend: boolean;
    // Smart Trend Colors
    bullishSurgeColor: string;
    bearishSurgeColor: string;
    bullishNormalColor: string;
    bearishNormalColor: string;
    chopColor: string;

    // Actions
    setEma1Length: (val: number) => void;
    setEma1Color: (val: string) => void;
    setEma1LineWidth: (val: number) => void;
    setEma1LineStyle: (val: number) => void;

    setEma2Length: (val: number) => void;
    setEma2Color: (val: string) => void;
    setEma2LineWidth: (val: number) => void;
    setEma2LineStyle: (val: number) => void;

    setShowVolume: (val: boolean) => void;

    setShowRsi: (val: boolean) => void;
    setRsiLength: (val: number) => void;
    setRsiColor: (val: string) => void;
    setRsiLineWidth: (val: number) => void;
    setRsiLineStyle: (val: number) => void;
    setRsiOverbought: (val: number) => void;
    setRsiOversold: (val: number) => void;

    setShowSmartTrend: (val: boolean) => void;
    setBullishSurgeColor: (val: string) => void;
    setBearishSurgeColor: (val: string) => void;
    setBullishNormalColor: (val: string) => void;
    setBearishNormalColor: (val: string) => void;
    setChopColor: (val: string) => void;
}

export const useChartSettingsStore = create<ChartSettingsState>()(
    persist(
        (set) => ({
            ema1Length: 9,
            ema1Color: '#2962FF',
            ema1LineWidth: 2,
            ema1LineStyle: 0,

            ema2Length: 21,
            ema2Color: '#FF6D00',
            ema2LineWidth: 2,
            ema2LineStyle: 0,

            showVolume: true,

            showRsi: false,
            rsiLength: 14,
            rsiColor: '#7E57C2',
            rsiLineWidth: 2,
            rsiLineStyle: 0,
            rsiOverbought: 70,
            rsiOversold: 30,

            showSmartTrend: false,

            bullishSurgeColor: '#7C3AED',
            bearishSurgeColor: '#FF007F',
            bullishNormalColor: '#00FF00',
            bearishNormalColor: '#FF0000',
            chopColor: '#6B7280',

            setEma1Length: (val) => set({ ema1Length: val }),
            setEma1Color: (val) => set({ ema1Color: val }),
            setEma1LineWidth: (val) => set({ ema1LineWidth: val }),
            setEma1LineStyle: (val) => set({ ema1LineStyle: val }),

            setEma2Length: (val) => set({ ema2Length: val }),
            setEma2Color: (val) => set({ ema2Color: val }),
            setEma2LineWidth: (val) => set({ ema2LineWidth: val }),
            setEma2LineStyle: (val) => set({ ema2LineStyle: val }),

            setShowVolume: (val) => set({ showVolume: val }),

            setShowRsi: (val) => set({ showRsi: val }),
            setRsiLength: (val) => set({ rsiLength: val }),
            setRsiColor: (val) => set({ rsiColor: val }),
            setRsiLineWidth: (val) => set({ rsiLineWidth: val }),
            setRsiLineStyle: (val) => set({ rsiLineStyle: val }),
            setRsiOverbought: (val) => set({ rsiOverbought: val }),
            setRsiOversold: (val) => set({ rsiOversold: val }),

            setShowSmartTrend: (val) => set({ showSmartTrend: val }),
            setBullishSurgeColor: (val) => set({ bullishSurgeColor: val }),
            setBearishSurgeColor: (val) => set({ bearishSurgeColor: val }),
            setBullishNormalColor: (val) => set({ bullishNormalColor: val }),
            setBearishNormalColor: (val) => set({ bearishNormalColor: val }),
            setChopColor: (val) => set({ chopColor: val }),
        }),
        {
            name: 'chart-settings-storage',
        }
    )
);
