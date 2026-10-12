export const API_BASE = "http://127.0.0.1:8000";

const TOKEN_KEY = "campuscustoms.session";

export type User = {
  id: number;
  email: string;
  name: string;
  first_name: string;
  last_name: string;
};

export type RegisterInput = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  confirm_password: string;
};

type AuthPayload = {
  token: string;
  user: User;
};

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: string };
      if (first.msg) return first.msg;
    }
  } catch {
    /* response was not JSON */
  }
  return fallback;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error("Can't reach the shop right now. Try again in a minute.");
  }
}

export async function login(email: string, password: string): Promise<User> {
  const response = await request("/api/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "That email and password don't match."));
  }
  const payload = (await response.json()) as AuthPayload;
  setToken(payload.token);
  return payload.user;
}

export async function register(input: RegisterInput): Promise<User> {
  const response = await request("/api/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Couldn't create your account. Try again."));
  }
  const payload = (await response.json()) as AuthPayload;
  setToken(payload.token);
  return payload.user;
}

export async function fetchMe(): Promise<User | null> {
  if (!getToken()) return null;
  const response = await request("/api/me");
  if (response.status === 401) {
    clearToken();
    return null;
  }
  if (!response.ok) {
    throw new Error(await readError(response, "Couldn't load your account."));
  }
  return (await response.json()) as User;
}

export type ProductCard = {
  product_id: string;
  name: string;
  price: number;
  garment_type: string;
  image_file_path: string;
  description: string;
  colors: string[];
  in_stock_sizes: string[];
};

export type SavedChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  products: ProductCard[];
  created_at: string;
};

export async function fetchMessages(): Promise<SavedChatMessage[]> {
  const response = await request("/api/messages");
  if (response.status === 401) {
    clearToken();
    throw new Error("Your session ended. Log in again.");
  }
  if (!response.ok) {
    throw new Error(await readError(response, "Couldn't load your past chats."));
  }
  return (await response.json()) as SavedChatMessage[];
}

export async function sendChat(
  message: string,
  context: {
    pagePath: string;
    productId: string;
    history: { role: string; content: string }[];
  },
): Promise<SavedChatMessage> {
  const response = await request("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      page_path: context.pagePath,
      product_id: context.productId,
      history: context.history,
    }),
  });
  if (response.status === 401) {
    clearToken();
    throw new Error("Your session ended. Log in again.");
  }
  if (!response.ok) {
    throw new Error(await readError(response, "The chat hit a snag. Try again."));
  }
  const body = (await response.json()) as { message: SavedChatMessage };
  return body.message;
}

export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    await fetch(`${API_BASE}/api/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
  clearToken();
}
