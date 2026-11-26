import { API_BASE_URL } from "../config";
import type { SignalInput, TrafficSignal } from "../types";

interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // The ReLy API returns { error: { code, message, details } } — surface it to the user.
    let message = `API request failed (${response.status})`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.error?.message) {
        const details = Array.isArray(body.error.details) ? `: ${body.error.details.join("; ")}` : "";
        message = `${body.error.message}${details}`;
      }
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// GET /signals returns { items, count, generated_at }.
export const listSignals = async () =>
  (await request<{ items: TrafficSignal[] }>("/signals")).items;
export const getSignal = (id: string) =>
  request<TrafficSignal>(`/signals/${encodeURIComponent(id)}`);
export const createSignal = (body: SignalInput) =>
  request<TrafficSignal>("/signals", { method: "POST", body: JSON.stringify(body) });
export const updateSignal = (id: string, body: SignalInput) =>
  request<TrafficSignal>(`/signals/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
export const deleteSignal = (id: string) =>
  request<{ deleted: string }>(`/signals/${encodeURIComponent(id)}`, { method: "DELETE" });
