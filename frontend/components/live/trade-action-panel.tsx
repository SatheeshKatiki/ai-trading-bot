import React, { useState, useEffect } from 'react';
import { Settings, Shield, Target, Clock, ChevronDown, Package, Layers, AlertTriangle, X } from 'lucide-react';
import { NumberInput } from "@/components/number-input";
import { useLiveSettingsStore } from '@/store/useLiveSettingsStore';
import { useLiveMarketStore } from '@/store/useLiveMarketStore';
import { toast } from 'sonner';

interface TradeActionPanelProps {
    urlSymbol: string;
    defaultBaseQty: number;
}

// Confirmation Modal
function ConfirmModal({
    title, lines, confirmLabel, confirmClass = "", onConfirm, onCancel
}: {
    title: string;
    lines: string[];
    confirmLabel: string;
    confirmClass?: string;
    onConfirm: () => void;
    onCancel: () => void;
}) {
    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
            <div className="relative z-10 bg-card border border-border rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
                <div className="flex items-start gap-3 mb-4">
                    <div className="p-2 bg-destructive/10 rounded-xl shrink-0">
                        <AlertTriangle className="w-5 h-5 text-destructive" />
                    </div>
                    <div className="flex-1">
                        <h4 className="font-bold text-foreground text-base">{title}</h4>
                        {lines.map((l, i) => (
                            <p key={i} className="text-sm text-muted-foreground mt-1">{l}</p>
                        ))}
                    </div>
                    <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
                        <X className="w-4 h-4" />
                    </button>
                </div>
                <div className="flex gap-3 mt-5">
                    <button
                        onClick={onCancel}
                        className="flex-1 px-4 py-2 rounded-xl border border-border bg-background text-sm font-semibold text-foreground hover:bg-muted transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        className={`flex-1 px-4 py-2 rounded-xl text-white text-sm font-bold transition-colors ${confirmClass || 'bg-destructive hover:bg-destructive/90'}`}
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}

