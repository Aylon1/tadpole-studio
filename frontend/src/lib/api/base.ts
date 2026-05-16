const DEFAULT_BASE_URL = "http://localhost:8500";

export function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    // First check localStorage for backward compatibility
    const storedUrl = localStorage.getItem("tadpole-studio-backend-url");
    if (storedUrl) {
      return storedUrl;
    }
    
    // If on a non-localhost hostname (like tjkserver), use current host with backend port
    const hostname = window.location.hostname;
    if (hostname !== "localhost" && hostname !== "127.0.0.1") {
      return `http://${hostname}:8500`;
    }
  }
  return DEFAULT_BASE_URL;
}

export function getWsUrl(): string {
  if (typeof window !== "undefined") {
    // First check localStorage for backward compatibility
    const storedUrl = localStorage.getItem("tadpole-studio-backend-url");
    if (storedUrl) {
      return storedUrl.replace(/^http/, "ws");
    }
    
    // If on a non-localhost hostname (like tjkserver), use current host with backend port
    const hostname = window.location.hostname;
    if (hostname !== "localhost" && hostname !== "127.0.0.1") {
      return `ws://${hostname}:8500`;
    }
  }
  return DEFAULT_BASE_URL.replace(/^http/, "ws");
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
