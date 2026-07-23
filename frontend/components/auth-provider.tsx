"use client";

import React, { useState, useEffect, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Lock, 
  ShieldCheck, 
  Key, 
  ArrowRight, 
  Loader2, 
  User, 
  AlertCircle,
  Eye,
  EyeOff,
  Mail,
  BrainCircuit,
  Activity,
  Fingerprint,
  Sparkles
} from "lucide-react";
import { toast } from "sonner";
import Image from "next/image";

interface AuthStatus {
  hasPassword: boolean;
  lockedOut: boolean;
  lockoutSeconds: number;
}

type ViewState = "login" | "register" | "forgot";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  
  // Form States
  const [view, setView] = useState<ViewState>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [clientId, setClientId] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

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
    
    if (view === "register") {
      setSubmitting(true);
      // Simulate a network delay for realism
      await new Promise(r => setTimeout(r, 1200));
      setSubmitting(false);
      toast.error("System is locked to a single administrator account. Registration is disabled.", {
        icon: <ShieldCheck className="h-5 w-5 text-rose-500" />
      });
      return;
    }

    if (!password) {
      toast.error("Password is required");
      return;
    }

    if (view === "forgot" && !clientId) {
      toast.error("Broker Client ID is required for recovery");
      return;
    }
    
    setSubmitting(true);
    try {
      let endpoint = status?.hasPassword ? `/api/auth/login` : `/api/auth/setup`;
      let body: any = { password };

      if (view === "forgot") {
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
        toast.success(
          view === "forgot" ? "Password Reset Successfully" : 
          (status?.hasPassword ? "Access Granted" : "Password Set Successfully")
        );
        localStorage.setItem("mana_ai_auth_token", "mana_ai_auth_v1_valid");
        setIsAuthenticated(true);
        setView("login");
        setPassword("");
        setClientId("");
      } else {
        toast.error(data.detail || data.error || "Authentication failed");
        if (data.detail && data.detail.includes("Locked out")) {
          setStatus(prev => prev ? { ...prev, lockedOut: true, lockoutSeconds: 120 } : null);
        }
      }
    } catch (e) {
      toast.error("Network error. Make sure API Bridge is running.");
    } finally {
      setSubmitting(false);
      if (view !== "forgot") {
        setPassword("");
      }
    }
  };

  if (isAuthenticated) {
    return <>{children}</>;
  }

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

  // Determine actual setup mode
  const isSetupMode = !status?.hasPassword && view === "login";

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#030303] text-foreground font-sans">
      
      {/* 
        ========================================
        AI TRADING THEMED BACKGROUND
        ========================================
      */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        {/* Core Glowing Orbs */}
        <div className="absolute top-[-10%] left-[-10%] h-[600px] w-[600px] rounded-full bg-primary/10 opacity-40 blur-[120px] mix-blend-screen" />
        <div className="absolute bottom-[-20%] right-[-10%] h-[700px] w-[700px] rounded-full bg-blue-600/10 opacity-30 blur-[150px] mix-blend-screen" />
        
        {/* Animated AI Network Grid Effect */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_20%,transparent_100%)]" />
        
        {/* Data Stream Lines (Simulated AI processing) */}
        <motion.div 
          animate={{ y: [0, -1000] }} 
          transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
          className="absolute inset-0 opacity-[0.03]"
        >
          {Array.from({ length: 15 }).map((_, i) => (
            <div 
              key={i} 
              className="absolute w-[1px] bg-gradient-to-b from-transparent via-primary to-transparent"
              style={{
                left: `${Math.random() * 100}%`,
                height: `${200 + Math.random() * 300}px`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 5}s`
              }}
            />
          ))}
        </motion.div>

        {/* Ambient Noise */}
        <div className="absolute inset-0 bg-[url('/noise.png')] opacity-[0.02] mix-blend-overlay" />
      </div>

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-[440px] px-4"
      >
        <div className="group relative overflow-hidden rounded-[24px] border border-white/10 bg-black/60 p-8 shadow-2xl backdrop-blur-2xl transition-all duration-500 hover:border-primary/20 hover:shadow-primary/5">
          
          {/* Subtle Glow Border on Hover */}
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
          
          {/* 
            ========================================
            SYSTEM LOGO & HEADER
            ========================================
          */}
          <div className="mb-8 text-center">
            <motion.div 
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
              className="mx-auto mb-4 flex justify-center relative"
            >
              {/* Bright glowing background to make dark text readable */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-20 bg-white/20 blur-[25px] rounded-full" />
              
              <div className="relative w-56 h-36 drop-shadow-[0_2px_10px_rgba(255,255,255,0.8)]">
                <Image 
                  src="/mana-logo.png" 
                  alt="MANA AI Logo" 
                  fill 
                  style={{ objectFit: "contain", filter: "drop-shadow(0 0 2px rgba(255,255,255,0.5))" }}
                  priority
                />
              </div>
            </motion.div>
            
            <p className="text-sm font-medium text-muted-foreground/70">
              {view === "register" 
                ? "Apply for Institutional Access"
                : view === "forgot" 
                ? "Recover System Credentials"
                : isSetupMode
                ? "Initialize Secure Terminal"
                : "Sign in to trading terminal"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <AnimatePresence mode="popLayout">
              
              {/* 
                ========================================
                EMAIL / USERNAME / CLIENT ID FIELD
                ========================================
              */}
              {(view === "login" || view === "register") && (
                <motion.div
                  key="email-field"
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.3 }}
                >
                  <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Email Address
                  </label>
                  <div className="relative group/input">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                      <Mail className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-primary" />
                    </div>
                    <input
                      type="text"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={status?.lockedOut || submitting}
                      placeholder="trader@institution.com"
                      className="block w-full rounded-xl border border-white/10 bg-white/5 py-3.5 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-primary/50 focus:bg-white/10 focus:ring-4 focus:ring-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                  </div>
                </motion.div>
              )}

              {view === "forgot" && (
                <motion.div
                  key="client-id-field"
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.3 }}
                >
                  <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Broker Client ID
                  </label>
                  <div className="relative group/input">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                      <Fingerprint className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-primary" />
                    </div>
                    <input
                      type="text"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      disabled={status?.lockedOut || submitting}
                      placeholder="Enter linked Broker ID"
                      className="block w-full rounded-xl border border-white/10 bg-white/5 py-3.5 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-primary/50 focus:bg-white/10 focus:ring-4 focus:ring-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                      autoFocus
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-muted-foreground/60 leading-relaxed">
                    For security reasons, password recovery requires verification of the broker client ID connected to this engine.
                  </p>
                </motion.div>
              )}

              {/* 
                ========================================
                PASSWORD FIELD
                ========================================
              */}
              <motion.div
                key="password-field"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3, delay: 0.05 }}
              >
                <div className="mb-1.5 flex justify-between items-center">
                  <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {view === "register" || view === "forgot" || isSetupMode ? "New Password" : "Password"}
                  </label>
                  {view === "login" && (
                    <button
                      type="button"
                      onClick={() => setView("forgot")}
                      className="text-xs font-medium text-primary/80 hover:text-primary transition-colors"
                      tabIndex={-1}
                    >
                      Forgot?
                    </button>
                  )}
                </div>
                <div className="relative group/input">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                    <Key className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-primary" />
                  </div>
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={status?.lockedOut || submitting}
                    placeholder="••••••••••••"
                    className="block w-full rounded-xl border border-white/10 bg-white/5 py-3.5 pl-11 pr-12 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-primary/50 focus:bg-white/10 focus:ring-4 focus:ring-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  {/* Eye Icon for Show/Hide Password */}
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 flex items-center pr-4 text-muted-foreground/50 hover:text-white transition-colors focus:outline-none"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                {/* Password Strength Indicator (Setup/Recovery/Register) */}
                <AnimatePresence>
                  {(isSetupMode || view === "forgot" || view === "register") && password.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="pt-3 overflow-hidden"
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
                      <p className="mt-1.5 text-right text-[10px] font-medium text-muted-foreground/60 uppercase tracking-widest">
                        {strength <= 25 && "Weak"}
                        {strength > 25 && strength <= 50 && "Fair"}
                        {strength > 50 && strength <= 75 && "Good"}
                        {strength > 75 && "Institutional Grade"}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </AnimatePresence>

            {/* 
              ========================================
              SUBMIT BUTTON
              ========================================
            */}
            <motion.div
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="pt-2"
            >
              <button
                type="submit"
                disabled={status?.lockedOut || submitting || !password || (view === "forgot" && !clientId) || ((isSetupMode || view === "register") && strength < 50)}
                className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-white py-3.5 text-sm font-bold text-black transition-all hover:bg-gray-100 hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-none"
              >
                {submitting ? (
                  <Loader2 className="h-5 w-5 animate-spin text-black" />
                ) : view === "register" ? (
                  <>Create Account <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                ) : view === "forgot" ? (
                  <>Reset Password <ShieldCheck className="h-4 w-4" /></>
                ) : isSetupMode ? (
                  <>Initialize Engine <Sparkles className="h-4 w-4" /></>
                ) : (
                  <>Sign In <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                )}
              </button>
            </motion.div>
          </form>
          
          {/* 
            ========================================
            BOTTOM NAVIGATION (Register / Sign In)
            ========================================
          */}
          <motion.div 
            layout
            className="mt-6 text-center"
          >
              {view === "login" ? (
                <p className="text-xs text-muted-foreground">
                  Don't have an account?{" "}
                  <button 
                    onClick={() => setView("register")}
                    className="font-semibold text-white hover:text-primary transition-colors hover:underline underline-offset-4"
                  >
                    Sign Up
                  </button>
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Already have an account?{" "}
                  <button 
                    onClick={() => setView("login")}
                    className="font-semibold text-white hover:text-primary transition-colors hover:underline underline-offset-4"
                  >
                    Sign In
                  </button>
                </p>
              )}
          </motion.div>
          
          {/* Lockout Warning */}
          <AnimatePresence>
            {status?.lockedOut && (
              <motion.div
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: "auto", marginTop: 24 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                className="overflow-hidden"
              >
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-center">
                  <p className="text-xs font-medium text-rose-400 flex items-center justify-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5" /> Maximum attempts reached. Locked.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

        </div>
      </motion.div>
    </div>
  );
}
