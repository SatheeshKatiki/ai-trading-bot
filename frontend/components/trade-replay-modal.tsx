import React, { useState, useEffect } from 'react';
import { X, PlayCircle, Loader2, ArrowUpRight, ArrowDownRight, Target, ShieldAlert } from 'lucide-react';
import NativeChart from './native-chart';

interface Trade {
  id: string;
  type: string;
  entry: number;
  exit: number;
  pnl: number;
  time: string;
  exit_reason: string;
  score: number;
  qty?: number;
  scales?: number;
}

interface TradeReplayModalProps {
  trade: Trade;
  symbol: string;
  timeframe: string;
  onClose: () => void;
}

export function TradeReplayModal({ trade, symbol, timeframe, onClose }: TradeReplayModalProps) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Extract date from trade time "YYYY-MM-DD HH:MM:SS"
    const dateStr = trade.time.split(" ")[0];
    
    // Fetch historical data for this specific day
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/history?symbol=${encodeURIComponent(symbol)}&start_date=${dateStr}&end_date=${dateStr}&timeframe=${encodeURIComponent(timeframe)}`);
        if (!res.ok) throw new Error("Failed to fetch historical data for replay");
        const json = await res.json();
        if (json.data && Array.isArray(json.data)) {
          const annotatedData = json.data.map((candle: any) => {
            const dateStrRaw = candle.datetime || candle.Datetime || candle.date || candle.time;
            let candleTimeStr = "";
            if (dateStrRaw) {
               const safeDateStrRaw = dateStrRaw.includes(' ') ? dateStrRaw.replace(' ', 'T') : dateStrRaw;
               const d = new Date(safeDateStrRaw);
               if (!isNaN(d.getTime())) {
                  candleTimeStr = d.toISOString().replace("T", " ").substring(0, 16);
               }
            }
            
            // Format for NativeChart (expects native-chart formatted payload)
            const safeDateStrRaw2 = dateStrRaw.includes(' ') ? dateStrRaw.replace(' ', 'T') : dateStrRaw;
            const dateObj = new Date(safeDateStrRaw2);
            const time = (Math.floor(dateObj.getTime() / 1000) - (dateObj.getTimezoneOffset() * 60));
            
            const formattedCandle = {
              time: time,
              open: parseFloat(candle.open || candle.Open),
              high: parseFloat(candle.high || candle.High),
              low: parseFloat(candle.low || candle.Low),
              close: parseFloat(candle.close || candle.Close),
              volume: parseFloat(candle.volume || candle.Volume || 0)
            };

            const isEntry = candleTimeStr === trade.time.substring(0, 16);
            return {
              ...formattedCandle,
              marker: isEntry ? (trade.type === 'BUY' ? 'long_entry' : 'short_entry') : undefined,
              markerPrice: isEntry ? trade.entry : undefined,
            };
          }).sort((a: any, b: any) => a.time - b.time);
          
          setData(annotatedData);
        } else {
          throw new Error("No data returned");
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [trade, symbol, timeframe]);

  const isProfitable = trade.pnl > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <div className="glass-card w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col border border-border/50 rounded-xl shadow-2xl relative animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex justify-between items-center p-4 border-b border-border/20 bg-muted/20">
          <div className="flex items-center gap-3">
            <PlayCircle className="w-5 h-5 text-primary" />
            <h2 className="font-display font-bold text-lg text-foreground">AI Trade Replay</h2>
            <span className="text-xs font-mono bg-muted/50 text-muted-foreground px-2 py-1 rounded">
              {trade.id} | {trade.time}
            </span>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-muted/50 rounded-md transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          
          {/* Left Panel: Trade Stats */}
          <div className="w-full md:w-64 border-r border-border/20 p-4 bg-muted/10 overflow-y-auto space-y-4">
            
            <div className={`p-3 rounded-lg border ${isProfitable ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-red-500/10 border-red-500/20'}`}>
              <div className="text-xs text-muted-foreground mb-1">Trade Net PnL</div>
              <div className={`text-xl font-bold font-mono ${isProfitable ? 'text-emerald-400' : 'text-red-400'}`}>
                {isProfitable ? '+' : ''}₹{trade.pnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center border-b border-border/10 pb-2">
                <span className="text-xs text-muted-foreground">Direction</span>
                <span className={`text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1 ${trade.type === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                  {trade.type === 'BUY' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                  {trade.type}
                </span>
              </div>
              <div className="flex justify-between items-center border-b border-border/10 pb-2">
                <span className="text-xs text-muted-foreground">Quantity</span>
                <span className="text-sm font-mono text-foreground">{trade.qty || 65} ({(trade.scales || 0) + 1} Lots)</span>
              </div>
              <div className="flex justify-between items-center border-b border-border/10 pb-2">
                <span className="text-xs text-muted-foreground">Avg Entry Price</span>
                <span className="text-sm font-mono text-foreground">{trade.entry.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center border-b border-border/10 pb-2">
                <span className="text-xs text-muted-foreground">Exit Price</span>
                <span className="text-sm font-mono text-foreground">{trade.exit.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center border-b border-border/10 pb-2">
                <span className="text-xs text-muted-foreground">Exit Reason</span>
                <span className="text-xs font-medium bg-muted/40 px-1.5 py-0.5 rounded text-foreground flex items-center gap-1">
                  {trade.exit_reason === 'TARGET' ? <Target className="w-3 h-3 text-emerald-400" /> : <ShieldAlert className="w-3 h-3 text-warning" />}
                  {trade.exit_reason}
                </span>
              </div>
              <div className="flex justify-between items-center pb-2">
                <span className="text-xs text-muted-foreground">AI Score</span>
                <span className="text-sm font-mono text-primary font-bold">{trade.score.toFixed(1)}/100</span>
              </div>
            </div>
            
          </div>

          {/* Right Panel: Chart */}
          <div className="flex-1 bg-[#09090b] relative h-[400px] md:h-auto">
            {loading ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/50">
                <Loader2 className="w-8 h-8 text-primary animate-spin mb-4" />
                <p className="text-sm text-muted-foreground font-mono">Fetching full historical candles...</p>
              </div>
            ) : error ? (
              <div className="absolute inset-0 flex items-center justify-center text-destructive p-6 text-center">
                <p>Error loading chart: {error}</p>
              </div>
            ) : (
              <NativeChart initialData={data} disableFetch={true} symbol={`${symbol} (${timeframe})`} />
            )}
            
            {/* Draw Horizontal lines for Entry and Exit via overlay */}
            {!loading && !error && data.length > 0 && (
              <div className="absolute top-4 left-4 bg-background/80 border border-border/40 p-2 rounded text-xs text-muted-foreground backdrop-blur-md pointer-events-none z-10">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-3 h-0.5 bg-blue-500"></div> Entry: {trade.entry.toFixed(2)}
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-0.5 bg-fuchsia-500"></div> Exit: {trade.exit.toFixed(2)}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
