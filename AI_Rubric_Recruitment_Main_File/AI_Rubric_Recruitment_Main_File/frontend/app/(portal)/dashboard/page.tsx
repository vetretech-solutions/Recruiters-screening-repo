"use client";

import { useEffect, useState } from "react";
import { portalApi, PortalUser } from "@/lib/portal-api";
import { NAV_CONFIG, navItemsForRole, WORKSPACE_NAV_KEYS } from "@/lib/portal-nav";
import { getStoredToken, getStoredUser, saveSession } from "@/lib/session";

const WORKSPACE_LABELS: Record<string, string> = {
  recruitment: "Recruitment — create job posts and manage applicants",
  screening: "Rubric Screening — score resumes with AI rubrics",
};

function formatRole(role: string) {
  return role.replace(/_/g, " ");
}

export default function DashboardPage() {
  const [user, setUser] = useState<PortalUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) {
      setReady(true);
      return;
    }

    setUser(stored);

    portalApi
      .me()
      .then((fresh) => {
        const token = getStoredToken();
        if (token) saveSession(token, fresh);
        setUser(fresh);
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  if (!ready || !user) {
    return <div className="dashboard-page dashboard-page--loading">Loading dashboard...</div>;
  }

  const firstName = user.full_name.split(" ")[0];
  const workspaceKeys = new Set<string>(WORKSPACE_NAV_KEYS);
  const accessItems = navItemsForRole(user.role).filter((item) => workspaceKeys.has(item));

  return (
    <div className="dashboard-page">
      <section className="dashboard-hero">
        <div className="dashboard-hero-content">
          <p className="dashboard-hero-eyebrow">AI Recruiter Portal</p>
          <h1 className="dashboard-hero-title">Welcome back, {firstName}</h1>
          <p className="dashboard-hero-lead">
            Your central hub for AI-powered hiring. Use the sidebar to open Recruitment or Rubric Screening.
          </p>
        </div>
      </section>

      <div className="dashboard-overview-grid">
        <section className="dashboard-panel">
          <h2 className="dashboard-panel-title">Your Account</h2>
          <div className="dashboard-account-row">
            <div className="dashboard-user-card-avatar dashboard-user-card-avatar--large">
              {(user.full_name?.charAt(0) || user.email.charAt(0)).toUpperCase()}
            </div>
            <div className="dashboard-account-details">
              <div className="dashboard-detail-item">
                <span className="dashboard-detail-label">Full name</span>
                <span className="dashboard-detail-value">{user.full_name}</span>
              </div>
              <div className="dashboard-detail-item">
                <span className="dashboard-detail-label">Email</span>
                <span className="dashboard-detail-value">{user.email}</span>
              </div>
              <div className="dashboard-detail-item">
                <span className="dashboard-detail-label">Role</span>
                <span className="dashboard-detail-value dashboard-detail-value--role">
                  {formatRole(user.role)}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="dashboard-panel">
          <h2 className="dashboard-panel-title">Your Access</h2>
          {accessItems.length > 0 ? (
            <ul className="dashboard-access-list">
              {accessItems.map((item) => (
                <li key={item}>
                  <span className="dashboard-access-dot" />
                  <span>{WORKSPACE_LABELS[item] || NAV_CONFIG[item]?.label}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dashboard-panel-text">No hiring workspaces assigned to this account.</p>
          )}
          <p className="dashboard-panel-hint">
            Select a workspace from the <strong>Hiring</strong> menu in the left sidebar to get started.
          </p>
        </section>
      </div>
    </div>
  );
}
