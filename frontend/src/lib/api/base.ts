const DEFAULT_BASE_URL = "http://localhost:8500";

export function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    return localStorage.getItem("tadpole-studio-backend-url") || DEFAULT_BASE_URL;
  }
  return DEFAULT_BASE_URL;
}

export function getWsUrl(): string {
  return getBaseUrl().replace(/^http/, "ws");
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}/api${path}`;
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}
