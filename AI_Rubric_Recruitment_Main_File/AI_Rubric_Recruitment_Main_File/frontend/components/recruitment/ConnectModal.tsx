"use client";

import { useEffect, useState } from "react";
import { Platform, PlatformConnection } from "@/lib/recruitment-api";

interface Props {
  platform: Platform;
  userEmail: string;
  userName: string;
  onClose: () => void;
  onConnected: (conn: PlatformConnection) => void;
  connectFn: (platformId: string, email: string, password: string) => Promise<PlatformConnection>;
  quickConnectFn: (platformId: string) => Promise<PlatformConnection>;
  googleConnectFn: (platformId: string) => Promise<{
    auth_url: string | null;
    mode: "oauth" | "quick";
    connection?: PlatformConnection;
  }>;
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export default function ConnectModal({
  platform,
  userEmail,
  userName,
  onClose,
  onConnected,
  connectFn,
  quickConnectFn,
  googleConnectFn,
}: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const isLinkedIn = platform.id === "linkedin";

  useEffect(() => {
    setEmail(isLinkedIn ? "" : userEmail);
    setPassword("");
    setError("");
    setLoading(false);
  }, [platform.id, userEmail, isLinkedIn]);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const conn = await connectFn(platform.id, email, isLinkedIn ? "" : password);
      onConnected(conn);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleQuickConnect() {
    setError("");
    setLoading(true);
    try {
      const conn = await quickConnectFn(platform.id);
      onConnected(conn);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    setError("");
    setLoading(true);
    try {
      const result = await googleConnectFn(platform.id);
      if (result.mode === "oauth" && result.auth_url) {
        window.location.href = result.auth_url;
        return;
      }
      if (result.connection) {
        onConnected(result.connection);
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google connect failed");
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>

        <div className={`platform-icon ${platform.logo} modal-platform-icon`}>
          {platform.name.slice(0, 2).toUpperCase()}
        </div>
        <h2 className="modal-title">Connect {platform.name}</h2>

        {isLinkedIn ? (
          <>
            <p className="modal-subtitle">
              Two steps on linkedin.com: (1) sign in on the full login page, (2) authorize this app.
              Complete step 1 in this browser, then return here for step 2.
            </p>

            {error && <p className="error">{error}</p>}

            <button
              type="button"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: "100%" }}
              onClick={() => {
                setError("");
                setLoading(true);
                connectFn(platform.id, "", "")
                  .then(() => {})
                  .catch((err) => {
                    setError(err instanceof Error ? err.message : "Connection failed");
                    setLoading(false);
                  });
              }}
            >
              {loading ? (
                <>
                  <span className="spinner" /> Starting...
                </>
              ) : (
                "Connect LinkedIn (2 steps)"
              )}
            </button>

            <p className="modal-note" style={{ marginTop: "1rem" }}>
              Works in Incognito too — always complete step 1 (linkedin.com/login) before step 2.
            </p>
          </>
        ) : (
          <>
            <p className="modal-subtitle">
              Link <strong>your own</strong> {platform.name} employer account.
              Signed in to this portal as <strong>{userEmail}</strong> — use your{" "}
              {platform.name} credentials below (each recruiter has their own).
            </p>

            <button
              className="btn btn-google"
              onClick={handleGoogle}
              disabled={loading}
              style={{ width: "100%", marginBottom: "0.75rem" }}
            >
              <GoogleIcon />
              Continue with Google
            </button>

            {userEmail && (
              <button
                className="btn btn-account"
                onClick={handleQuickConnect}
                disabled={loading}
                style={{ width: "100%", marginBottom: "1rem" }}
              >
                Use my portal email ({userEmail})
              </button>
            )}

            <div className="modal-divider">
              <span>or sign in with {platform.name} email</span>
            </div>

            <form onSubmit={handleConnect}>
              <div className="form-group">
                <label className="label">{platform.name} Email</label>
                <input
                  className="input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your-employer@company.com"
                  required
                />
              </div>
              <div className="form-group">
                <label className="label">{platform.name} Password</label>
                <input
                  className="input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={6}
                />
              </div>

              {error && <p className="error">{error}</p>}

              <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: "100%" }}>
                {loading ? (
                  <>
                    <span className="spinner" /> Connecting...
                  </>
                ) : (
                  `Connect ${platform.name}`
                )}
              </button>
            </form>

            <p className="modal-note">
              Your {platform.name} password is never stored. Each recruiter connects
              only their own account while logged into their portal session.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
