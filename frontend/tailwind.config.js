import tailwindcssAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Telemetry severity + signal accents
        signal: {
          ok: "hsl(var(--signal-ok))",
          warn: "hsl(var(--signal-warn))",
          error: "hsl(var(--signal-error))",
          info: "hsl(var(--signal-info))",
          accent: "hsl(var(--signal-accent))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "pulse-node": {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 0 0 hsl(var(--signal-accent) / 0.5)" },
          "50%": { opacity: "0.85", boxShadow: "0 0 0 8px hsl(var(--signal-accent) / 0)" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // The Cognition view's slow ~20s pulse — synced to Orrin's cycle so the
        // page "breathes" (§9.3). Deliberately subtle (a faint ring/opacity swell).
        breathe: {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 0 0 hsl(var(--signal-accent) / 0.18)" },
          "50%": { opacity: "0.97", boxShadow: "0 0 0 6px hsl(var(--signal-accent) / 0)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "pulse-node": "pulse-node 1.6s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out",
        breathe: "breathe 20s ease-in-out infinite",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
