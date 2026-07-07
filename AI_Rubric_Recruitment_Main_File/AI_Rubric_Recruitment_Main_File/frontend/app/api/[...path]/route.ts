import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.BACKEND_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params;
  const target = `${BACKEND}/api/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  let body: BodyInit | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    const ct = contentType || "";
    if (ct.includes("multipart/form-data")) {
      body = await req.arrayBuffer();
    } else {
      body = await req.text();
    }
  }

  try {
    const res = await fetch(target, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });

    if (REDIRECT_STATUSES.has(res.status)) {
      const location = res.headers.get("location");
      if (location) return NextResponse.redirect(location, res.status);
    }

    const outHeaders = new Headers();
    const resType = res.headers.get("content-type");
    if (resType) outHeaders.set("content-type", resType);
    const disposition = res.headers.get("content-disposition");
    if (disposition) outHeaders.set("content-disposition", disposition);

    return new NextResponse(res.body, { status: res.status, headers: outHeaders });
  } catch {
    return NextResponse.json(
      { detail: "Backend not running. Start: cd backend && python main.py" },
      { status: 503 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
