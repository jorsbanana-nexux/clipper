import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clipper — AI Podcast Clipper",
  description: "Paste a link, get viral 9:16 clips with word-by-word captions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
