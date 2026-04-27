import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#1f4e79",
          50: "#eef4fa",
          100: "#d3e2f0",
          200: "#a8c5e0",
          300: "#7da9d1",
          400: "#528cc1",
          500: "#1f4e79",
          600: "#194064",
          700: "#13314e",
          800: "#0e2238",
          900: "#081523",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
