"use client";

import { Bell, ShieldAlert, Zap, BarChart } from "lucide-react";
import CustomSwitch from "@/components/custom-switch";

interface NotificationsTabProps {
  settings: any;
  setSettings: (settings: any) => void;
}

export default function NotificationsTab({ settings, setSettings }: NotificationsTabProps) {
  const updateSetting = (key: string, value: any) => {
    setSettings({ ...settings, [key]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

      {/* Box 1: Telegram Alerts */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#4f46e5]/20 rounded-xl text-[#4f46e5] shadow-lg shadow-indigo-500/10">
              <Bell className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Telegram Alerts</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Chat ID</label>
              <input
                type="text"
                value={settings.telegram_chat_id || "123456789"}
                onChange={(e) => updateSetting("telegram_chat_id", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Bot Token</label>
              <input type="password" value="••••••••••••••••" className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#4f46e5]" readOnly />
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Telegram</span>
          <CustomSwitch
            checked={settings.enable_telegram || false}
            onChange={(checked: boolean) => updateSetting("enable_telegram", checked)}
          />
        </div>
      </div>

      {/* Box 2: WhatsApp Alerts */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#10b981]/20 rounded-xl text-[#10b981] shadow-lg shadow-emerald-500/10">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">WhatsApp Alerts</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Phone Number</label>
              <input
                type="text"
                value={settings.whatsapp_phone_number || "+91 9876543210"}
                onChange={(e) => updateSetting("whatsapp_phone_number", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#10b981]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">API Provider</label>
              <select
                value={settings.whatsapp_api_provider || "Twilio"}
                onChange={(e) => updateSetting("whatsapp_api_provider", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#10b981]"
              >
                <option>Twilio</option>
                <option>Gupshup</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable WhatsApp</span>
          <CustomSwitch
            checked={settings.enable_auto_trading || false}
            onChange={(checked) => updateSetting("enable_auto_trading", checked)}
          />
        </div>
      </div>

      {/* Box 3: Email Alerts */}
      <div className="glass-card p-6 rounded-2xl space-y-5 h-[] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300">
        <div>
          <div className="flex items-center gap-3 border-b border-border pb-3">
            <div className="p-2.5 bg-[#ec4899]/20 rounded-xl text-[#ec4899] shadow-lg shadow-pink-500/10">
              <BarChart className="w-5 h-5" />
            </div>
            <h3 className="font-display font-extrabold text-base text-foreground">Email Alerts</h3>
          </div>

          <div className="space-y-4 mt-4">
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Recipient Email</label>
              <input
                type="email"
                value={settings.recipient_email || "trader@pro.com"}
                onChange={(e) => updateSetting("recipient_email", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground block mb-1.5 uppercase tracking-wider">Alert Type</label>
              <select
                value={settings.email_alert_type || "Summary Only"}
                onChange={(e) => updateSetting("email_alert_type", e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-[#ec4899]"
              >
                <option>Summary Only</option>
                <option>Every Trade</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border">
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Enable Email</span>
          <CustomSwitch
            checked={settings.enable_whatsapp || false}
            onChange={(checked: boolean) => updateSetting("enable_whatsapp", checked)}
          />
        </div>
      </div>

    </div>
  );
}
