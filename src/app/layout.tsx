import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Inter, Source_Serif_4 } from "next/font/google";
import { ThemeProvider } from "@/lib/theme-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GWhFi - Turning Wasted Energy Into Heat and Revenue",
  description:
    "GWhFi deploys programmable Bitcoin mining ASIC heaters that replace immersion elements in hot water cylinders. Heat water, mine Bitcoin, and earn grid flexibility payments from surplus renewable energy.",
  keywords: [
    "energy flexibility",
    "renewable energy",
    "grid balancing",
    "Bitcoin mining",
    "hot water",
    "UK energy",
    "curtailment",
  ],
  authors: [{ name: "GWhFi" }],
  openGraph: {
    title: "GWhFi - Turning Wasted Energy Into Heat and Revenue",
    description:
      "Programmable ASIC heaters that turn curtailed renewable energy into hot water, Bitcoin revenue, and grid flexibility payments.",
    url: "https://gwhfi.com",
    siteName: "GWhFi",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#1A2332",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} ${sourceSerif.variable}`}
      suppressHydrationWarning
    >
      <body className="font-sans antialiased">
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
