import { JobDescription } from "./recruitment-api";
import { getRecruitmentApiBase } from "./backend-url";

export interface ApplyPageData {
  platform: string;
  job: Partial<JobDescription>;
  title: string;
}

export interface ApplyFormData {
  full_name: string;
  email: string;
  phone: string;
  current_title?: string;
  current_company?: string;
  years_experience?: string;
  location?: string;
  cover_letter?: string;
  resume_text?: string;
  resume_file?: File | null;
}

async function parseError(res: Response): Promise<string> {
  const err = await res.json().catch(() => ({ detail: res.statusText }));
  const detail = err.detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg).join(", ");
  }
  return detail || "Request failed";
}

export const applyApi = {
  getJob: async (token: string): Promise<ApplyPageData> => {
    const res = await fetch(`${getRecruitmentApiBase()}/apply/${encodeURIComponent(token)}`);
    if (!res.ok) throw new Error(await parseError(res));
    return res.json();
  },

  submit: async (
    token: string,
    body: ApplyFormData
  ): Promise<{ message: string; id: number }> => {
    const form = new FormData();
    form.append("full_name", body.full_name);
    form.append("email", body.email);
    form.append("phone", body.phone);
    form.append("current_title", body.current_title || "");
    form.append("current_company", body.current_company || "");
    form.append("years_experience", body.years_experience || "");
    form.append("location", body.location || "");
    form.append("cover_letter", body.cover_letter || "");
    form.append("resume_text", body.resume_text || "");
    if (body.resume_file) {
      form.append("resume_file", body.resume_file);
    }

    const res = await fetch(`${getRecruitmentApiBase()}/apply/${encodeURIComponent(token)}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await parseError(res));
    return res.json();
  },
};
