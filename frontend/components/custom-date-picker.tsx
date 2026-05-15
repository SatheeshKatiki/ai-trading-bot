"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from "lucide-react";

interface CustomDatePickerProps {
  label: string;
  value: string;
  onChange: (date: string) => void;
}

export default function CustomDatePicker({ label, value, onChange }: CustomDatePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentMonth, setCurrentMonth] = useState(new Date("2026-05-04")); // Default to data month
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    if (value) {
      setCurrentMonth(new Date(value));
    }
  }, [value]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node) &&
          buttonRef.current && !buttonRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const calendarWidth = 280; // Width of the popover
      
      let left = rect.left + window.scrollX;
      
      // If the calendar extends beyond the screen width, align it to the right of the button instead
      if (rect.left + calendarWidth > window.innerWidth) {
        left = rect.right + window.scrollX - calendarWidth;
      }
      
      setCoords({
        top: rect.bottom + window.scrollY,
        left: left
      });
    }
  }, [isOpen]);

  const getDaysInMonth = (date: Date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDayIndex = new Date(year, month, 1).getDay();
    const startDay = firstDayIndex === 0 ? 6 : firstDayIndex - 1;
    return { daysInMonth, startDay };
  };

  const { daysInMonth, startDay } = getDaysInMonth(currentMonth);
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);
  const blanks = Array.from({ length: startDay }, (_, i) => i);

  const months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  const handleDateSelect = (day: number) => {
    const year = currentMonth.getFullYear();
    const month = (currentMonth.getMonth() + 1).toString().padStart(2, '0');
    const dayStr = day.toString().padStart(2, '0');
    onChange(`${year}-${month}-${dayStr}`);
    setIsOpen(false);
  };

  const changeMonth = (offset: number) => {
    const newDate = new Date(currentMonth);
    newDate.setMonth(newDate.getMonth() + offset);
    setCurrentMonth(newDate);
  };

  const calendarJSX = (
    <div 
      ref={popoverRef}
      style={{ top: coords.top + 8, left: coords.left }}
      className="absolute z-[9999] p-4 bg-popover border border-border/50 rounded-xl shadow-2xl w-[280px]"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-bold text-foreground">
          {months[currentMonth.getMonth()]} {currentMonth.getFullYear()}
        </h4>
        <div className="flex gap-1">
          <button onClick={() => changeMonth(-1)} className="p-1.5 hover:bg-muted rounded-md transition-colors">
            <ChevronLeft className="w-4 h-4 text-foreground" />
          </button>
          <button onClick={() => changeMonth(1)} className="p-1.5 hover:bg-muted rounded-md transition-colors">
            <ChevronRight className="w-4 h-4 text-foreground" />
          </button>
        </div>
      </div>

      {/* Weekdays */}
      <div className="grid grid-cols-7 gap-1 text-center text-xs font-bold text-primary mb-2">
        <div>Mo</div><div>Tu</div><div>We</div><div>Th</div><div>Fr</div><div>Sa</div><div>Su</div>
      </div>

      {/* Days Grid */}
      <div className="grid grid-cols-7 gap-1">
        {blanks.map((_, i) => <div key={`blank-${i}`} className="h-8"></div>)}
        {days.map((day) => {
          const year = currentMonth.getFullYear();
          const month = (currentMonth.getMonth() + 1).toString().padStart(2, '0');
          const dayStr = day.toString().padStart(2, '0');
          const dateStr = `${year}-${month}-${dayStr}`;
          const isSelected = dateStr === value;
          const isToday = dateStr === "2026-05-06";
          
          return (
            <button
              key={day}
              onClick={() => handleDateSelect(day)}
              className={`h-8 text-xs font-bold rounded-md transition-colors flex items-center justify-center ${
                isSelected 
                  ? "bg-primary text-primary-foreground" 
                  : isToday
                    ? "border border-primary text-primary hover:bg-primary/10"
                    : "text-foreground hover:bg-muted"
              }`}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="relative">
      <label className="text-xs font-medium text-muted-foreground block mb-1.5">{label}</label>
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-muted/30 border border-border/50 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary flex items-center justify-between hover:bg-muted/50 transition-colors"
      >
        <span>{value || "Select Date"}</span>
        <CalendarIcon className="w-4 h-4 text-muted-foreground" />
      </button>

      {isOpen && mounted && typeof window !== 'undefined'
        ? createPortal(calendarJSX, document.body)
        : null}
    </div>
  );
}
