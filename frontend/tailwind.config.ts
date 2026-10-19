import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f3efe6",
        ink: "#1c1915",
        muted: "#5e584e",
        line: "#d9d1c3",
        card: "#faf7f1",
        copper: "#8d4e2f",
        dem: "#1d4e89",
        rep: "#8d2f2f",
      },
      fontFamily: {
        serif: ["Newsreader", "Iowan Old Style", "Georgia", "serif"],
        sans: ["Public Sans", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(28, 25, 21, 0.05), 0 16px 40px rgba(28, 25, 21, 0.05)",
      },
    },
  },
  plugins: [],
};

export default config;
