import React, { InputHTMLAttributes } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';

interface NumberInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> {
  value?: number | string;
  defaultValue?: number | string;
  onChange?: (value: number | string) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  ringColor?: 'primary' | 'warning' | 'destructive' | 'muted-foreground';
  containerClassName?: string;
  appendContent?: React.ReactNode;
}

export function NumberInput({
  value: controlledValue,
  defaultValue,
  onChange,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
  step = 1,
  suffix,
  ringColor = 'primary',
  containerClassName = '',
  className = '',
  appendContent,
  children,
  ...props
}: NumberInputProps & { children?: React.ReactNode }) {

  const [localValue, setLocalValue] = React.useState<number | string>(defaultValue !== undefined ? defaultValue : '');

  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : localValue;

  const handleChange = (newVal: number | string) => {
    if (!isControlled) setLocalValue(newVal);
    if (onChange) onChange(newVal);
  };

  const handleIncrement = () => {
    // Treat empty string as 0 for arithmetic
    const numValue = value === '' ? 0 : Number(value);
    const newValue = Math.min(max, numValue + step);
    // Format to avoid floating point issues if step is decimal
    const formatted = step % 1 !== 0 ? Number(newValue.toFixed(2)) : newValue;
    handleChange(formatted);
  };

  const handleDecrement = () => {
    const numValue = value === '' ? 0 : Number(value);
    const newValue = Math.max(min, numValue - step);
    const formatted = step % 1 !== 0 ? Number(newValue.toFixed(2)) : newValue;
    handleChange(formatted);
  };

  const ringClassMap = {
    primary: 'focus-within:ring-primary focus-within:border-primary',
    warning: 'focus-within:ring-warning focus-within:border-warning',
    destructive: 'focus-within:ring-destructive focus-within:border-destructive',
    'muted-foreground': 'focus-within:ring-muted-foreground focus-within:border-muted-foreground'
  };

  const textClassMap = {
    primary: 'text-primary',
    warning: 'text-warning',
    destructive: 'text-destructive',
    'muted-foreground': 'text-muted-foreground'
  };

  return (
    <div className={`relative group flex items-center bg-muted/30 border border-border/50 rounded-lg focus-within:ring-1 ${ringClassMap[ringColor]} overflow-hidden transition-all ${containerClassName || 'h-10'}`}>
      {children}
      <input
        type="number"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        step={step}
        min={min}
        max={max}
        className={`flex-1 w-full bg-transparent pl-3 pr-2 py-2 text-sm text-foreground focus:outline-none font-mono ${className}`}
        {...props}
      />
      {suffix && (
        <span className={`text-xs font-bold font-mono pr-2 ${textClassMap[ringColor]}`}>
          {suffix}
        </span>
      )}
      <div className="flex flex-col h-full border-l border-border/50 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity bg-background/20">
        <button
          type="button"
          onClick={handleIncrement}
          className="cursor-pointer flex-1 flex items-center justify-center hover:bg-muted/50 border-b border-border/50 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronUp className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={handleDecrement}
          className="cursor-pointer flex-1 flex items-center justify-center hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>
      {appendContent}
    </div>
  );
}
