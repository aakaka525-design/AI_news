import { NextRequest } from "next/server";

type RouteContext = {
  params: {
    path?: string[];
  };
};

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function getTargetBaseUrl(): URL | null {
  const raw = process.env.DASHBOARD_INTERNAL_URL || "http://dashboard:8000";
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function buildTargetUrl(base: URL, pathParts: string[], search: string): URL {
  const normalizedPath = pathParts.map((part) => encodeURIComponent(part)).join("/");
  const target = new URL(base.toString());
  target.pathname = `/${normalizedPath}`;
  target.search = search;
  return target;
}

function buildForwardHeaders(req: NextRequest): Headers {
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (!HOP_BY_HOP_HEADERS.has(lower)) {
      headers.set(key, value);
    }
  });
  const dashboardApiKey = process.env.DASHBOARD_API_KEY?.trim();
  if (dashboardApiKey) {
    headers.set("X-API-Key", dashboardApiKey);
  }
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const baseUrl = getTargetBaseUrl();
  if (!baseUrl) {
    return new Response("Server misconfigured: DASHBOARD_INTERNAL_URL", { status: 500 });
  }

  const pathParts = context.params.path ?? [];
  if (!Array.isArray(pathParts) || pathParts.length === 0) {
    return new Response("Missing target path", { status: 400 });
  }

  // Security: only allow proxying to known API path prefixes
  const ALLOWED_PREFIXES = ["api/", "webhook/", "health"];
  const joinedPath = pathParts.join("/");
  const isAllowed = ALLOWED_PREFIXES.some((prefix) =>
    joinedPath === prefix.replace(/\/$/, "") || joinedPath.startsWith(prefix)
  );
  if (!isAllowed) {
    return new Response("Forbidden: path not in allowlist", { status: 403 });
  }

  const targetUrl = buildTargetUrl(baseUrl, pathParts, request.nextUrl.search);
  const headers = buildForwardHeaders(request);

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, init);
  } catch (error) {
    const message = error instanceof Error ? error.message : "proxy request failed";
    return new Response(message, { status: 502 });
  }

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) {
    responseHeaders.set("content-type", contentType);
  }
  const cacheControl = upstream.headers.get("cache-control");
  if (cacheControl) {
    responseHeaders.set("cache-control", cacheControl);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const dynamic = "force-dynamic";

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
