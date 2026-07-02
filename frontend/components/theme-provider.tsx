"use client";

import { createContext, useContext, useEffect, useState } from "react";

type ThemeContextType = {
  theme: string;
  accentColor: string;
  density: string;
  glassEnabled: boolean;
  setTheme: (t: string) => void;
  setAccentColor: (c: string) => void;
  setDensity: (d: string) => void;
  setGlassEnabled: (g: boolean) => void;
  isMounted: boolean;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [isMounted, setIsMounted] = useState(false);
  const [theme, setThemeState] = useState<string>("dark");
  const [accentColor, setAccentColorState] = useState<string>("#ff4d4d");
  const [density, setDensityState] = useState<string>("compact");
  const [glassEnabled, setGlassEnabledState] = useState<boolean>(true);

  // Synchronize state with what the blocking script applied
  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") || "dark";
    const savedColor = localStorage.getItem("accentColor") || "#ff4d4d";
    const savedDensity = localStorage.getItem("density") || "compact";
    const savedGlass = localStorage.getItem("glassEnabled") !== "false";

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeState(savedTheme);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAccentColorState(savedColor);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDensityState(savedDensity);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGlassEnabledState(savedGlass);
    setIsMounted(true);
  }, []);

  const applyTheme = (t: string) => {
    if (t === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  };

  const applyAccent = (c: string) => {
    document.documentElement.style.setProperty('--primary', c);
    
    // Calculate RGB for glow effects
    const hex = c.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
      document.documentElement.style.setProperty('--primary-rgb', `${r}, ${g}, ${b}`);
      document.documentElement.style.setProperty('--glow-primary', `rgba(${r}, ${g}, ${b}, 0.25)`);
    }
  };

  const applyDensity = (d: string) => {
    if (d === "spacious") document.documentElement.classList.add("spacious-mode");
    else document.documentElement.classList.remove("spacious-mode");
  };

  const applyGlass = (g: boolean) => {
    if (!g) document.documentElement.classList.add("no-glass");
    else document.documentElement.classList.remove("no-glass");
  };

  const setTheme = (t: string) => {
    setThemeState(t);
    localStorage.setItem("theme", t);
    applyTheme(t);
  };

  const setAccentColor = (c: string) => {
    setAccentColorState(c);
    localStorage.setItem("accentColor", c);
    applyAccent(c);
  };

  const setDensity = (d: string) => {
    setDensityState(d);
    localStorage.setItem("density", d);
    applyDensity(d);
  };

  const setGlassEnabled = (g: boolean) => {
    setGlassEnabledState(g);
    localStorage.setItem("glassEnabled", g.toString());
    applyGlass(g);
  };

  return (
    <ThemeContext.Provider value={{
      theme, accentColor, density, glassEnabled,
      setTheme, setAccentColor, setDensity, setGlassEnabled,
      isMounted
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within a ThemeProvider");
  return context;
}
