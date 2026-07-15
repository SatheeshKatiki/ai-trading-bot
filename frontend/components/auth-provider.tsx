"use client";

import React, { useState, useEffect, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, ShieldCheck, Key, ArrowRight, Loader2, Sparkles, Fingerprint, User, AlertCircle } from "lucide-react";
import { toast } from "sonner";

interface AuthStatus {
  hasPassword: boolean;
  lockedOut: boolean;
  lockoutSeconds: number;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [password, setPassword] = useState("");
  const [clientId, setClientId] = useState("");
  const [isRecovering, setIsRecovering] = useState(false);
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Simple auto-lock timer (Temporarily disabled for local development)
  /*
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    
    const resetTimer = () => {
      clearTimeout(timeoutId);
      // Auto lock after 30 mins of inactivity
      timeoutId = setTimeout(() => {
        if (isAuthenticated) {
          setIsAuthenticated(false);
          toast("Session Locked", { description: "Your session was locked due to inactivity." });
        }
      }, 30 * 60 * 1000);
    };

    if (isAuthenticated) {
      window.addEventListener("mousemove", resetTimer);
      window.addEventListener("keydown", resetTimer);
      resetTimer();
    }

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("mousemove", resetTimer);
      window.removeEventListener("keydown", resetTimer);
    };
  }, [isAuthenticated]);
  */

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem("mana_ai_auth_token");
      if (token) {
        setIsAuthenticated(true);
      }
      
