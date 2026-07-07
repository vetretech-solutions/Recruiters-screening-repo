export const NAV_CONFIG: Record<string, { href: string; label: string }> = {
  dashboard: { href: "/dashboard", label: "Dashboard" },
  users: { href: "/users", label: "Users" },
  contacts: { href: "/contacts", label: "Contact Inquiries" },
  recruitment: { href: "/recruitment", label: "Recruitment" },
  screening: { href: "/screening", label: "Rubric Screening" },
};

/** Sidebar dropdown items grouped under "Hiring" */
export const WORKSPACE_NAV_KEYS = ["recruitment", "screening"] as const;

/** Shown in app but hidden from the left sidebar and dashboard */
export const SIDEBAR_EXCLUDED_KEYS = ["users", "contacts"] as const;

const ROLE_NAV: Record<string, string[]> = {
  super_admin: ["dashboard", "users", "contacts"],
  admin: ["dashboard", "users", "recruitment", "screening"],
  recruiter: ["dashboard", "recruitment"],
  resume_screener: ["dashboard", "screening"],
};

export function navItemsForRole(role: string): string[] {
  return ROLE_NAV[role] || ["dashboard"];
}

export function defaultRouteForRole(_role: string): string {
  return "/dashboard";
}

export function canAccessTab(role: string, tab: string): boolean {
  if (tab === "dashboard") return true;
  return navItemsForRole(role).includes(tab);
}
