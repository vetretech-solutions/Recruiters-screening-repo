export interface PortalUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  status: string;
  tenant_id: string | null;
  tenant_name?: string | null;
  created_at?: string;
  permissions?: string[];
}

import { getStoredToken } from "./session";
import { getPortalApiBase } from "./backend-url";

function normalizePortalUser(raw: Partial<PortalUser> & { id: number; email: string; full_name: string }): PortalUser {
  return {
    id: raw.id,
    email: raw.email,
    full_name: raw.full_name,
    role: raw.role || "admin",
    status: raw.status || "active",
    tenant_id: raw.tenant_id ?? null,
    tenant_name: raw.tenant_name ?? null,
    created_at: raw.created_at,
    permissions: raw.permissions,
  };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${getPortalApiBase()}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join(", ")
      : detail || "Request failed";
    throw new Error(message);
  }
  return res.json();
}

export interface PaginatedUsers {
  items: PortalUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface ContactSubmission {
  id: number;
  full_name: string;
  email: string;
  company: string | null;
  message: string;
  created_at: string;
}

export interface PaginatedContactSubmissions {
  items: ContactSubmission[];
  total: number;
  page: number;
  page_size: number;
}

export const portalApi = {
  login: async (email: string, password: string) => {
    const res = await request<{ access_token: string; user: Partial<PortalUser> & { id: number; email: string; full_name: string } }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    return { access_token: res.access_token, user: normalizePortalUser(res.user) };
  },

  register: async (data: {
    full_name: string;
    email: string;
    password: string;
  }) => {
    const res = await request<{ access_token: string; user: Partial<PortalUser> & { id: number; email: string; full_name: string } }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return { access_token: res.access_token, user: normalizePortalUser(res.user) };
  },

  me: async () => normalizePortalUser(await request<Partial<PortalUser> & { id: number; email: string; full_name: string }>("/auth/me")),

  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>("/auth/change-password", {
      method: "PATCH",
      body: JSON.stringify({ current_password, new_password }),
    }),

  listUsers: (page = 1, page_size = 10, q = "") =>
    request<PaginatedUsers>(
      `/users?page=${page}&page_size=${page_size}&q=${encodeURIComponent(q)}`
    ),

  createUser: (data: {
    full_name: string;
    email: string;
    role: string;
    password: string;
    status?: string;
  }) =>
    request<PortalUser>("/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateUser: (id: number, data: { full_name?: string; status?: string }) =>
    request<PortalUser>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  setUserPassword: (id: number, new_password: string) =>
    request<{ message: string }>(`/users/${id}/password`, {
      method: "PATCH",
      body: JSON.stringify({ new_password }),
    }),

  listTenantAdmins: (page = 1, page_size = 10, q = "") =>
    request<PaginatedUsers>(
      `/super-admin/tenant-admins?page=${page}&page_size=${page_size}&q=${encodeURIComponent(q)}`
    ),

  updateTenantAdmin: (id: number, data: { full_name?: string; status?: string }) =>
    request<PortalUser>(`/super-admin/tenant-admins/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  setTenantAdminPassword: (id: number, new_password: string) =>
    request<{ message: string }>(`/super-admin/tenant-admins/${id}/password`, {
      method: "PATCH",
      body: JSON.stringify({ new_password }),
    }),

  listContactSubmissions: (page = 1, page_size = 10, q = "") =>
    request<PaginatedContactSubmissions>(
      `/super-admin/contacts?page=${page}&page_size=${page_size}&q=${encodeURIComponent(q)}`
    ),
};

export async function submitContactForm(data: {
  full_name: string;
  email: string;
  company?: string;
  message: string;
}) {
  const res = await fetch(`${getPortalApiBase()}/contact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join(", ")
      : detail || "Request failed";
    throw new Error(message);
  }
  return res.json();
}

export { canAccessTab, defaultRouteForRole, navItemsForRole } from "@/lib/portal-nav";
