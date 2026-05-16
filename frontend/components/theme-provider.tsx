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
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState("dark");
  const [accentColor, setAccentColorState] = useState("#ff4d4d");
  const [density, setDensityState] = useState("compact");
  const [glassEnabled, setGlassEnabledState] = useState(true);

  // Initial load from localStorage
  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") || "dark";
    const savedColor = localStorage.getItem("accentColor") || "#ff4d4d";
    const savedDensity = localStorage.getItem("density") || "compact";
    const savedGlass = localStorage.getItem("glassEnabled") !== "false";

    setThemeState(savedTheme);
    setAccentColorState(savedColor);
    setDensityState(savedDensity);
    setGlassEnabledState(savedGlass);

    applyTheme(savedTheme);
    applyAccent(savedColor);
    applyDensity(savedDensity);
    applyGlass(savedGlass);
  }, []);

  const applyTheme = (t: string) => {
    if (t === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  };

  const applyAccent = (c: string) => {
    document.documentElement.style.setProperty('--primary', c);
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
      setTheme, setAccentColor, setDensity, setGlassEnabled
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
