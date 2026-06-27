// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { useSyncExternalStore } from "react";

export type AccentColorId =
  | "black"
  | "graphite"
  | "blue"
  | "cyan"
  | "teal"
  | "emerald"
  | "violet"
  | "rose"
  | "red"
  | "orange"
  | "amber";

export interface AccentColorOption {
  id: AccentColorId;
  label: string;
  color: string;
  foreground: string;
}

export const ACCENT_COLORS: AccentColorOption[] = [
  { id: "black", label: "Black", color: "#000000", foreground: "#ffffff" },
  { id: "graphite", label: "Graphite", color: "#3f3f46", foreground: "#ffffff" },
  { id: "blue", label: "Blue", color: "#2563eb", foreground: "#ffffff" },
  { id: "cyan", label: "Cyan", color: "#0891b2", foreground: "#ffffff" },
  { id: "teal", label: "Teal", color: "#0d9488", foreground: "#ffffff" },
  { id: "emerald", label: "Emerald", color: "#17b88b", foreground: "#ffffff" },
  { id: "violet", label: "Violet", color: "#7c3aed", foreground: "#ffffff" },
  { id: "rose", label: "Rose", color: "#e11d48", foreground: "#ffffff" },
  { id: "red", label: "Red", color: "#dc2626", foreground: "#ffffff" },
  { id: "orange", label: "Orange", color: "#ea580c", foreground: "#ffffff" },
  { id: "amber", label: "Amber", color: "#f59e0b", foreground: "#111111" },
];

const STORAGE_KEY = "cognix_accent_color";
const DEFAULT_ACCENT: AccentColorId = "black";

function getOption(id: string | null): AccentColorOption {
  return (
    ACCENT_COLORS.find((option) => option.id === id) ??
    ACCENT_COLORS.find((option) => option.id === DEFAULT_ACCENT) ??
    ACCENT_COLORS[0]
  );
}

function readStoredAccent(): AccentColorId {
  if (typeof window === "undefined") return DEFAULT_ACCENT;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return getOption(stored).id;
  } catch {
    return DEFAULT_ACCENT;
  }
}

function applyAccentToDocument(id: AccentColorId): void {
  if (typeof document === "undefined") return;
  const option = getOption(id);
  const root = document.documentElement;
  root.style.setProperty("--primary", option.color);
  root.style.setProperty("--ring", option.color);
  root.style.setProperty("--chart-1", option.color);
  root.style.setProperty("--sidebar-primary", option.color);
  root.style.setProperty("--sidebar-ring", option.color);
  root.style.setProperty("--primary-foreground", option.foreground);
  root.style.setProperty("--sidebar-primary-foreground", option.foreground);
}

const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function initializeAccentColor(): void {
  applyAccentToDocument(readStoredAccent());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  if (typeof window === "undefined") {
    return () => listeners.delete(cb);
  }
  initializeAccentColor();
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === null) {
      initializeAccentColor();
      cb();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot(): AccentColorId {
  return readStoredAccent();
}

function getServerSnapshot(): AccentColorId {
  return DEFAULT_ACCENT;
}

export function setAccentColor(id: AccentColorId): void {
  if (typeof window === "undefined") return;
  const option = getOption(id);
  try {
    window.localStorage.setItem(STORAGE_KEY, option.id);
  } catch {
    // ignore storage failures
  }
  applyAccentToDocument(option.id);
  notify();
}

export function useAccentColor(): {
  accentColor: AccentColorId;
  setAccentColor: (id: AccentColorId) => void;
} {
  const accentColor = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );
  return { accentColor, setAccentColor };
}
