import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Working palette — refined when the design language lands.
        aegis: {
          bg: "#0b0d10",
          panel: "#121519",
          border: "#1f242c",
          text: "#e8ecf1",
          muted: "#8a93a0",
          accent: "#5eead4",
          danger: "#f87171",
          warn: "#fbbf24",
          ok: "#4ade80",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
