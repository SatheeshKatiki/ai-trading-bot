"use client";
import { useState, useEffect } from "react";
import { Globe } from "lucide-react";

export default function NewsTicker() {
  const [sentiment, setSentiment] = useState<{
    score: number;
    label: string;
    top_headlines: any[];
  }>({
    score: 0.0,
    label: "Loading...",
    top_headlines: []
  });
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showTelugu, setShowTelugu] = useState(false);

  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    // Fetch initial sentiment
    const fetchSentiment = async () => {
      try {
        const res = await fetch("/api/sentiment");
        if (res.ok) {
          const data = await res.json();
          setSentiment(data);
        }
      } catch (e) {
        console.warn("Failed to fetch sentiment", e);
      }
    };
    fetchSentiment();
    // Refresh every minute
    const interval = setInterval(fetchSentiment, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (sentiment.top_headlines.length === 0) return;
    if (isHovered) return; // Pause ticker if hovered
    
    const tickerInterval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % sentiment.top_headlines.length);
    }, 4000);
    return () => clearInterval(tickerInterval);
  }, [sentiment.top_headlines, isHovered]);

  const currentHeadline = sentiment.top_headlines[currentIndex];

  const getSentimentColor = (label: string) => {
    if (label.includes("Bullish")) return "text-success";
    if (label.includes("Bearish") || label.includes("Panic")) return "text-destructive";
    return "text-muted-foreground";
  };

  const getBreakingStatus = (headline: any) => {
    if (!headline) return { active: false, type: 'neutral' };
    const title = headline.title_en.toLowerCase();
    const sentimentScore = headline.sentiment || 0;
    
    let type = 'neutral';
    if (sentimentScore >= 0.4) {
      type = 'positive';
    } else if (sentimentScore <= -0.4) {
      type = 'negative';
    } else {
      const isPosKey = /(surge|soars|boom|gain|record high|bull|jump)/.test(title);
      const isNegKey = /(crash|plummets|crisis|panic|drop|bear|fall)/.test(title);
      if (isPosKey) type = 'positive';
      else if (isNegKey) type = 'negative';
      else if (/(breaking|alert|urgent|record)/.test(title)) type = sentimentScore >= 0 ? 'positive' : 'negative';
    }
    
    return { active: type !== 'neutral', type };
  };

  const breaking = getBreakingStatus(currentHeadline);

  // Dynamic Styles
  const badgeBg = breaking.active
    ? breaking.type === 'positive'
      ? 'bg-success/20 border-success/50'
      : 'bg-destructive/20 border-destructive/50'
    : 'bg-muted/30 border-border/40';

  const textColor = breaking.active
    ? breaking.type === 'positive'
      ? 'text-success'
      : 'text-destructive'
    : 'text-primary';

  const textStyle = breaking.active
    ? breaking.type === 'positive'
      ? 'text-success hover:text-emerald-700 dark:hover:text-emerald-400 font-bold tracking-wide'
      : 'text-destructive hover:text-red-700 dark:hover:text-red-400 font-bold tracking-wide'
    : 'text-foreground/90 hover:text-foreground';

  return (
    <div 
      className={`w-full flex items-center justify-between bg-gradient-to-r from-muted/10 via-background/40 to-muted/10 p-3 overflow-hidden transition-all duration-500`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="flex items-center gap-3 w-full">
        <div className={`flex items-center gap-2 px-3 py-1 ${badgeBg} rounded-full border whitespace-nowrap shrink-0 transition-colors duration-500`}>
          <Globe className={`h-4 w-4 ${breaking.active ? textColor + ' animate-pulse' : 'text-primary'}`} />
          <span className={`text-xs font-bold uppercase tracking-wider ${breaking.active ? textColor + ' font-extrabold animate-pulse' : 'text-foreground/80'}`}>
            {breaking.active ? "🚨 BREAKING" : "Macro News"}
          </span>
          {!breaking.active && (
            <span className={`text-xs font-bold ${getSentimentColor(sentiment.label)} ml-2 uppercase tracking-tight`}>
              {sentiment.label} ({sentiment.score})
            </span>
          )}
        </div>
        
        <div className="flex-1 overflow-hidden relative h-6 flex items-center px-4">
          {sentiment.top_headlines.length > 0 ? (
            <a 
              href={currentHeadline?.link}
              target="_blank"
              rel="noopener noreferrer"
              className={`text-[15px] font-semibold tracking-tight ${textStyle} transition-colors truncate block w-full animate-in slide-in-from-bottom-2 fade-in duration-500`}
              key={currentIndex}
            >
              <span className={`mr-2 ${breaking.active ? textColor : 'text-muted-foreground'} font-mono text-[11px] font-bold`}>[{currentHeadline?.published ? currentHeadline.published.substring(0, 16) : "Live"}]</span>
              {showTelugu && currentHeadline?.title_te ? currentHeadline.title_te : currentHeadline?.title_en}
            </a>
          ) : (
            <span className="text-sm text-muted-foreground italic flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              Scanning global financial news...
            </span>
          )}
        </div>
        
        <button
          onClick={() => setShowTelugu(!showTelugu)}
          className="shrink-0 px-3 py-1.5 text-xs font-bold uppercase tracking-widest bg-muted/20 hover:bg-primary/10 text-foreground hover:text-primary rounded-lg border border-border/50 transition-all active:scale-95"
        >
          {showTelugu ? "English" : "తెలుగు"}
        </button>
      </div>
    </div>
  );
}