      try {
        const res = await fetch(`/api/auth/status`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
        }
      } catch (e) {
        console.error("Auth status error", e);
      } finally {
        setLoading(false);
      }
    };
    
    checkAuth();
  }, [isAuthenticated]);

  const getPasswordStrength = (pass: string) => {
    let score = 0;
    if (!pass) return 0;
    if (pass.length >= 8) score += 25;
    if (/[A-Z]/.test(pass)) score += 25;
    if (/[0-9]/.test(pass)) score += 25;
    if (/[^A-Za-z0-9]/.test(pass)) score += 25;
    return Math.min(100, score);
  };

  const strength = getPasswordStrength(password);
  
  const getStrengthColor = () => {
    if (strength <= 25) return "bg-rose-500";
    if (strength <= 50) return "bg-amber-500";
    if (strength <= 75) return "bg-emerald-400";
    return "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return;
    if (isRecovering && !clientId) return;
    
    setSubmitting(true);
    try {
      let endpoint = status?.hasPassword ? `/api/auth/login` : `/api/auth/setup`;
      let body: any = { password };

      if (isRecovering) {
        endpoint = `/api/auth/reset`;
        body = { client_id: clientId, new_password: password };
      }
      
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(isRecovering ? "Password Reset Successfully" : (status?.hasPassword ? "Access Granted" : "Password Set Successfully"));
        localStorage.setItem("mana_ai_auth_token", "mana_ai_auth_v1_valid");
        setIsAuthenticated(true);
        setIsRecovering(false);
        setPassword("");
        setClientId("");
      } else {
        toast.error(data.detail || "Authentication failed");
        if (data.detail && data.detail.includes("Locked out")) {
          setStatus(prev => prev ? { ...prev, lockedOut: true, lockoutSeconds: 120 } : null);
        }
      }
    } catch (e) {
      toast.error("Network error. Make sure API Bridge is running.");
    } finally {
      setSubmitting(false);
      if (!isRecovering) {
        setPassword("");
      }
    }
  };

  // Allow passing through if already authenticated
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // Show loading skeleton while checking
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050505]">
        <div className="flex flex-col items-center gap-4">
          <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-primary/20 bg-primary/10">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <div className="absolute inset-0 rounded-full border-t-2 border-primary animate-[spin_2s_linear_infinite]" />
          </div>
          <p className="text-sm font-medium tracking-widest text-muted-foreground/60 uppercase">Initializing Secure Enclave</p>
        </div>
      </div>
    );
  }

  const isSetupOrRecovery = !status?.hasPassword || isRecovering;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#030303] text-foreground">
      {/* Dynamic Background */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-1/4 left-1/4 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 opacity-30 blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 h-[600px] w-[600px] translate-x-1/2 translate-y-1/2 rounded-full bg-blue-500/10 opacity-20 blur-[150px]" />
        <div className="absolute inset-0 bg-[url('/noise.png')] opacity-[0.03] mix-blend-overlay" />
      </div>

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-md"
      >
        <div className="group relative overflow-hidden rounded-[24px] border border-white/10 bg-black/40 p-8 pt-10 shadow-2xl backdrop-blur-2xl transition-all duration-500 hover:border-primary/30">
          
          {/* Subtle Glow Border on Hover */}
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-primary/10 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
          
          <div className="mb-8 text-center">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-white/5 to-white/0 shadow-inner">
              {isRecovering ? (
                <ShieldCheck className="h-10 w-10 text-amber-500 drop-shadow-[0_0_15px_rgba(245,158,11,0.5)]" />
              ) : status?.hasPassword ? (
                <Fingerprint className="h-10 w-10 text-primary drop-shadow-[0_0_15px_rgba(var(--primary-rgb),0.5)]" />
              ) : (
                <ShieldCheck className="h-10 w-10 text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]" />
              )}
            </div>
            <h1 className="mb-2 text-3xl font-semibold tracking-tight text-white">
              {isRecovering ? "Account Recovery" : status?.hasPassword ? "System Access" : "Initialize Terminal"}
            </h1>
            <p className="text-sm font-medium text-muted-foreground/70">
              {isRecovering 
                ? "Enter your Broker Client ID to securely reset your password."
                : status?.hasPassword 
                ? "Enter your master password to unlock the institutional dashboard."
                : "Create a secure master password to protect your trading engine."}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <AnimatePresence mode="popLayout">
              {isRecovering && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="space-y-2"
                >
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                      <User className="h-5 w-5 text-muted-foreground/50 transition-colors group-focus-within:text-primary" />
                    </div>
                    <input
                      type="text"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      disabled={status?.lockedOut || submitting}
                      placeholder="Broker Client ID (e.g. 0KHBQ6IQA4-100)"
                      className="block w-full rounded-xl border border-white/10 bg-black/50 py-4 pl-12 pr-4 text-sm text-white placeholder-white/30 outline-none ring-offset-black transition-all focus:border-primary/50 focus:bg-white/5 focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                      autoFocus={isRecovering}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="space-y-2">
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                  <Key className="h-5 w-5 text-muted-foreground/50 transition-colors group-focus-within:text-primary" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={status?.lockedOut || submitting}
                  placeholder={isRecovering || !status?.hasPassword ? "New Master Password" : "Master Password"}
                  className="block w-full rounded-xl border border-white/10 bg-black/50 py-4 pl-12 pr-4 text-sm text-white placeholder-white/30 outline-none ring-offset-black transition-all focus:border-primary/50 focus:bg-white/5 focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                  autoFocus={!isRecovering}
                />
              </div>

              {/* Password Strength Indicator */}
              <AnimatePresence>
                {isSetupOrRecovery && password.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="pt-2"
                  >
                    <div className="flex gap-1.5 h-1.5 w-full">
                      {[1, 2, 3, 4].map((bar) => (
                        <div key={bar} className="h-full flex-1 rounded-full bg-white/10 overflow-hidden">
                          <div 
                            className={`h-full transition-all duration-300 ${getStrengthColor()}`} 
                            style={{ width: strength >= bar * 25 ? "100%" : "0%" }}
                          />
                        </div>
                      ))}
                    </div>
                    <p className="mt-2 text-right text-xs font-medium text-muted-foreground/60">
                      {strength <= 25 && "Weak"}
                      {strength > 25 && strength <= 50 && "Fair"}
                      {strength > 50 && strength <= 75 && "Good"}
                      {strength > 75 && "Institutional Grade"}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button
              type="submit"
              disabled={status?.lockedOut || submitting || !password || (isRecovering && !clientId) || (isSetupOrRecovery && strength < 50)}
              className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-white py-4 text-sm font-bold text-black transition-all hover:bg-white/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 className="h-5 w-5 animate-spin text-black" />
              ) : isRecovering ? (
                <>Reset Secure Access <ShieldCheck className="h-4 w-4" /></>
              ) : status?.hasPassword ? (
                <>Unlock System <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
              ) : (
                <>Secure Engine <Sparkles className="h-4 w-4" /></>
              )}
            </button>
          </form>
          
          <AnimatePresence>
            {status?.lockedOut && (
              <motion.div
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: "auto", marginTop: 24 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                className="overflow-hidden"
              >
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-center">
                  <p className="text-sm font-medium text-rose-400 flex items-center justify-center gap-2">
                    <AlertCircle className="w-4 h-4" /> Maximum attempts reached. Locked.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Forgot Password Toggle */}
          {status?.hasPassword && !status?.lockedOut && (
            <div className="mt-6 text-center">
              <button 
                onClick={() => {
                  setIsRecovering(!isRecovering);
                  setPassword("");
                  setClientId("");
                }}
                className="text-sm font-medium text-muted-foreground/60 transition-colors hover:text-white"
              >
                {isRecovering ? "Back to Secure Login" : "Forgot Master Password?"}
              </button>
            </div>
          )}

        </div>
        
        {/* Footer info */}
        <div className="mt-8 flex items-center justify-center gap-4 text-xs font-medium uppercase tracking-widest text-muted-foreground/40">
          <span>Encrypted Engine</span>
          <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
          <span>Institutional Grade</span>
          <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
          <span>v2.0 Ultra</span>
        </div>
      </motion.div>
    </div>
  );
}
