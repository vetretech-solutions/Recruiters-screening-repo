import type { PortalUser } from "./portal-api";

const TOKEN_KEY = "token";
const USER_KEY = "user";

function isValidUser(value: unknown): value is PortalUser {
  if (!value || typeof value !== "object") return false;
  const user = value as PortalUser;
  return (
    typeof user.id === "number" &&
    typeof user.email === "string" &&
    user.email.length > 0 &&
    typeof user.full_name === "string" &&
    user.full_name.length > 0 &&
    typeof user.role === "string" &&
    user.role.length > 0
  );
}

export function saveSession(token: string, user: PortalUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function hasValidSession(): boolean {
  return getStoredUser() !== null;
}

export function getStoredUser(): PortalUser | null {
  if (typeof window === "undefined") return null;

  const token = localStorage.getItem(TOKEN_KEY);
  const raw = localStorage.getItem(USER_KEY);

  if (!token || !raw) {
    if (token || raw) clearSession();
    return null;
  }

  try {
    const user = JSON.parse(raw) as unknown;
    if (!isValidUser(user)) {
      clearSession();
      return null;
    }
    return user;
  } catch {
    clearSession();
    return null;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  if (!getStoredUser()) return null;
  return localStorage.getItem(TOKEN_KEY);
}
