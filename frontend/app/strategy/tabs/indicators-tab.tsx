"use client";

import React from "react";
import IndicatorSettings from "@/components/indicator-settings";

interface IndicatorsTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function IndicatorsTab({ settings, setSettings }: IndicatorsTabProps) {
  return (
    <div className="space-y-6">
      {/* Mana Indicators Directory & Settings */}
      <IndicatorSettings />
    </div>
  );
}
