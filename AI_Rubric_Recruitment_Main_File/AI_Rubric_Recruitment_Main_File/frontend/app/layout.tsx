import type { Metadata } from "next";
import "./globals.css";
import BackendConfig from "@/components/BackendConfig";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "AI Recruiter — Trusted AI for Smarter Hiring",
  description:
    "AI-powered recruitment platform for job descriptions, resume screening, and team collaboration.",
};

function serverBackendUrl(): string {
  return (
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    ""
  ).replace(/\/$/, "");
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const backendUrl = serverBackendUrl();

  return (
    <html lang="en">
      <head>
        {backendUrl ? (
          <script
            dangerouslySetInnerHTML={{
              __html: `window.__BACKEND_URL__=${JSON.stringify(backendUrl)};`,
            }}
          />
        ) : null}
      </head>
      <body suppressHydrationWarning>
        <BackendConfig backendUrl={backendUrl} />
        {children}
      </body>
    </html>
  );
}
