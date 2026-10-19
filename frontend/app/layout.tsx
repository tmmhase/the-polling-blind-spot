import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Polling Blind Spot",
  description:
    "Historical U.S. Senate polling error for 2018–2024, with a hierarchical uncertainty model and backtest.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
