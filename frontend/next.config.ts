import type { NextConfig } from "next";

// Build-time env validation: BACKEND_URL is what every app/api/** proxy
// route forwards to (see lib/backend.ts). It silently falls back to
// http://127.0.0.1:8000 when unset -- fine for local dev where the
// FastAPI bridge runs on the same machine, but almost certainly wrong
// for a real deployment where the backend is on a different host. This
// only warns (doesn't fail the build) since we can't know every
// deployment's intent, but it makes a likely misconfiguration visible
// at build time instead of surfacing later as broken API calls.
if (process.env.NODE_ENV === "production" && !process.env.BACKEND_URL) {
  console.warn(
    "[next.config.ts] WARNING: BACKEND_URL is not set for a production build -- " +
    "API routes will fall back to http://127.0.0.1:8000, which is almost " +
    "certainly wrong outside local dev. Set BACKEND_URL to the real backend origin."
  );
}

// Baseline security headers. The CSP still allows 'unsafe-inline'/'unsafe-eval'
// for script-src because Next.js injects inline hydration scripts and (in dev)
// relies on eval for HMR; tightening that to a nonce/strict-dynamic policy
// would need broader middleware changes and is out of scope here. This is
// meant as defense-in-depth (clickjacking, MIME sniffing, referrer leakage),
// not a replacement for proper output encoding/XSS review elsewhere.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  // Direct browser->backend WebSocket ticks (components/live-ticker.tsx,
  // store/useLiveMarketStore.ts) don't go through the app/api/** proxy, so
  // 'self' alone isn't enough -- allow ws/wss generally rather than
  // hardcoding a host:port that changes between local dev and deployment.
  "connect-src 'self' ws: wss:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  experimental: {
    optimizePackageImports: ['lucide-react', 'recharts'],
  },
  images: {
    // No remote images are loaded anywhere in the app today (both <Image>
    // usages point at local files under /public) -- keep it that way
    // explicitly rather than relying on the implicit default.
    remotePatterns: [],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
