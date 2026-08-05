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
  Fingerprint,
  Sparkles,
  CheckCircle2,
  XCircle,
  BadgeCheck,
  UserPlus,
  LogIn,
  Copy,
  Check,
  Frown
} from "lucide-react";
import { toast } from "sonner";
import Image from "next/image";

interface AuthStatus {
  hasUsers: boolean;
  hasPassword: boolean;
  lockedOut: boolean;
  lockoutSeconds: number;
  userCount?: number;
}

interface UserProfile {
  user_id: string;
  name: string;
  email: string;
}

type ViewState = "login" | "register" | "forgot";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  
  // View Tab
  const [view, setView] = useState<ViewState>("login");
  
  // Registration Success Modal State
  const [createdUserId, setCreatedUserId] = useState<string | null>(null);
  const [copiedUserId, setCopiedUserId] = useState(false);

  // Sign In Form State
  const [userIdOrEmail, setUserIdOrEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Sign Up Form State (Full Name empty by default!)
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientId, setClientId] = useState("");

  // UI Controls
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      // Source of truth is the backend: /api/auth/me only returns 200 if the
      // httpOnly session cookie is present AND still valid server-side.
      // (Previously this just checked whether *any* value existed in
      // localStorage, which anyone could set from devtools to bypass login
      // entirely — see the audit finding this fixes.)
      try {
        const meRes = await fetch(`/api/auth/me`);
        if (meRes.ok) {
          const meData = await meRes.json();
          setIsAuthenticated(true);
          setUserProfile(meData.user);
          try {
            localStorage.setItem("mana_ai_user_profile", JSON.stringify(meData.user));
          } catch {}
        } else {
          setIsAuthenticated(false);
        }
      } catch (e) {
        console.error("Auth check error", e);
        setIsAuthenticated(false);
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
  }, []);

  // Password Complexity Validation Rules
  // Max raised from 15 -> 128: an unnecessarily small cap combined with
  // requiring all 4 character classes needlessly shrinks the keyspace for
  // an otherwise-valid password. Matches api_bridge.py's
  // _validate_password_complexity (server-side is the authoritative check;
  // this must stay in sync so a password valid here isn't rejected there).
  const passwordLengthValid = password.length >= 8 && password.length <= 128;
  const passwordHasUpper = /[A-Z]/.test(password);
  const passwordHasLower = /[a-z]/.test(password);
  const passwordHasNumber = /[0-9]/.test(password);
  const passwordHasSpecial = /[^A-Za-z0-9]/.test(password);

  const isPasswordValid = 
    passwordLengthValid &&
    passwordHasUpper &&
    passwordHasLower &&
    passwordHasNumber &&
    passwordHasSpecial;

  const isEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const isNameValid = name.trim().length >= 2;
  const isConfirmPasswordValid = confirmPassword.length > 0 && confirmPassword === password;

  const isSignUpFormValid = 
    isNameValid && 
    isEmailValid && 
    isPasswordValid && 
    isConfirmPasswordValid;

  const getPasswordStrength = (pass: string) => {
    let score = 0;
    if (!pass) return 0;
    if (pass.length >= 8 && pass.length <= 128) score += 25;
    if (/[A-Z]/.test(pass)) score += 25;
    if (/[a-z]/.test(pass) && /[0-9]/.test(pass)) score += 25;
    if (/[^A-Za-z0-9]/.test(pass)) score += 25;
    return Math.min(100, score);
  };

  const strength = getPasswordStrength(password);

  const getStrengthColor = () => {
    if (strength <= 33) return "bg-rose-500";
    if (strength <= 66) return "bg-amber-500";
    return "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]";
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isSignUpFormValid || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          client_id: clientId.trim()
        })
      });

      const data = await res.json().catch(() => ({ error: `Server error (HTTP ${res.status})` }));

      if (res.ok) {
        const generatedId = data.user_id || data.user?.user_id || "MNA100001";
        setCreatedUserId(generatedId);
        toast.success("Account created successfully.");
        
        // Reset inputs
        setName("");
        setEmail("");
        setEmailError("");
        setPassword("");
        setConfirmPassword("");
      } else {
        const errMsg = data.detail || data.error || "Failed to create account";
        if (errMsg.toLowerCase().includes("already used") || errMsg.toLowerCase().includes("registered")) {
          const customMsg = "Sorry already used this email address";
          setEmailError(customMsg);
          toast.error(customMsg);
        } else {
          toast.error(errMsg);
        }
      }
    } catch (e) {
      toast.error("Network error. Please check backend API connection.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userIdOrEmail.trim() || !loginPassword || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id_or_email: userIdOrEmail.trim(),
          password: loginPassword
        })
      });

      const data = await res.json().catch(() => ({ error: `Server error (HTTP ${res.status})` }));

      if (res.ok) {
        toast.success(`Welcome back, ${data.user?.name || 'Trader'}!`);
        // The real session lives in an httpOnly cookie set by the
        // /api/auth/login route handler itself — nothing to store here.
        if (data.user) {
          try {
            localStorage.setItem("mana_ai_user_profile", JSON.stringify(data.user));
          } catch {}
          setUserProfile(data.user);
        }
        setIsAuthenticated(true);
        setLoginPassword("");
      } else {
        toast.error(data.detail || data.error || "Invalid login credentials");
        if (data.detail && data.detail.includes("Locked out")) {
          setStatus(prev => prev ? { ...prev, lockedOut: true, lockoutSeconds: 300 } : null);
        }
      }
    } catch (e) {
      toast.error("Network error. Please verify backend service.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleResetSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userIdOrEmail.trim() || !clientId.trim() || !isPasswordValid || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id_or_email: userIdOrEmail.trim(),
          client_id: clientId.trim(),
          new_password: password
        })
      });

      const data = await res.json().catch(() => ({ error: `Server error (HTTP ${res.status})` }));

      if (res.ok) {
        toast.success("Password reset successfully. You can now Login.");
        setView("login");
        setLoginPassword("");
        setPassword("");
        setClientId("");
      } else {
        toast.error(data.detail || data.error || "Password reset failed");
      }
    } catch (e) {
      toast.error("Network error. Make sure API bridge is running.");
    } finally {
      setSubmitting(false);
    }
  };

  const copyUserId = () => {
    if (createdUserId) {
      navigator.clipboard.writeText(createdUserId);
      setCopiedUserId(true);
      toast.success("User ID copied to clipboard");
      setTimeout(() => setCopiedUserId(false), 2500);
    }
  };

  if (isAuthenticated) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div data-testid="auth-loading" className="flex min-h-screen items-center justify-center bg-[#030303]">
        <div className="flex flex-col items-center gap-4">
          <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-emerald-500/20 bg-emerald-500/10">
            <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
            <div className="absolute inset-0 rounded-full border-t-2 border-emerald-500 animate-[spin_2s_linear_infinite]" />
          </div>
          <p className="text-xs font-semibold tracking-widest text-muted-foreground/70 uppercase">Initializing Trading Enclave</p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="auth-gate" className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#030303] text-foreground font-sans py-10 px-4">
      
      {/* AI TRADING THEMED BACKGROUND */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] h-[600px] w-[600px] rounded-full bg-emerald-500/10 opacity-30 blur-[140px] mix-blend-screen" />
        <div className="absolute bottom-[-20%] right-[-10%] h-[700px] w-[700px] rounded-full bg-blue-600/10 opacity-30 blur-[160px] mix-blend-screen" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_20%,transparent_100%)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-[460px]"
      >
        <div className="group relative overflow-hidden rounded-[24px] border border-white/10 bg-black/75 p-8 shadow-2xl backdrop-blur-2xl transition-all duration-500">
          
          {/* LOGO & HEADER */}
          <div className="mb-6 text-center">
            <motion.div 
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.1, type: "spring", stiffness: 200 }}
              className="mx-auto mb-2 flex justify-center relative"
            >
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-20 bg-white/15 blur-[25px] rounded-full" />
              
              <div className="relative w-52 h-32 drop-shadow-[0_2px_10px_rgba(255,255,255,0.7)]">
                <Image 
                  src="/mana-logo.png" 
                  alt="MANA AI Logo" 
                  fill 
                  style={{ objectFit: "contain" }}
                  priority
                />
              </div>
            </motion.div>
            
            <p className="text-xs font-semibold tracking-wider text-muted-foreground/80 uppercase">
              Zerodha / Fyers Grade Trading Terminal
            </p>
          </div>

          {/* =========================================
              SUCCESS MODAL (Auto-Generated Trading User ID)
              ========================================= */}
          {createdUserId ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-5 text-center py-2"
            >
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <CheckCircle2 className="h-8 w-8" />
              </div>

              <div>
                <h3 className="text-lg font-bold text-white mb-1">Account created successfully.</h3>
                <p className="text-xs text-muted-foreground">
                  Your Trading User ID has been sent to your registered email.
                </p>
              </div>

              {/* GENERATED USER ID DISPLAY BOX */}
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-center relative">
                <p className="text-[10px] font-bold text-emerald-400/80 uppercase tracking-widest mb-1">
                  YOUR GENERATED TRADING USER ID
                </p>
                <p className="text-2xl font-extrabold text-white font-mono tracking-widest">
                  {createdUserId}
                </p>

                <button
                  type="button"
                  onClick={copyUserId}
                  className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 text-xs font-medium text-white hover:bg-white/10 transition-colors"
                >
                  {copiedUserId ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" /> Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-muted-foreground" /> Copy User ID
                    </>
                  )}
                </button>
              </div>

              <button
                type="button"
                onClick={() => {
                  setUserIdOrEmail("");
                  setCreatedUserId(null);
                  setView("login");
                }}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-white py-3.5 text-sm font-bold text-black hover:bg-gray-100 transition-all shadow-lg"
              >
                Proceed to Login <ArrowRight className="h-4 w-4" />
              </button>
            </motion.div>
          ) : (
            <>
              {/* TAB SWITCHER: SIGN IN | SIGN UP */}
              {view !== "forgot" && (
                <div className="mb-6 flex rounded-xl border border-white/10 bg-white/5 p-1 backdrop-blur-md">
                  <button
                    type="button"
                    data-testid="auth-tab-login"
                    onClick={() => setView("login")}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${
                      view === "login"
                        ? "bg-white text-black shadow-lg"
                        : "text-muted-foreground hover:text-white"
                    }`}
                  >
                    <LogIn className="w-3.5 h-3.5" /> Sign In
                  </button>
                  <button
                    type="button"
                    data-testid="auth-tab-register"
                    onClick={() => setView("register")}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${
                      view === "register"
                        ? "bg-white text-black shadow-lg"
                        : "text-muted-foreground hover:text-white"
                    }`}
                  >
                    <UserPlus className="w-3.5 h-3.5" /> Sign Up
                  </button>
                </div>
              )}

              {/* =========================================
                  VIEW 1: SIGN IN (LOGIN)
                  ========================================= */}
              {view === "login" && (
                <form data-testid="login-form" onSubmit={handleLoginSubmit} className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      User ID or Email
                    </label>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <User className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type="text"
                        data-testid="login-user-id"
                        value={userIdOrEmail}
                        onChange={(e) => setUserIdOrEmail(e.target.value)}
                        disabled={status?.lockedOut || submitting}
                        placeholder="Enter Email or User ID"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 focus:bg-white/10 focus:ring-4 focus:ring-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                        autoFocus
                      />
                    </div>
                  </div>

                  <div>
                    <div className="mb-1.5 flex justify-between items-center">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Password
                      </label>
                      <button
                        type="button"
                        onClick={() => setView("forgot")}
                        className="text-xs font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                        tabIndex={-1}
                      >
                        Forgot Password?
                      </button>
                    </div>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Key className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type={showPassword ? "text" : "password"}
                        data-testid="login-password"
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        disabled={status?.lockedOut || submitting}
                        placeholder="Enter Password"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-11 pr-12 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 focus:bg-white/10 focus:ring-4 focus:ring-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-0 flex items-center pr-4 text-muted-foreground/50 hover:text-white transition-colors"
                        tabIndex={-1}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    data-testid="login-submit"
                    disabled={status?.lockedOut || submitting || !userIdOrEmail.trim() || !loginPassword}
                    className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-white py-3.5 text-sm font-bold text-black transition-all hover:bg-gray-100 hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 mt-2"
                  >
                    {submitting ? (
                      <Loader2 className="h-5 w-5 animate-spin text-black" />
                    ) : (
                      <>Login <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                    )}
                  </button>
                </form>
              )}

              {/* =========================================
                  VIEW 2: SIGN UP (ACCOUNT CREATION)
                  ========================================= */}
              {view === "register" && (
                <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
                  {/* FULL NAME FIELD (Empty by default!) */}
                  <div>
                    <div className="mb-1 flex justify-between items-center">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Full Name
                      </label>
                      {isNameValid && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    </div>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <User className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        disabled={submitting}
                        placeholder="Enter Full Name"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 focus:bg-white/10 focus:ring-4 focus:ring-emerald-500/10"
                        autoFocus
                      />
                    </div>
                  </div>

                  {/* EMAIL ADDRESS FIELD */}
                  <div>
                    <div className="mb-1 flex justify-between items-center">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Email Address
                      </label>
                      {isEmailValid && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    </div>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Mail className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (emailError) setEmailError("");
                        }}
                        disabled={submitting}
                        placeholder="Enter Email Address"
                        className={`block w-full rounded-xl border py-2.5 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:bg-white/10 focus:ring-4 ${
                          emailError 
                            ? "border-rose-500/60 bg-rose-500/5 focus:border-rose-500 focus:ring-rose-500/10" 
                            : "border-white/10 bg-white/5 focus:border-emerald-500/50 focus:ring-emerald-500/10"
                        }`}
                      />
                    </div>
                    {emailError && (
                      <p className="mt-1.5 text-xs font-semibold text-rose-400 flex items-center gap-1.5">
                        <Frown className="w-4 h-4 text-rose-400 shrink-0" /> {emailError}
                      </p>
                    )}
                  </div>

                  {/* PASSWORD FIELD */}
                  <div>
                    <div className="mb-1 flex justify-between items-center">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Password
                      </label>
                      {isPasswordValid && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    </div>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Key className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        disabled={submitting}
                        maxLength={128}
                        placeholder="Enter Password"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-11 pr-12 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 focus:bg-white/10 focus:ring-4 focus:ring-emerald-500/10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-0 flex items-center pr-4 text-muted-foreground/50 hover:text-white transition-colors"
                        tabIndex={-1}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>

                    {/* PASSWORD STRENGTH BAR & HELPER */}
                    <p className="mt-1.5 text-[11px] text-muted-foreground/70 leading-normal">
                      Password must be 8–128 characters long and include uppercase, lowercase, number, and special character.
                    </p>

                    {password.length > 0 && (
                      <div className="mt-2.5 space-y-1.5 overflow-hidden">
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
                        <p className="text-right text-[10px] font-bold text-muted-foreground/70 uppercase tracking-widest">
                          {strength <= 33 && <span className="text-rose-400">Weak</span>}
                          {strength > 33 && strength <= 66 && <span className="text-amber-400">Moderate</span>}
                          {strength > 66 && <span className="text-emerald-400 font-extrabold shadow-[0_0_8px_rgba(16,185,129,0.8)]">Strong</span>}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* CONFIRM PASSWORD FIELD */}
                  <div>
                    <div className="mb-1 flex justify-between items-center">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Confirm Password
                      </label>
                      {confirmPassword.length > 0 && (
                        isConfirmPasswordValid ? (
                          <span className="text-[10px] font-semibold text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Passwords match
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-rose-400 flex items-center gap-1">
                            <XCircle className="w-3 h-3" /> Passwords do not match
                          </span>
                        )
                      )}
                    </div>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Key className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type={showConfirmPassword ? "text" : "password"}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        disabled={submitting}
                        placeholder="Confirm Password"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-11 pr-12 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 focus:bg-white/10 focus:ring-4 focus:ring-emerald-500/10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute inset-y-0 right-0 flex items-center pr-4 text-muted-foreground/50 hover:text-white transition-colors"
                        tabIndex={-1}
                      >
                        {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={submitting || !isSignUpFormValid}
                    className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-white py-3.5 text-sm font-bold text-black transition-all hover:bg-gray-100 hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 mt-4"
                  >
                    {submitting ? (
                      <Loader2 className="h-5 w-5 animate-spin text-black" />
                    ) : (
                      <>Create Account <Sparkles className="h-4 w-4" /></>
                    )}
                  </button>
                </form>
              )}

              {/* =========================================
                  VIEW 3: FORGOT PASSWORD RECOVERY
                  ========================================= */}
              {view === "forgot" && (
                <form onSubmit={handleResetSubmit} className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Enter Email or User ID
                    </label>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <User className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type="text"
                        value={userIdOrEmail}
                        onChange={(e) => setUserIdOrEmail(e.target.value)}
                        disabled={submitting}
                        placeholder="Enter Email or User ID"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50"
                        autoFocus
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Linked Broker Client ID
                    </label>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Fingerprint className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type="text"
                        value={clientId}
                        onChange={(e) => setClientId(e.target.value)}
                        disabled={submitting}
                        placeholder="Enter linked Fyers / Broker Client ID"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-11 pr-4 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50 font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      New Password
                    </label>
                    <div className="relative group/input">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                        <Key className="h-4 w-4 text-muted-foreground/50 transition-colors group-focus-within/input:text-emerald-400" />
                      </div>
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        disabled={submitting}
                        maxLength={128}
                        placeholder="Enter Password"
                        className="block w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-11 pr-12 text-sm text-white placeholder-white/20 outline-none transition-all focus:border-emerald-500/50"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-0 flex items-center pr-4 text-muted-foreground/50 hover:text-white transition-colors"
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setView("login")}
                      className="flex-1 rounded-xl border border-white/10 bg-white/5 py-3 text-xs font-bold text-white hover:bg-white/10 transition-all"
                    >
                      Back to Sign In
                    </button>
                    <button
                      type="submit"
                      disabled={submitting || !userIdOrEmail.trim() || !clientId.trim() || !isPasswordValid}
                      className="flex-1 rounded-xl bg-white py-3 text-xs font-bold text-black hover:bg-gray-100 transition-all disabled:opacity-50"
                    >
                      {submitting ? <Loader2 className="h-4 w-4 animate-spin mx-auto text-black" /> : "Reset Password"}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}

          {/* Lockout Warning */}
          <AnimatePresence>
            {status?.lockedOut && (
              <motion.div
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: "auto", marginTop: 20 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                className="overflow-hidden"
              >
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-center">
                  <p className="text-xs font-medium text-rose-400 flex items-center justify-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5" /> Maximum login attempts exceeded. Locked out for security.
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
