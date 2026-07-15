import React, { useState, useEffect } from 'react';
import { Settings, Shield, Target, Clock, ChevronDown, Package, Layers } from 'lucide-react';
import { NumberInput } from "@/components/number-input";
import { useLiveSettingsStore } from '@/store/useLiveSettingsStore';
import { toast } from 'sonner';

interface TradeActionPanelProps {
    urlSymbol: string;
    defaultBaseQty: number;
}

export function TradeActionPanel({ urlSymbol, defaultBaseQty }: TradeActionPanelProps) {
    const {
        tradingMode, setTradingMode,
        strategy, setStrategy,
        inputMode, setInputMode,
        quantity, setQuantity,
        stoploss, setStoploss,
        timeframe, setTimeframe,
        filters, setFilter,
        enablePyramiding, setEnablePyramiding,
        scalePct, setScalePct,
        maxScales, setMaxScales,
        trailingSl, setTrailingSl,
        trailTrigger, setTrailTrigger,
        trailOffset, setTrailOffset,
        donchianPeriod, setDonchianPeriod,
        maxDailyLossPct, setMaxDailyLossPct,
        maxDailyTrades, setMaxDailyTrades
    } = useLiveSettingsStore();

    const strategyNames: Record<string, string> = {
        "ema_rsi": "EMA + RSI (Classic)",
        "enhanced_ai": "Enhanced AI Strategy",
        "advanced_ai": "Advanced AI/ML",
        "premium": "Premium Options Alpha",
        "institutional_momentum": "Institutional Momentum Breakout",
        "ema_crossover": "Ultra-EMA Crossover Strategy",
        "meta_agent_swarm": "Meta-Agent AI Swarm (5 Brains)",
        "ultra_meta_dip_swarm": "Ultra Meta-Dip Swarm (6 Brains)",
        "buy_the_dip": "Buy the Dip (Mean Reversion)",
    };

    // Available Strategies State
    const [availableStrategies, setAvailableStrategies] = useState<{name: string, description?: string}[]>([]);

    useEffect(() => {
        const fetchStrategies = async () => {
            try {
                const res = await fetch('/api/strategies');
                if (res.ok) {
                    const data = await res.json();
                    if (data.strategies) {
                        // Backend might return dict or list of objects
                        const formatted = Array.isArray(data.strategies) 
                            ? data.strategies.map((s: any) => typeof s === 'string' ? { name: s } : s)
                            : Object.keys(data.strategies).map(key => ({ name: key, ...data.strategies[key] }));
                        setAvailableStrategies(formatted);
                        // Make sure the active strategy exists in the backend list, otherwise default to first
                        if (formatted.length > 0 && !formatted.find(s => s.name === strategy)) {
                            setStrategy(formatted[0].name);
                        }
                    }
                }
            } catch (error) {
                console.error("Failed to fetch available strategies:", error);
            }
        };
        fetchStrategies();
    }, []);

    // Handle Strategy Change
    const handleStrategyChange = async (newStrategy: string) => {
        setStrategy(newStrategy);
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_strategy: newStrategy })
            });
            toast.success(`Strategy updated to ${newStrategy.replace('_', ' ').toUpperCase()}`);
        } catch (error) {
            console.error("Failed to update strategy:", error);
            toast.error("Failed to update strategy");
        }
    };

    // Handle Stoploss Change
    const handleStoplossChange = async (val: string) => {
        let cleanVal = val.replace(/^0+(?=\d)/, '');
        setStoploss(cleanVal as any);

        const newSl = parseFloat(cleanVal);
        if (!isNaN(newSl)) {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stoploss_pct: newSl })
                });
            } catch (error) {
                console.error("Failed to update stoploss:", error);
            }
        }
    };

    // Handle Quantity Change
    const getBaseQty = (sym: string) => {
        if (sym.includes('BANKNIFTY')) return 15;
        if (sym.includes('NIFTY')) return 25;
        if (sym.includes('SENSEX')) return 10;
        return 1;
    };
    
    const baseQty = getBaseQty(urlSymbol);
    const displayValue = quantity === 0 ? '' : (inputMode === 'lots' ? Number((quantity / baseQty).toFixed(2)) : quantity);

    const handleValueChange = (val: number) => {
        const newQty = inputMode === 'lots' ? val * baseQty : val;
        handleQuantityChange(newQty);
    };

    const handleQuantityChange = async (newQty: number) => {
        setQuantity(newQty);
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ quantity: newQty })
            });
        } catch (error) {
            console.error("Failed to update quantity:", error);
        }
    };

    const handleFilterChange = async (key: string, value: boolean) => {
        setFilter(key as any, value);
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [key]: value })
            });
        } catch (error) {
            console.error(`Failed to update filter ${key}:`, error);
        }
    };

    const handleAdvancedSettingChange = async (key: string, value: any, setter: (val: any) => void) => {
        setter(value);
        let apiPayload: any = {};
        
        switch (key) {
            case 'enablePyramiding': apiPayload = { enable_pyramiding: value }; break;
            case 'scalePct': apiPayload = { scale_pct: value }; break;
            case 'maxScales': apiPayload = { max_scales: value }; break;
            case 'trailingSl': apiPayload = { trailing_sl: value }; break;
            case 'trailTrigger': apiPayload = { trail_trigger: value }; break;
            case 'trailOffset': apiPayload = { trail_offset: value }; break;
            case 'donchianPeriod': apiPayload = { donchian_period: value }; break;
            case 'maxDailyLossPct': apiPayload = { max_daily_loss_pct: value }; break;
            case 'maxDailyTrades': apiPayload = { max_daily_trades: value }; break;
        }

        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(apiPayload)
            });
        } catch (error) {
            console.error(`Failed to update advanced setting ${key}:`, error);
        }
    };

    return (
        <div className="glass-card rounded-xl border border-border/20 overflow-hidden flex flex-col h-full bg-card shadow-lg shadow-black/5">
            <div className="p-4 border-b border-border/50 bg-muted/20 flex items-center justify-between">
                <h3 className="font-display font-bold text-sm text-foreground flex items-center gap-2">
                    <Settings className="w-4 h-4 text-primary" />
                    Trade Actions & Config
                </h3>
            </div>
            
            {/* --- CORE SETTINGS ROW --- */}
            <div className="p-4 flex flex-wrap items-center gap-4 bg-background border-b border-border/30 w-full relative z-30">
                {/* Trading Mode Dropdown */}
                <div className="relative group">
                    <select
                        value={tradingMode}
                        onChange={(e) => {
                            setTradingMode(e.target.value);
                            localStorage.setItem('tradingMode', e.target.value);
                            toast.info(`Switched to ${e.target.value.toUpperCase()} mode`);
                        }}
                        className={`cursor-pointer w-[120px] pl-3 pr-10 h-10 appearance-none rounded-xl text-xs font-bold focus:outline-none focus:ring-1 transition-all ${tradingMode === 'live' ? 'bg-destructive/10 text-destructive border-destructive/30 focus:ring-destructive focus:border-destructive' : 'bg-primary/10 text-primary border-primary/30 focus:ring-primary focus:border-primary'}`}
                        style={{ backgroundImage: 'none' }}
                    >
                        <option value="paper" className="font-bold">Paper Trade</option>
                        <option value="live" className="font-bold text-destructive">Live Trade</option>
                    </select>
                    <ChevronDown className={`w-4 h-4 absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none z-10 transition-colors ${tradingMode === 'live' ? 'text-destructive/70 group-focus-within:text-destructive' : 'text-primary/70 group-focus-within:text-primary'}`} />
                </div>

                {/* Strategy Selector */}
                <div className="relative group flex-1">
                    <select
                        value={strategy}
                        onChange={(e) => handleStrategyChange(e.target.value)}
                        className="cursor-pointer w-full pl-3 pr-10 h-10 appearance-none rounded-xl bg-muted/30 border border-border/50 text-sm font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all truncate"
                        style={{ backgroundImage: 'none' }}
                    >
                        {availableStrategies.length > 0 ? (
                            availableStrategies.map((s, idx) => (
                                <option key={idx} value={s.name}>
                                    {strategyNames[s.name] || s.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                </option>
                            ))
                        ) : (
                            <option value={strategy}>{strategyNames[strategy] || strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
                        )}
                    </select>
                    <ChevronDown className="w-4 h-4 text-muted-foreground absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none z-10 group-focus-within:text-primary transition-colors" />
                </div>

                {/* Quantity Controls */}
                <div className="relative group flex items-center">
                    <span className="absolute -top-3 left-2 px-1 bg-background text-[10px] font-bold text-muted-foreground uppercase tracking-wider group-focus-within:text-primary transition-colors z-20">
                        {inputMode === 'lots' ? 'Lots' : 'Qty.'}
                    </span>
                    <NumberInput
                        value={displayValue}
                        onChange={(val) => handleValueChange(Number(val))}
                        min={0}
                        step={1}
                        containerClassName="w-24 h-10 rounded-xl"
                        appendContent={
                            <button
                                onClick={() => setInputMode(inputMode === 'lots' ? 'qty' : 'lots')}
                                className="flex items-center justify-center w-10 h-full border border-l-0 border-border bg-muted/20 hover:bg-muted/50 hover:text-primary transition-colors rounded-r-xl flex-shrink-0 z-10"
                                title={`Switch to ${inputMode === 'lots' ? 'Quantity' : 'Lots'}`}
                            >
                                {inputMode === 'lots' ? <Package className="w-4 h-4" /> : <Layers className="w-4 h-4" />}
                            </button>
                        }
                    />
                </div>

                {/* Stoploss Selector */}
                <div className="relative group">
                    <span className="absolute -top-3 left-2 px-1 bg-background text-[10px] font-bold text-destructive/80 uppercase tracking-wider group-focus-within:text-destructive transition-colors z-20">
                        SL %
                    </span>
                    <NumberInput
                        value={stoploss}
                        onChange={(val) => handleStoplossChange(String(val))}
                        min={0.1}
                        step={0.1}
                        suffix="%"
                        ringColor="destructive"
                        containerClassName="w-24 h-10 rounded-xl"
                    />
                </div>

                {/* Timeframe Selector */}
                <div className="relative group">
                    <Clock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 transform -translate-y-1/2 group-focus-within:text-primary transition-colors pointer-events-none z-10" />
                    <select
                        value={timeframe}
                        onChange={(e) => setTimeframe(e.target.value)}
                        className="cursor-pointer flex-1 w-full pl-10 pr-10 h-10 min-w-[110px] appearance-none rounded-xl bg-muted/30 border border-border/50 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
                        style={{ backgroundImage: 'none' }}
                    >
                        <option value="1 Min">1 Min</option>
                        <option value="3 Min">3 Min</option>
                        <option value="5 Min">5 Min</option>
                        <option value="15 Min">15 Min</option>
                        <option value="30 Min">30 Min</option>
                        <option value="1 Hour">1 Hour</option>
                        <option value="1 Week">1 Week</option>
                        <option value="1 Month">1 Month</option>
                    </select>
                    <ChevronDown className="w-4 h-4 text-muted-foreground absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none z-10 group-focus-within:text-primary transition-colors" />
                </div>
            </div>

            {/* --- FILTERS --- */}
            <div className="p-4 flex flex-wrap items-center gap-4 w-full">
                <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 border-r border-border/50 pr-4">
                    <Shield className="w-3.5 h-3.5" /> Filters
                </div>

                {[
                    { id: "enable_ema_filter", label: "EMA Trend" },
                    { id: "enable_volume_filter", label: "Volume" },
                    { id: "enable_adx_filter", label: "ADX > 25" },
                    { id: "enable_vwap_filter", label: "VWAP" },
                    { id: "enable_rsi_filter", label: "RSI Momentum" },
                    { id: "enable_squeeze_filter", label: "Squeeze" },
                    { id: "enable_extension_filter", label: "EMA Ext" },
                    { id: "enable_cpr_filter", label: "CPR Rejection" },
                    { id: "enable_aggression_filter", label: "Aggression" },
                ].map(filter => (
                    <div key={filter.id} className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id={filter.id}
                            checked={(filters as any)[filter.id]}
                            onChange={(e) => handleFilterChange(filter.id, e.target.checked)}
                            className="w-3 h-3 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                        />
                        <label htmlFor={filter.id} className={`text-[11px] font-medium cursor-pointer transition-colors ${(filters as any)[filter.id] ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                            {filter.label}
                        </label>
                    </div>
                ))}
            </div>

            {/* --- ENGINE SETTINGS --- */}
            <div className="p-4 flex flex-wrap items-center gap-5 w-full">
                <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 border-r border-border/50 pr-4">
                    <Target className="w-3.5 h-3.5" /> Engine
                </div>

                <div className="flex items-center gap-2">
                    <input
                        type="checkbox"
                        id="enable_pyramiding"
                        checked={enablePyramiding}
                        onChange={(e) => handleAdvancedSettingChange("enablePyramiding", e.target.checked, setEnablePyramiding)}
                        className="w-3 h-3 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                    />
                    <label htmlFor="enable_pyramiding" className={`text-[11px] font-medium cursor-pointer transition-colors ${enablePyramiding ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                        Pyramiding
                    </label>
                </div>

                {enablePyramiding && (
                    <>
                        <div className="flex items-center gap-2 border-l border-border/50 pl-3">
                            <span className="text-[10px] text-muted-foreground uppercase">Scale %</span>
                            <NumberInput
                                value={scalePct}
                                onChange={(val) => handleAdvancedSettingChange("scalePct", val === '' ? '' : Number(val), setScalePct)}
                                min={0}
                                step={0.1}
                                containerClassName="w-20 h-7 rounded-md"
                            />
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground uppercase">Max</span>
                            <NumberInput
                                value={maxScales}
                                onChange={(val) => handleAdvancedSettingChange("maxScales", val === '' ? '' : Number(val), setMaxScales)}
                                min={0}
                                step={1}
                                containerClassName="w-14 h-7 rounded-md"
                            />
                        </div>
                    </>
                )}

                <div className="flex items-center gap-2 border-l border-border/50 pl-4">
                    <input
                        type="checkbox"
                        id="trailing_sl"
                        checked={trailingSl}
                        onChange={(e) => handleAdvancedSettingChange("trailingSl", e.target.checked, setTrailingSl)}
                        className="w-3 h-3 rounded border-border/50 bg-background/50 focus:ring-primary focus:ring-offset-0 text-primary transition-colors cursor-pointer"
                    />
                    <label htmlFor="trailing_sl" className={`text-[11px] font-medium cursor-pointer transition-colors ${trailingSl ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>
                        Trailing SL
                    </label>
                </div>

                {trailingSl && (
                    <>
                        <div className="flex items-center gap-2 border-l border-border/50 pl-3">
                            <span className="text-[10px] text-muted-foreground uppercase">Trigger %</span>
                            <NumberInput
                                value={trailTrigger}
                                onChange={(val) => handleAdvancedSettingChange("trailTrigger", val === '' ? '' : Number(val), setTrailTrigger)}
                                min={0.1}
                                step={0.1}
                                containerClassName="w-20 h-7 rounded-md"
                            />
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground uppercase">Offset %</span>
                            <NumberInput
                                value={trailOffset}
                                onChange={(val) => handleAdvancedSettingChange("trailOffset", val === '' ? '' : Number(val), setTrailOffset)}
                                min={0.1}
                                step={0.1}
                                containerClassName="w-20 h-7 rounded-md"
                            />
                        </div>
                    </>
                )}

                <div className="flex items-center gap-2 border-l border-border/50 pl-4">
                    <span className="text-[10px] text-muted-foreground uppercase">Donchian</span>
                    <NumberInput
                        value={donchianPeriod}
                        onChange={(val) => handleAdvancedSettingChange("donchianPeriod", val === '' ? '' : Number(val), setDonchianPeriod)}
                        min={1}
                        max={250}
                        step={1}
                        containerClassName="w-20 h-7 rounded-md"
                    />
                </div>

                <div className="flex items-center gap-2 border-l border-border/50 pl-4 text-destructive">
                    <span className="text-[10px] uppercase">Max Loss %</span>
                    <NumberInput
                        value={maxDailyLossPct}
                        onChange={(val) => handleAdvancedSettingChange("maxDailyLossPct", val === '' ? '' : Number(val), setMaxDailyLossPct)}
                        min={0.5}
                        step={0.5}
                        ringColor="destructive"
                        containerClassName="w-20 h-7 rounded-md"
                    />
                </div>

                <div className="flex items-center gap-2 border-l border-border/50 pl-4 text-destructive">
                    <span className="text-[10px] uppercase">Max Trades</span>
                    <NumberInput
                        value={maxDailyTrades === 0 ? '' : maxDailyTrades}
                        onChange={(val) => handleAdvancedSettingChange("maxDailyTrades", val === '' ? 0 : Number(val), setMaxDailyTrades)}
                        min={0}
                        step={1}
                        ringColor="destructive"
                        containerClassName="w-20 h-7 rounded-md"
                    />
                </div>
            </div>
        </div>
    );
}
