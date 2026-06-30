// SPDX-License-Identifier: AGPL-3.0-only

import { authFetch } from "@/features/auth/api";

export type JsonRecord = Record<string, unknown>;

export async function cognixJson<T = JsonRecord>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await authFetch(path, {
    ...init,
    headers,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return (await response.json()) as T;
}

export function jsonBody(value: JsonRecord): BodyInit {
  return JSON.stringify(value);
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.clone().json()) as unknown;
    if (isRecord(payload)) {
      const detail = payload.detail;
      if (typeof detail === "string" && detail.trim()) return detail;
      if (isRecord(detail)) {
        const message = detail.message;
        if (typeof message === "string" && message.trim()) return message;
      }
      const message = payload.message;
      if (typeof message === "string" && message.trim()) return message;
    }
  } catch {
    // Fall back to the HTTP status below.
  }
  return `CogniX API request failed (${response.status})`;
}

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function asRecord(value: unknown): JsonRecord {
  return isRecord(value) ? value : {};
}

export function readString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

export function readNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function readBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => readString(item).trim()).filter(Boolean)
    : [];
}
