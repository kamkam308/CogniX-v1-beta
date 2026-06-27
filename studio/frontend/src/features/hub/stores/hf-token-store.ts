// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { create } from "zustand";
import { bumpInventoryVersion } from "./inventory-events";

const HF_TOKEN_KEY = "unsloth_hf_token";
const HF_TOKEN_CHANGED_EVENT = "unsloth:hf-token-changed";
const LEGACY_TRAINING_KEY = "unsloth_training_config_v1";
let storageSyncStarted = false;
let storageSyncListener: ((event: StorageEvent) => void) | null = null;
let tokenChangedListener: ((event: Event) => void) | null = null;

function canUseStorage(): boolean {
  return typeof window !== "undefined";
}

function loadInitial(): string {
  if (!canUseStorage()) return "";
  try {
    const direct = window.sessionStorage.getItem(HF_TOKEN_KEY);
    if (direct !== null) {
      const normalized = normalize(direct);
      if (normalized !== direct) persist(normalized);
      return normalized;
    }
    const legacyDirect = window.localStorage.getItem(HF_TOKEN_KEY);
    if (legacyDirect !== null) {
      const normalized = normalize(legacyDirect);
      persist(normalized);
      window.localStorage.removeItem(HF_TOKEN_KEY);
      return normalized;
    }
    const legacy = window.localStorage.getItem(LEGACY_TRAINING_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy) as {
        state?: Record<string, unknown>;
        [key: string]: unknown;
      };
      const state = parsed?.state;
      const fromTraining = state?.hfToken;
      if (typeof fromTraining === "string" && fromTraining.length > 0) {
        const normalized = normalize(fromTraining);
        if (state) delete state.hfToken;
        window.localStorage.setItem(LEGACY_TRAINING_KEY, JSON.stringify(parsed));
        persist(normalized);
        return normalized;
      }
    }
  } catch {
    return "";
  }
  return "";
}

function persist(value: string): void {
  if (!canUseStorage()) return;
  try {
    window.localStorage.removeItem(HF_TOKEN_KEY);
    if (value) window.sessionStorage.setItem(HF_TOKEN_KEY, value);
    else window.sessionStorage.removeItem(HF_TOKEN_KEY);
  } catch {
    void 0;
  }
}

function normalize(raw: string): string {
  return raw.replace(/^[\s"']+|[\s"']+$/g, "");
}

function stopStorageSync(): void {
  if (!canUseStorage()) return;
  if (storageSyncListener !== null) {
    window.removeEventListener("storage", storageSyncListener);
    storageSyncListener = null;
  }
  if (tokenChangedListener !== null) {
    window.removeEventListener(HF_TOKEN_CHANGED_EVENT, tokenChangedListener);
    tokenChangedListener = null;
  }
  storageSyncStarted = false;
}

if (import.meta.hot) {
  import.meta.hot.dispose(stopStorageSync);
}

interface HfTokenStore {
  token: string;
  setToken: (value: string) => void;
  clearToken: () => void;
}

export const useHfTokenStore = create<HfTokenStore>((set) => {
  const applyToken = (value: string, shouldPersist: boolean) => {
    const next = normalize(value);
    if (shouldPersist || next !== value) persist(next);
    let changed = false;
    set((state) => {
      if (state.token === next) return state;
      changed = true;
      return { token: next };
    });
    if (changed) bumpInventoryVersion();
  };

  if (!storageSyncStarted && canUseStorage()) {
    storageSyncStarted = true;
    storageSyncListener = (event) => {
      if (event.key !== HF_TOKEN_KEY) return;
      applyToken(window.sessionStorage.getItem(HF_TOKEN_KEY) ?? "", false);
    };
    window.addEventListener("storage", storageSyncListener);
    tokenChangedListener = (event) => {
      applyToken((event as CustomEvent<string>).detail ?? "", false);
    };
    window.addEventListener(HF_TOKEN_CHANGED_EVENT, tokenChangedListener);
  }

  return {
    token: loadInitial(),
    setToken: (value) => applyToken(value, true),
    clearToken: () => applyToken("", true),
  };
});

export function getHfToken(): string {
  return useHfTokenStore.getState().token;
}

// HF's JS client throws on a non-empty token that isn't `hf_...` instead of
// browsing anonymously, so treat anything malformed as no token.
export function hfApiToken(
  token: string | undefined | null,
): string | undefined {
  return token && token.startsWith("hf_") ? token : undefined;
}
