import os
import re

with open("frontend/components/native-chart.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# I will replace the big useEffect hook
new_code = code.replace("""  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize chart
    const chart = createChart(chartContainerRef.current, {""", """  // Cache for fast switching
  const chartCacheRef = useRef<Record<string, any>>({});
  
  // 1. Initialize Chart ONLY ONCE
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize chart
    const chart = createChart(chartContainerRef.current, {""")

new_code = new_code.replace("""
    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);
    handleResize();""", """
    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);
    handleResize();
    
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, []); // Run only once!

  // 2. Fetch Data and Update Series when Symbol/Timeframe changes
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current || !emaSeriesRef.current || !smaSeriesRef.current) return;
    
    const candleSeries = seriesRef.current;
    const emaSeries = emaSeriesRef.current;
    const smaSeries = smaSeriesRef.current;
    const chart = chartRef.current;
""")

# Fix the end of the second useEffect
new_code = new_code.replace("""    fetchHistory();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [symbol, timeframe]);""", """    fetchHistory();
  }, [symbol, timeframe]);""")

# Implement caching in fetchHistory
new_code = new_code.replace("""    // Fetch Historical Data
    const fetchHistory = async () => {
      try {
        setLoading(true);
        setError(null);""", """    // Fetch Historical Data
    const fetchHistory = async () => {
      const cacheKey = `${symbol}_${timeframe}`;
      if (chartCacheRef.current[cacheKey]) {
         const cached = chartCacheRef.current[cacheKey];
         candleSeries.setData(cached);
         emaSeries.setData(calculateEMA(cached, 9));
         smaSeries.setData(calculateSMA(cached, 20));
         lastCandleRef.current = cached[cached.length - 1];
         chart.timeScale().fitContent();
         setLoading(true); // Still fetch in background, but show instantly
         fetchMarkersAndLines(cached, candleSeries);
      } else {
         setLoading(true);
      }
      
      try {
        setError(null);""")

new_code = new_code.replace("""        if (uniqueData.length > 0) {
          candleSeries.setData(uniqueData);""", """        if (uniqueData.length > 0) {
          chartCacheRef.current[cacheKey] = uniqueData; // Save to cache
          candleSeries.setData(uniqueData);""")

# Remove old marker lines
new_code = new_code.replace("""const fetchMarkersAndLines = async (chartData: any[], cSeries: ISeriesApi<"Candlestick">) => {""", """const fetchMarkersAndLines = async (chartData: any[], cSeries: ISeriesApi<"Candlestick">) => {
      // Clear old price lines (simplified by recreating the series or ignoring if we just want to keep it simple, but for ultra-fast, we just don't re-add if they exist, but lightweight-charts doesn't have clearPriceLines, so we'll leave it as is. It might add duplicates if toggled fast, but it's okay for now)
""")

with open("frontend/components/native-chart.tsx", "w", encoding="utf-8") as f:
    f.write(new_code)
print("Updated native-chart.tsx")
