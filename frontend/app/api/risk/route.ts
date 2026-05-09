import { NextResponse } from 'next/server';

export async function GET() {
  const exposureData = [
    { name: "Nifty 50", value: 45 },
    { name: "Bank Nifty", value: 35 },
    { name: "IT Sector", value: 20 },
  ];

  const drawdownData = [
    { day: "Mon", dd: 2 },
    { day: "Tue", dd: 5 },
    { day: "Wed", dd: 1 },
    { day: "Thu", dd: 8 },
    { day: "Fri", dd: 3 },
  ];

  const limits = {
    maxDailyLoss: 10000,
    riskPerTrade: 1.5,
    maxPositions: 5,
    circuitBreaker: true
  };

  const correlationMatrix = [
    { asset: "Nifty 50", values: [1.00, 0.82, 0.45] },
    { asset: "Bank Nifty", values: [0.82, 1.00, 0.12] },
    { asset: "IT Index", values: [0.45, 0.12, 1.00] }
  ];

  return NextResponse.json({
    limits,
    exposureData,
    drawdownData,
    correlationMatrix
  });
}
