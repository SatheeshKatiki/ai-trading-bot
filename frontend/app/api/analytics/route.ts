import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  const filePath = path.join(process.cwd(), '..', 'trading-system', 'backtest_results.json');
  
  try {
    if (!fs.existsSync(filePath)) {
      // Return empty data if file doesn't exist
      return NextResponse.json({
        stats: {
          profitFactor: 0,
          expectancy: 0,
          winRate: 0,
          maxDrawdown: 0,
          totalTrades: 0,
          winningTrades: 0
        },
        winLossData: [],
        dayOfWeekData: [],
        expectancyData: [],
        streaks: {
          winning: { count: 0, value: 0 },
          losing: { count: 0, value: 0 },
          avgRatio: 0
        }
      });
    }
    
    const fileContent = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(fileContent);
    const trades = data.trades || [];
    const stats = data.stats || {};
    
    // Calculate Win/Loss Data
    const winningTrades = trades.filter((t: any) => t.pnl > 0);
    const losingTrades = trades.filter((t: any) => t.pnl <= 0);
    
    const winLossData = [
      { name: "Winning Trades", value: trades.length > 0 ? Math.round((winningTrades.length / trades.length) * 100) : 0 },
      { name: "Losing Trades", value: trades.length > 0 ? Math.round((losingTrades.length / trades.length) * 100) : 0 },
    ];
    
    // Calculate Day of Week Data
    const dayMap: { [key: string]: number } = { "Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0 };
    trades.forEach((t: any) => {
      if (t.time) {
        // Try to parse time, handle formats like "14:20" or full datetime
        let day = "Mon";
        try {
          if (t.time.includes('-')) {
            const date = new Date(t.time);
            day = date.toLocaleDateString('en-US', { weekday: 'short' });
          } else {
            // If just time "14:20", we don't know the day, default to Mon or skip
            day = "Wed"; // Default to middle of week for dummy times if any
          }
        } catch (e) {
          day = "Wed";
        }
        
        if (dayMap[day] !== undefined) {
          dayMap[day] += t.pnl;
        }
      }
    });
    
    const dayOfWeekData = Object.keys(dayMap).map(day => ({
      day,
      pnl: Math.round(dayMap[day])
    }));
    
    // Calculate Expectancy Growth
    let cumulativePnl = 0;
    const expectancyData = trades.map((t: any, index: number) => {
      cumulativePnl += t.pnl;
      return {
        trade: index + 1,
        val: Math.round(cumulativePnl / (index + 1))
      };
    });
    
    // Calculate Streaks
    let currentWinStreak = 0;
    let maxWinStreak = 0;
    let winStreakValue = 0;
    let maxWinStreakValue = 0;
    
    let currentLossStreak = 0;
    let maxLossStreak = 0;
    let lossStreakValue = 0;
    let maxLossStreakValue = 0;
    
    trades.forEach((t: any) => {
      if (t.pnl > 0) {
        currentWinStreak++;
        winStreakValue += t.pnl;
        if (currentWinStreak > maxWinStreak) {
          maxWinStreak = currentWinStreak;
          maxWinStreakValue = winStreakValue;
        }
        currentLossStreak = 0;
        lossStreakValue = 0;
      } else {
        currentLossStreak++;
        lossStreakValue += t.pnl;
        if (currentLossStreak > maxLossStreak) {
          maxLossStreak = currentLossStreak;
          maxLossStreakValue = lossStreakValue;
        }
        currentWinStreak = 0;
        winStreakValue = 0;
      }
    });
    
    const streaks = {
      winning: { count: maxWinStreak, value: Math.round(maxWinStreakValue) },
      losing: { count: maxLossStreak, value: Math.round(maxLossStreakValue) },
      avgRatio: losingTrades.length > 0 ? Math.round((winningTrades.length / losingTrades.length) * 10) / 10 : winningTrades.length
    };
    
    return NextResponse.json({
      stats: {
        profitFactor: stats.profitFactor || 0,
        expectancy: trades.length > 0 ? Math.round(cumulativePnl / trades.length) : 0,
        winRate: parseFloat(stats.winRate) || 0,
        maxDrawdown: stats.maxDrawdown || 0,
        totalTrades: trades.length,
        winningTrades: winningTrades.length
      },
      winLossData,
      dayOfWeekData,
      expectancyData: expectancyData.slice(-20), // Show last 20 for chart clarity
      streaks
    });
    
  } catch (error) {
    console.error('Failed to read data file:', error);
    return NextResponse.json({ error: 'Failed to process data file.' }, { status: 500 });
  }
}
