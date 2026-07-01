import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f0f9ff",
          500: "#0ea5e9",
          600: "#0284c7",
          900: "#0c4a6e",
        },
        surface: {
          900: "#0f1117",
          800: "#161b22",
          700: "#1c2333",
          600: "#21262d",
        },
      },
    },
  },
  plugins: [],
};

export default config;
