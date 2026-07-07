"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getStoredUser } from "@/lib/session";

const LINKEDIN_LOGIN = "https://www.linkedin.com/login";

/** Backend opens LinkedIn OAuth — step=authorize goes straight to consent when already signed in. */
function linkedInOAuthBeginUrl(state: string, step: "authorize" | "logout" | "go" = "authorize") {
  const q = new URLSearchParams({ state, step });
  return `/api/platforms/linkedin/oauth/begin?${q}`;
}

function LinkedInConnectContent() {
  const router = useRouter();
  const params = useSearchParams();
  const state = params.get("state") || "";
  const step = params.get("step");

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    if (!getStoredUser()) {
      router.replace("/login");
      return;
    }
    if (!state) {
      setError("Invalid connect link. Go back to Recruitment and click Connect LinkedIn again.");
      return;
    }
    // Returned from LinkedIn logout — continue to full login + OAuth (avoids uas/login HTTP 500).
    if (step === "go") {
      window.location.href = linkedInOAuthBeginUrl(state, "go");
    }
  }, [state, step, router]);

  const authorizeApp = useCallback(() => {
    if (!state) return;
    setLoading(true);
    setError("");
    window.location.href = linkedInOAuthBeginUrl(state, "authorize");
  }, [state]);

  const clearSessionAndRetry = useCallback(() => {
    if (!state) return;
    setLoading(true);
    setError("");
    window.location.href = linkedInOAuthBeginUrl(state, "logout");
  }, [state]);

  return (
    <div className="container" style={{ maxWidth: 560, paddingTop: "8vh" }}>
      <div className="card">
        <h2 style={{ marginBottom: "0.5rem" }}>Connect LinkedIn — 2 steps</h2>
        <p style={{ color: "var(--muted)", marginBottom: "1.25rem", fontSize: "0.92rem" }}>
          Sign in on linkedin.com first (step 1), then authorize this app (step 2). Step 2 opens
          LinkedIn&apos;s permission screen directly — it will not sign you out if you just signed in.
        </p>

        <div
          style={{
            marginBottom: "1rem",
            padding: "1rem",
            background: "var(--surface2)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Step 1 — Sign in to LinkedIn</div>
          <a
            href={LINKEDIN_LOGIN}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary"
            style={{ display: "block", textAlign: "center", textDecoration: "none" }}
          >
            Open linkedin.com/login ↗
          </a>
        </div>

        <div
          style={{
            marginBottom: "1rem",
            padding: "1rem",
            background: "var(--surface2)",
            borderRadius: 8,
            border: signedIn ? "2px solid var(--accent)" : "1px solid var(--border)",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Step 2 — Authorize this app</div>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              fontSize: "0.9rem",
              marginBottom: "0.85rem",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={signedIn}
              onChange={(e) => setSignedIn(e.target.checked)}
            />
            I signed in to LinkedIn successfully
          </label>
          <button
            type="button"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={!signedIn || loading || !state}
            onClick={authorizeApp}
          >
            {loading ? "Authorizing..." : "Authorize app on LinkedIn"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ width: "100%", marginTop: "0.65rem", fontSize: "0.85rem" }}
            disabled={loading || !state}
            onClick={clearSessionAndRetry}
          >
            Having trouble? Clear LinkedIn session first
          </button>
        </div>

        {error && <p className="error" style={{ marginBottom: "1rem" }}>{error}</p>}

        <button
          type="button"
          className="btn btn-secondary"
          style={{ width: "100%" }}
          onClick={() => router.push("/recruitment")}
        >
          Back to Recruitment
        </button>
      </div>
    </div>
  );
}

export default function LinkedInConnectPage() {
  return (
    <Suspense fallback={<div className="container" style={{ paddingTop: "12vh", textAlign: "center" }}>Loading...</div>}>
      <LinkedInConnectContent />
    </Suspense>
  );
}
