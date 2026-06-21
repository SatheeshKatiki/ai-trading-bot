import React, { useMemo, useState } from 'react';
import { Calendar, ChevronLeft, ChevronRight, Layers, TrendingUp, TrendingDown, Activity, Target, Award, DollarSign } from 'lucide-react';
import { format, startOfWeek, endOfWeek, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isSameDay, eachMonthOfInterval } from 'date-fns';

interface Trade {
  pnl: number;
  time: string; // e.g., "2025-06-21 09:15:00"
  [key: string]: any;
}

interface HeatmapProps {
  trades: Trade[];
  startDate?: string;
  endDate?: string;
}

export function HeatmapAnalytics({ trades, startDate, endDate }: HeatmapProps) {
  const [currentMonthIndex, setCurrentMonthIndex] = useState(0);

  // Group trades by month including empty months
  const availableMonths = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    
    let minDate, maxDate;
    
    if (startDate && endDate) {
      minDate = new Date(startDate);
      maxDate = new Date(endDate);
    } else {
      const validDates = trades.map(t => new Date(t.time.replace(" ", "T"))).filter(d => !isNaN(d.getTime()));
      if (validDates.length === 0) return [];
      
      minDate = new Date(Math.min(...validDates.map(d => d.getTime())));
      maxDate = new Date(Math.max(...validDates.map(d => d.getTime())));
    }
    
    const allMonths = eachMonthOfInterval({ start: minDate, end: maxDate });
    const tradesByMonth: Record<string, Trade[]> = {};
    
    trades.forEach(trade => {
      const d = new Date(trade.time.replace(" ", "T"));
      if (isNaN(d.getTime())) return;
      const key = format(startOfMonth(d), 'yyyy-MM-dd');
      if (!tradesByMonth[key]) tradesByMonth[key] = [];
      tradesByMonth[key].push(trade);
    });
    
    return allMonths.map(monthStart => {
      const key = format(monthStart, 'yyyy-MM-dd');
      return {
        start: monthStart,
        end: endOfMonth(monthStart),
        trades: tradesByMonth[key] || [],
        key
      };
    });
  }, [trades]);

  const handlePrevMonth = () => {
    if (currentMonthIndex > 0) setCurrentMonthIndex(prev => prev - 1);
  };
  const handleNextMonth = () => {
    if (currentMonthIndex < availableMonths.length - 1) setCurrentMonthIndex(prev => prev + 1);
  };

  return (
    <div className="glass-card rounded-xl p-6 border border-border/20">
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-display font-bold text-lg text-foreground flex items-center gap-2">
          <Calendar className="w-5 h-5 text-primary" />
          Time & Day Heatmap
        </h3>
      </div>

      {trades.length === 0 || availableMonths.length === 0 ? (
        <div className="h-40 flex items-center justify-center text-muted-foreground text-sm border border-dashed border-border/20 rounded-xl">
          No trades executed yet
        </div>
      ) : (
        <div className="w-full grid grid-cols-1 lg:grid-cols-[350px_1fr] gap-6 items-start max-w-4xl mx-auto">
          {/* Calendar View Left Column */}
          <div className="bg-muted/5 rounded-xl border border-border/10 p-5 shadow-sm">
            {/* Calendar Pagination Header */}
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-bold text-foreground">
                {format(availableMonths[currentMonthIndex].start, 'MMMM, yyyy')}
              </span>
              <div className="flex items-center gap-2">
                <button 
                  onClick={handlePrevMonth} 
                  disabled={currentMonthIndex === 0}
                  className="p-1.5 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button 
                  onClick={handleNextMonth}
                  disabled={currentMonthIndex === availableMonths.length - 1}
                  className="p-1.5 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Calendar Grid Header */}
            <div className="grid grid-cols-7 gap-1 mb-3 text-center">
              {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map(day => (
                <div key={day} className="text-[10px] font-bold tracking-wider text-muted-foreground/70 uppercase">
                  {day}
                </div>
              ))}
            </div>
            
            {/* Calendar Grid Body */}
            <div className="grid grid-cols-7 gap-1.5">
              {(() => {
                const monthData = availableMonths[currentMonthIndex];
                const startDate = startOfWeek(monthData.start, { weekStartsOn: 1 });
                const endDate = endOfWeek(monthData.end, { weekStartsOn: 1 });
                const calendarDays = eachDayOfInterval({ start: startDate, end: endDate });
                
                return calendarDays.map((day, idx) => {
                  const isCurrentMonth = isSameMonth(day, monthData.start);
                  
                  const dayTrades = monthData.trades.filter(t => {
                    const td = new Date(t.time.replace(" ", "T"));
                    return !isNaN(td.getTime()) && isSameDay(td, day);
                  });
                  
                  const dayPnl = dayTrades.reduce((sum, t) => sum + t.pnl, 0);
                  
                  let cellColor = 'bg-muted/5 text-muted-foreground/30';
                  let ringClass = '';
                  
                  if (isCurrentMonth) {
                    cellColor = 'bg-muted/10 text-muted-foreground hover:bg-muted/20 border border-transparent';
                    if (dayPnl > 0) {
                      cellColor = 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500 font-semibold hover:bg-emerald-500/20';
                    }
                    if (dayPnl < 0) {
                      cellColor = 'bg-red-500/10 border-red-500/30 text-red-500 font-semibold hover:bg-red-500/20';
                    }
                  }
                  
                  return (
                    <div key={idx} className="relative group">
                      <div className={`aspect-square rounded-md flex items-center justify-center text-xs transition-all cursor-default ${cellColor} ${ringClass}`}>
                        {format(day, 'dd')}
                      </div>
                      
                      {/* Tooltip */}
                      {isCurrentMonth && dayTrades.length > 0 && (
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-30 pointer-events-none">
                          <div className="bg-popover/95 backdrop-blur-md text-popover-foreground px-3 py-2 rounded-lg shadow-xl border border-border/50 whitespace-nowrap">
                            <div className="font-semibold text-muted-foreground text-[10px] mb-1">
                              {format(day, 'MMM dd, yyyy')}
                            </div>
                            <div className={`font-mono font-bold text-sm ${dayPnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                              {dayPnl >= 0 ? '+' : ''}₹{dayPnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </div>
                            <div className="text-[9px] font-medium text-muted-foreground/80 mt-0.5 uppercase tracking-wider">{dayTrades.length} Trades</div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          </div>

          {/* Right Column Monthly Summary Dashboard */}
          {(() => {
             const monthData = availableMonths[currentMonthIndex];
             const monthTrades = monthData.trades;
             const monthlyPnl = monthTrades.reduce((sum, t) => sum + t.pnl, 0);
             const monthlyWins = monthTrades.filter(t => t.pnl > 0).length;
             const totalTrades = monthTrades.length;
             const winRate = totalTrades > 0 ? (monthlyWins / totalTrades) * 100 : 0;
             
             const dailyPnls: Record<string, number> = {};
             monthTrades.forEach(t => {
               const td = new Date(t.time.replace(" ", "T"));
               if (isNaN(td.getTime())) return;
               const dateStr = format(td, 'yyyy-MM-dd');
               dailyPnls[dateStr] = (dailyPnls[dateStr] || 0) + t.pnl;
             });
             
             let bestDayStr = null;
             let bestDayPnl = -Infinity;
             let worstDayStr = null;
             let worstDayPnl = Infinity;
             
             Object.entries(dailyPnls).forEach(([dayStr, pnl]) => {
               if (pnl > bestDayPnl) { bestDayPnl = pnl; bestDayStr = dayStr; }
               if (pnl < worstDayPnl) { worstDayPnl = pnl; worstDayStr = dayStr; }
             });

             if (bestDayPnl === -Infinity) bestDayPnl = 0;
             if (worstDayPnl === Infinity) worstDayPnl = 0;

             return (
              <div className="flex flex-col gap-3 h-full justify-center">
                <div className="grid grid-cols-2 gap-3">
                  {/* Total PnL Card */}
                  <div className="bg-muted/10 rounded-xl border border-border/20 p-4 flex flex-col justify-center">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                      Net Monthly PnL
                    </span>
                    <span className={`text-xl font-mono font-bold ${monthlyPnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                      {monthlyPnl >= 0 ? '+' : ''}₹{monthlyPnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </span>
                  </div>

                  {/* Win Rate Card */}
                  <div className="bg-muted/10 rounded-xl border border-border/20 p-4 flex flex-col justify-center">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                      Win Rate
                    </span>
                    <span className="text-xl font-mono font-bold text-foreground">
                      {winRate.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-muted-foreground font-medium">{monthlyWins}W / {totalTrades - monthlyWins}L</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* Best Day */}
                  <div className="bg-emerald-500/5 rounded-xl border border-emerald-500/10 p-4 flex flex-col justify-center">
                    <span className="text-[10px] font-semibold text-emerald-500/80 uppercase tracking-wider mb-1">
                      Best Day
                    </span>
                    <span className="text-base font-mono font-bold text-emerald-500">
                      +₹{bestDayPnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-medium">
                      {bestDayStr ? format(new Date(bestDayStr), 'MMM dd') : '-'}
                    </span>
                  </div>

                  {/* Worst Day */}
                  <div className="bg-red-500/5 rounded-xl border border-red-500/10 p-4 flex flex-col justify-center">
                    <span className="text-[10px] font-semibold text-red-500/80 uppercase tracking-wider mb-1">
                      Worst Day
                    </span>
                    <span className="text-base font-mono font-bold text-red-500">
                      {worstDayPnl < 0 ? '-' : ''}₹{Math.abs(worstDayPnl).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-medium">
                      {worstDayStr ? format(new Date(worstDayStr), 'MMM dd') : '-'}
                    </span>
                  </div>
                </div>
                
                {/* Total Volume / Trades */}
                <div className="bg-muted/10 rounded-xl border border-border/20 p-4 flex items-center justify-between">
                  <div>
                     <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-0.5 block">
                        Monthly Trades
                      </span>
                      <span className="text-lg font-mono font-bold text-foreground">
                        {totalTrades}
                      </span>
                  </div>
                  <div className="text-right">
                     <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-0.5 block">
                        Total Trades (All-Time)
                      </span>
                      <span className="text-lg font-mono font-bold text-muted-foreground/70">
                        {trades.length}
                      </span>
                  </div>
                </div>
              </div>
             );
          })()}
        </div>
      )}
    </div>
  );
}
