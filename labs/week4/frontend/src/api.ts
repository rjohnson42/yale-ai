export const API_BASE = "http://127.0.0.1:8000";
const TOKEN_KEY = "som.session";

export type Course = {
  "Course Number": string;
  "Course Title": string;
  "Faculty 1": string;
  "Course Category": string;
  "Course Type": string;
  "Daytimes": string;
  "Room": string;
  Section: string;
  "Course Session": string;
  Units: string;
  "Course Description": string;
};

export type ChatReply = {
  reply: string;
  tools_used: string[];
};

export type User = {
  id: number;
  email: string;
  name: string;
};

export type SavedMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  tools: string[];
  created_at: string;
};

export class AuthError extends Error {}

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
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 401 && path !== "/api/login") {
    clearToken();
    throw new AuthError(await readError(response, "Sign in to continue."));
  }
  return response;
}

export async function register(email: string, password: string, name: string): Promise<User> {
  const response = await request("/api/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Could not create that account."));
  }
  const body = (await response.json()) as { token: string; user: User };
  setToken(body.token);
  return body.user;
}

export async function login(email: string, password: string): Promise<User> {
  const response = await request("/api/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Email or password is not right."));
  }
  const body = (await response.json()) as { token: string; user: User };
  setToken(body.token);
  return body.user;
}

export async function fetchMe(): Promise<User> {
  const response = await request("/api/me");
  if (!response.ok) {
    throw new AuthError(await readError(response, "Sign in to continue."));
  }
  return (await response.json()) as User;
}

export async function logout(): Promise<void> {
  try {
    await request("/api/logout", { method: "POST" });
  } finally {
    clearToken();
  }
}

export async function fetchCourses(): Promise<Course[]> {
  const response = await request("/api/courses");
  if (!response.ok) {
    throw new Error(await readError(response, `The catalog did not load (${response.status}).`));
  }
  const body = (await response.json()) as { courses?: Course[] };
  return body.courses ?? [];
}

export async function fetchMessages(): Promise<SavedMessage[]> {
  const response = await request("/api/messages");
  if (!response.ok) {
    throw new Error(await readError(response, "Saved messages did not load."));
  }
  const body = (await response.json()) as SavedMessage[];
  return body.map((message) => ({
    ...message,
    role: message.role === "assistant" ? "assistant" : "user",
    tools: message.tools ?? [],
  }));
}

export async function sendChat(message: string): Promise<ChatReply> {
  const response = await request("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, `The assistant did not answer (${response.status}).`));
  }
  const body = (await response.json()) as Partial<ChatReply>;
  return {
    reply: body.reply ?? "",
    tools_used: body.tools_used ?? [],
  };
}
