import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "AI Intraday Trading Platform",
  description: "Premium AI-powered trading platform for Indian markets",
};

import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "sonner";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  const theme = localStorage.getItem('theme') || 'dark';
                  const accentColor = localStorage.getItem('accentColor') || '#ff4d4d';
                  const density = localStorage.getItem('density') || 'compact';
                  const glassEnabled = localStorage.getItem('glassEnabled') !== 'false';
                  
                  if (theme === 'light') document.documentElement.classList.add('light');
                  document.documentElement.style.setProperty('--primary', accentColor);
                  
                  // Calculate RGB for glow effects
                  const hex = accentColor.replace('#', '');
                  const r = parseInt(hex.substring(0, 2), 16);
                  const g = parseInt(hex.substring(2, 4), 16);
                  const b = parseInt(hex.substring(4, 6), 16);
                  if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
                    document.documentElement.style.setProperty('--primary-rgb', r + ', ' + g + ', ' + b);
                    document.documentElement.style.setProperty('--glow-primary', 'rgba(' + r + ', ' + g + ', ' + b + ', 0.25)');
                  }

                  if (density === 'spacious') document.documentElement.classList.add('spacious-mode');
                  if (!glassEnabled) document.documentElement.classList.add('no-glass');
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className={`${inter.variable} ${poppins.variable} font-sans min-h-full bg-background text-foreground antialiased`}>
        <ThemeProvider>
          {children}
          <Toaster position="top-right" richColors closeButton />
        </ThemeProvider>
      </body>
    </html>
  );
}
