"use client";

import { useState, useRef, useEffect } from "react";
import { motion, useMotionValue } from "framer-motion";

interface SliderProps {
  min: number;
  max: number;
  value: number;
  step?: number;
  onChange: (val: number) => void;
}

export default function CustomSlider({ min, max, value, step = 1, onChange }: SliderProps) {
  const constraintsRef = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  
  // Map value to percentage
  const percentage = ((value - min) / (max - min)) * 100;
  
  useEffect(() => {
    if (constraintsRef.current) {
      const width = constraintsRef.current.offsetWidth;
      x.set((percentage / 100) * width);
    }
  }, [percentage, x]);

  const handleDrag = () => {
    if (constraintsRef.current) {
      const width = constraintsRef.current.offsetWidth;
      const currentX = x.get();
      const currentPercentage = Math.min(100, Math.max(0, (currentX / width) * 100));
      const rawValue = min + (currentPercentage / 100) * (max - min);
      
      const newValue = Math.round(rawValue / step) * step;
      const fixedValue = parseFloat(newValue.toFixed(2)); // Fix floating point issues
      
      onChange(fixedValue);
    }
  };

  return (
    <div ref={constraintsRef} className="relative w-full h-6 flex items-center cursor-pointer">
      {/* Empty Track (Thin Line) */}
      <div className="absolute w-full h-[2px] bg-border rounded-full"></div>
      
      {/* Filled Track (Thick Bar) */}
      <div 
        className="absolute h-1.5 bg-gradient-to-r from-[#ff4d4d] to-[#ff7675] rounded-full" 
        style={{ width: `${percentage}%` }}
      ></div>
      
      {/* Thumb */}
      <motion.div
        drag="x"
        dragConstraints={constraintsRef}
        dragElastic={0}
        dragMomentum={false}
        onDrag={handleDrag}
        style={{ x }}
        className="absolute w-3.5 h-3.5 rounded-full bg-[#ff4d4d] shadow-lg cursor-grab active:cursor-grabbing -ml-1.5"
      />
    </div>
  );
}
