/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces: a cool slate instrument panel, deliberately not near-black.
        ground: "#0F151C",
        panel: "#151D26",
        raised: "#1C2733",
        line: "#263341",
        "line-soft": "#1E2A36",

        // Ink, three steps. ink-3 is the floor that still clears 4.5:1 on panel.
        ink: "#E6ECF2",
        "ink-2": "#9BAAB9",
        "ink-3": "#7C8B9B",

        // Market axis: opportunity magnitude is sequential, never diverging.
        // There is no loss state in a detection-only system, so green is free.
        signal: {
          low: "#1E4D3A",
          mid: "#2E8F63",
          DEFAULT: "#3ECF8E",
          hi: "#7BE8B8",
        },

        // System axis: reserved for trouble only. Healthy renders in plain ink.
        // Pair validated at deutan dE 19.0 / normal dE 26.5 against each other.
        warn: "#F5C451",
        crit: "#F2546B",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "4px",
      },
      fontSize: {
        micro: ["11px", { lineHeight: "14px" }],
      },
    },
  },
  plugins: [],
};
