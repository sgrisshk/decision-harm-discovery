import type { Metadata } from "next";
import { IBM_Plex_Mono, Open_Sans, Urbanist } from "next/font/google";
import type { ReactNode } from "react";
import "./styles.css";

const display = Urbanist({ subsets: ["latin"], variable: "--font-display" });
const body = Open_Sans({ subsets: ["latin"], variable: "--font-body" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Signal Foundry",
  description: "Evidence-led policy discovery",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable} ${mono.variable}`}>{children}</body>
    </html>
  );
}

