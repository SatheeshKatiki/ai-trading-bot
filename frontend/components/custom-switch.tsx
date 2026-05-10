"use client";

import { motion } from "framer-motion";

interface CustomSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export default function CustomSwitch({ checked, onChange }: CustomSwitchProps) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-12 h-6 rounded-full p-0.5 transition-colors relative flex items-center shadow-lg ${
        checked ? "bg-[#ff4d4d] shadow-red-500/20" : "bg-muted border border-border"
      }`}
    >
      {/* Thumb */}
      <motion.div
        className="w-5 h-5 rounded-full bg-white shadow-md z-10"
        animate={{
          x: checked ? 24 : 0,
        }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}
