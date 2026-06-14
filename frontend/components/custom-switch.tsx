"use client";

import { motion } from "framer-motion";

interface CustomSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function CustomSwitch({ checked, onChange, label, size = 'md' }: CustomSwitchProps) {
  const dimensions = {
    sm: { track: "w-8 h-4", thumb: "w-3 h-3", offset: 16 },
    md: { track: "w-11 h-6", thumb: "w-5 h-5", offset: 20 },
    lg: { track: "w-14 h-8", thumb: "w-7 h-7", offset: 24 }
  };

  const currentSize = dimensions[size];

  return (
    <label className="flex items-center gap-3 cursor-pointer group">
      {label && <span className="text-sm font-medium text-foreground">{label}</span>}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`${currentSize.track} rounded-full p-0.5 transition-colors duration-300 relative flex items-center outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background ${
          checked 
            ? "bg-primary shadow-[0_0_12px_var(--glow-primary)]" 
            : "bg-slate-700/50 border border-slate-500/30 shadow-inner"
        }`}
      >
        <motion.div
          className={`${currentSize.thumb} relative rounded-full bg-white shadow-sm z-10 flex items-center justify-center overflow-hidden`}
          animate={{ x: checked ? currentSize.offset : 0 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          {/* Micro-interaction internal shadow/gradient */}
          <div className="absolute inset-0 bg-gradient-to-br from-white to-gray-300"></div>
        </motion.div>
      </button>
    </label>
  );
}
