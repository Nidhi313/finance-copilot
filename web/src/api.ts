import { createApiClient, type Schemas } from "@finance-copilot/api-client";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const api = createApiClient(API_URL);
export type { Schemas };

/** Turn FastAPI's error body into one readable sentence. */
export function errorMessage(err: unknown): string {
  if (!err) return "Something went wrong";
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  const detail = (err as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) =>
        [d.loc?.filter((l) => l !== "body").join("."), d.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: string }).message);
  return "Something went wrong";
}

/** Unwrap an openapi-fetch result, throwing a readable error. */
export async function call<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) throw new Error(errorMessage(error ?? response.statusText));
  return data as T;
}

/** Multipart uploads (CSV import) go through fetch directly. */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorMessage(body));
  return body as T;
}
