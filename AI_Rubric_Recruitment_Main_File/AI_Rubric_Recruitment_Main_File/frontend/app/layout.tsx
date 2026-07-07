import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Recruiter — Trusted AI for Smarter Hiring",
  description:
    "AI-powered recruitment platform for job descriptions, resume screening, and team collaboration.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