export function TradeActionPanel({ urlSymbol, defaultBaseQty }: TradeActionPanelProps) {
    const {
        tradingMode,
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

    const trades = useLiveMarketStore(state => state.trades);
    const openTrades = trades.filter(t => t.status === "Entered");

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

    const [availableStrategies, setAvailableStrategies] = useState<{ name: string, description?: string }[]>([]);
    const [targetPct, setTargetPctLocal] = useState<number | string>(2.5);

    // Order confirmation state
    const [pendingOrder, setPendingOrder] = useState<{ action: 'BUY' | 'SELL' } | null>(null);
    const [strategyChangeWarning, setStrategyChangeWarning] = useState<string | null>(null);

    useEffect(() => {
        const fetchStrategies = async () => {
            try {
                const res = await fetch('/api/strategies');
                if (res.ok) {
                    const data = await res.json();
                    if (data.strategies) {
                        const formatted = Array.isArray(data.strategies)
                            ? data.strategies.map((s: any) => typeof s === 'string' ? { name: s } : s)
                            : Object.keys(data.strategies).map(key => ({ name: key, ...data.strategies[key] }));
                        setAvailableStrategies(formatted);
                        if (formatted.length > 0 && !formatted.find((s: any) => s.name === strategy)) {
                            setStrategy(formatted[0].name);
                        }
                    }
                }
            } catch (error) {
                console.error("Failed to fetch available strategies:", error);
            }
        };
        // Also fetch current target pct from settings
        const fetchSettings = async () => {
            try {
                const res = await fetch('/api/settings');
                if (res.ok) {
                    const data = await res.json();
                    if (data.target_pct !== undefined) setTargetPctLocal(data.target_pct);
                }
            } catch { /* ignore */ }
        };
        fetchStrategies();
        fetchSettings();
    }, []);

    // Handle Strategy Change with open-position warning
    const handleStrategyChange = async (newStrategy: string) => {
        if (openTrades.length > 0) {
            setStrategyChangeWarning(newStrategy);
            return;
        }
        applyStrategyChange(newStrategy);
    };

    const applyStrategyChange = async (newStrategy: string) => {
        setStrategy(newStrategy);
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_strategy: newStrategy })
            });
            toast.success(`Strategy: ${(strategyNames[newStrategy] || newStrategy)}`);
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

    // Handle Target % Change
    const handleTargetPctChange = async (val: any) => {
        setTargetPctLocal(val);
        const num = parseFloat(val);
        if (!isNaN(num) && num > 0) {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_pct: num })
                });
            } catch (error) {
                console.error("Failed to update target pct:", error);
            }
        }
    };

    // Handle Quantity Change
    const getBaseQty = (sym: string) => {
        const { lotSizes } = useLiveSettingsStore.getState();
        const keys = Object.keys(lotSizes).sort((a, b) => b.length - a.length);
        for (const key of keys) {
            if (sym.toUpperCase().includes(key)) return lotSizes[key];
        }
        return defaultBaseQty || 1;
    };

    const baseQty = getBaseQty(urlSymbol);

    // Allow empty value (0) so the user can backspace to clear the field.
    // The `min` prop on NumberInput prevents the down-arrow from going to 0.
    const displayValue = quantity === 0 ? '' : (inputMode === 'lots'
        ? Math.round(quantity / baseQty)
        : quantity);

    // Hint text always visible if quantity > 0
    const hintText = quantity > 0
        ? (inputMode === 'lots'
            ? `= ${quantity} Qty`
            : `= ${Math.round(quantity / baseQty)} Lot${Math.round(quantity / baseQty) !== 1 ? 's' : ''}`)
        : null;

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

    const [isExecuting, setIsExecuting] = useState(false);

    const doExecute = async (action: 'BUY' | 'SELL') => {
        setPendingOrder(null);
        if (isExecuting) return;
        setIsExecuting(true);
        try {
            toast.loading(`Executing ${action}...`, { id: 'manual-exec' });
            const payload = {
                symbol: urlSymbol,
                action: action,
                quantity: quantity,
                order_type: "MARKET",
                product_type: "INTRADAY"
            };
            const res = await fetch('/api/order/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                toast.success(`Order Placed: ${data.order_id || 'Success'}`, { id: 'manual-exec' });
            } else {
                toast.error(data.error || data.detail || 'Execution failed', { id: 'manual-exec' });
            }
        } catch (err: any) {
            toast.error(err.message || 'Execution failed', { id: 'manual-exec' });
        } finally {
            setIsExecuting(false);
        }
    };

    const lotsDisplay = Math.max(1, Math.round(quantity / baseQty));
    const isLive = tradingMode === 'live';

    const FILTER_TOOLTIPS: Record<string, string> = {
        "enable_ema_filter": "Only trade when price is above/below the EMA trend direction",
        "enable_volume_filter": "Require above-average volume before entering a trade",
        "enable_adx_filter": "Only trade when ADX > 25, indicating a strong trend",
        "enable_vwap_filter": "Require price to be on the correct side of VWAP",
        "enable_rsi_filter": "Only enter when RSI momentum confirms the direction",
        "enable_squeeze_filter": "Wait for Bollinger Band squeeze breakout before entry",
        "enable_extension_filter": "Avoid entries when price is overextended from EMA",
        "enable_cpr_filter": "Filter trades based on CPR (Central Pivot Range) rejection",
        "enable_aggression_filter": "Only enter on aggressive candles (large body, small wick)",
    };

    return (
        <>
            {/* BUY/SELL Confirmation Modal */}
            {pendingOrder && (
                <ConfirmModal
                    title={`Confirm ${pendingOrder.action} Order`}
                    lines={[
                        `Symbol: ${urlSymbol}`,
                        `Side: ${pendingOrder.action}`,
                        `Quantity: ${quantity} Qty (${lotsDisplay} Lot${lotsDisplay !== 1 ? 's' : ''})`,
                        `Order Type: MARKET`,
                        isLive ? '⚠️ This is a LIVE order. Real money at risk.' : 'Paper trade — no real money involved.'
                    ]}
                    confirmLabel={`Place ${pendingOrder.action}`}
                    confirmClass={pendingOrder.action === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'}
                    onConfirm={() => doExecute(pendingOrder.action)}
                    onCancel={() => setPendingOrder(null)}
                />
            )}

            {/* Strategy Change Warning Modal */}
            {strategyChangeWarning && (
                <ConfirmModal
                    title="Strategy Change Warning"
                    lines={[
                        `You have ${openTrades.length} open position(s).`,
                        `Switching to "${strategyNames[strategyChangeWarning] || strategyChangeWarning}" while positions are open may cause unexpected exit behaviour.`,
                        'Are you sure you want to proceed?'
                    ]}
                    confirmLabel="Yes, Change Strategy"
                    onConfirm={() => { applyStrategyChange(strategyChangeWarning!); setStrategyChangeWarning(null); }}
                    onCancel={() => setStrategyChangeWarning(null)}
                />
            )}

            <div className="glass-card rounded-xl border border-border/20 overflow-hidden flex flex-col h-full bg-card shadow-lg shadow-black/5">
                <div className="p-4 border-b border-border/50 bg-muted/20 flex items-center justify-between">
                    <h3 className="font-display font-bold text-sm text-foreground flex items-center gap-2">
                        <Settings className="w-4 h-4 text-primary" />
                        Trade Actions & Config
                    </h3>
                    {/* Live mode badge */}
                    {isLive && (
                        <span className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-[10px] font-bold uppercase tracking-wider animate-pulse">
                            <span className="w-1.5 h-1.5 rounded-full bg-destructive inline-block"></span>
                            LIVE TRADING
                        </span>
                    )}
                </div>

                {/* --- CORE SETTINGS ROW --- */}
                <div className="p-4 flex flex-wrap items-start gap-4 bg-background border-b border-border/30 w-full relative z-30">

                    {/* Strategy Selector */}
                    <div className="relative group flex-1 min-w-[180px]">
                        <span className="absolute -top-3 left-2 px-1 bg-background text-[10px] font-bold text-muted-foreground uppercase tracking-wider z-20">Strategy</span>
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
                    <div className="relative group flex flex-col items-start">
                        <div className="flex items-center">
                            <span className="absolute -top-3 left-2 px-1 bg-background text-[10px] font-bold text-muted-foreground uppercase tracking-wider group-focus-within:text-primary transition-colors z-20">
                                {inputMode === 'lots' ? 'Lots' : 'Qty.'}
                            </span>
                            <NumberInput
                                value={displayValue}
                                onChange={(val) => handleValueChange(Number(val))}
                                onBlur={() => {
                                    if (quantity <= 0) {
                                        handleQuantityChange(baseQty);
                                    }
                                }}
                                min={inputMode === 'lots' ? 1 : baseQty}
                                step={inputMode === 'lots' ? 1 : baseQty}
                                containerClassName="w-32 h-10 rounded-xl"
                                appendContent={
                                    <button
                                        onClick={() => {
                                            if (inputMode === 'qty') {
                                                const lots = Math.max(1, Math.round(quantity / baseQty));
                                                handleQuantityChange(lots * baseQty);
                                                setInputMode('lots');
                                            } else {
                                                setInputMode('qty');
                                            }
                                        }}
                                        className="flex items-center justify-center w-10 h-full border border-l-0 border-border bg-muted/20 hover:bg-muted/50 hover:text-primary transition-colors rounded-r-xl flex-shrink-0 z-10"
                                        title={`Switch to ${inputMode === 'lots' ? 'Quantity' : 'Lots'}`}
                                    >
                                        {inputMode === 'lots' ? <Package className="w-4 h-4" /> : <Layers className="w-4 h-4" />}
                                    </button>
                                }
                            />
                        </div>
                        {/* Lot ↔ Qty hint */}
                        {hintText && (
                            <span className="text-[9px] text-muted-foreground mt-1 pl-1 font-mono">{hintText}</span>
                        )}
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

                    {/* Target % Selector — previously missing */}
                    <div className="relative group">
                        <span className="absolute -top-3 left-2 px-1 bg-background text-[10px] font-bold text-success/80 uppercase tracking-wider group-focus-within:text-success transition-colors z-20">
                            TP %
                        </span>
                        <NumberInput
                            value={targetPct}
                            onChange={(val) => handleTargetPctChange(val)}
                            min={0.1}
                            step={0.1}
                            suffix="%"
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

                    {/* Manual Execution Buttons — with confirmation */}
                    <div className="flex items-center gap-2 ml-auto">
                        <button
                            onClick={() => setPendingOrder({ action: 'BUY' })}
                            disabled={isExecuting || quantity <= 0}
                            className="px-6 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 font-bold rounded-xl transition-all disabled:opacity-50"
                        >
                            BUY
                        </button>
                        <button
                            onClick={() => setPendingOrder({ action: 'SELL' })}
                            disabled={isExecuting || quantity <= 0}
                            className="px-6 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 font-bold rounded-xl transition-all disabled:opacity-50"
                        >
                            SELL
                        </button>
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
                        <div key={filter.id} className="flex items-center gap-2" title={FILTER_TOOLTIPS[filter.id]}>
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
        </>
    );
}
