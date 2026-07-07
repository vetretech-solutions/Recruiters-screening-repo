"use client";

import { useCallback, useEffect, useState } from "react";
import { portalApi, PortalUser } from "@/lib/portal-api";
import { getStoredUser } from "@/lib/session";

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function UsersPage() {
  const me = getStoredUser();
  const isSuperAdmin = me?.role === "super_admin";

  const [items, setItems] = useState<PortalUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [showPassword, setShowPassword] = useState<PortalUser | null>(null);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    role: "recruiter",
    password: "",
    confirm: "",
    status: "active",
  });
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = isSuperAdmin
        ? await portalApi.listTenantAdmins(page, pageSize, search)
        : await portalApi.listUsers(page, pageSize, search);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load users";
      setError(msg === "Not Found" ? "" : msg);
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [isSuperAdmin, page, pageSize, search]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (form.password !== form.confirm) {
      setError("Passwords do not match");
      return;
    }
    try {
      await portalApi.createUser({
        full_name: form.full_name,
        email: form.email,
        role: form.role,
        password: form.password,
        status: form.status,
      });
      setShowCreate(false);
      setForm({
        full_name: "",
        email: "",
        role: "recruiter",
        password: "",
        confirm: "",
        status: "active",
      });
      setMessage("User created successfully");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    }
  }

  async function toggleStatus(user: PortalUser) {
    const status = user.status === "active" ? "inactive" : "active";
    try {
      if (isSuperAdmin) {
        await portalApi.updateTenantAdmin(user.id, { status });
      } else {
        await portalApi.updateUser(user.id, { status });
      }
      setMessage(`User ${status === "active" ? "activated" : "deactivated"}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handlePasswordReset(e: React.FormEvent) {
    e.preventDefault();
    if (!showPassword) return;
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    try {
      if (isSuperAdmin) {
        await portalApi.setTenantAdminPassword(showPassword.id, newPassword);
      } else {
        await portalApi.setUserPassword(showPassword.id, newPassword);
      }
      setShowPassword(null);
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <h2 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "0.25rem" }}>
        {isSuperAdmin ? "Administrators" : "Team Users"}
      </h2>
      <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
        {isSuperAdmin
          ? "View and manage administrator accounts"
          : "Manage recruiters and resume screeners on your team"}
      </p>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="users-toolbar">
        <input
          className="input"
          placeholder="Search by name or email..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (setPage(1), setSearch(q))}
          style={{ flex: 1, minWidth: 220 }}
        />
        <button className="btn btn-secondary" onClick={() => { setPage(1); setSearch(q); }}>
          Search
        </button>
        {!isSuperAdmin && (
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            + Add User
          </button>
        )}
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)" }}>
                    No users found
                  </td>
                </tr>
              ) : (
                items.map((u) => (
                  <tr key={u.id}>
                    <td>{u.full_name}</td>
                    <td>{u.email}</td>
                    <td style={{ textTransform: "capitalize" }}>
                      {u.role.replace(/_/g, " ")}
                    </td>
                    <td>
                      <span className={`status-badge status-${u.status}`}>{u.status}</span>
                    </td>
                    <td>{u.created_at ? formatDate(u.created_at) : "—"}</td>
                    <td style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                        onClick={() => {
                          setShowPassword(u);
                          setNewPassword("");
                          setConfirmPassword("");
                        }}
                      >
                        Reset password
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                        onClick={() => toggleStatus(u)}
                      >
                        {u.status === "active" ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          <div className="pagination">
            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
              Page {page} of {totalPages} ({total} total)
            </span>
            <button
              className="btn btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
            <h3 style={{ marginBottom: "1rem" }}>Add Team User</h3>
            <div className="form-group">
              <label className="label">Full Name</label>
              <input
                className="input"
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="label">Email</label>
              <input
                className="input"
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="label">Role</label>
              <select
                className="input"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="recruiter">Recruiter</option>
                <option value="resume_screener">Resume Screener</option>
              </select>
            </div>
            <div className="form-group">
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="label">Confirm Password</label>
              <input
                className="input"
                type="password"
                required
                minLength={8}
                value={form.confirm}
                onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              />
            </div>
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
              <button type="submit" className="btn btn-primary">Create User</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {showPassword && (
        <div className="modal-overlay" onClick={() => setShowPassword(null)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handlePasswordReset}>
            <h3 style={{ marginBottom: "0.5rem" }}>Reset Password</h3>
            <p style={{ color: "var(--muted)", marginBottom: "1rem", fontSize: "0.9rem" }}>
              {showPassword.full_name} ({showPassword.email})
            </p>
            <div className="form-group">
              <label className="label">New Password</label>
              <input
                className="input"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="label">Confirm Password</label>
              <input
                className="input"
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
              <button type="submit" className="btn btn-primary">Update Password</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowPassword(null)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
