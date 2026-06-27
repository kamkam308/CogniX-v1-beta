// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { useCallback, useSyncExternalStore } from "react";

export type DeveloperOptions = {
  trainingTools: boolean;
};

const DEVELOPER_OPTIONS_KEY = "unsloth_developer_options";
const DEFAULT_DEVELOPER_OPTIONS: DeveloperOptions = {
  trainingTools: false,
};

function readDeveloperOptions(): DeveloperOptions {
  if (typeof window === "undefined") return DEFAULT_DEVELOPER_OPTIONS;
  try {
    const raw = window.localStorage.getItem(DEVELOPER_OPTIONS_KEY);
    if (!raw) return DEFAULT_DEVELOPER_OPTIONS;
    const parsed = JSON.parse(raw) as Partial<DeveloperOptions>;
    return {
      trainingTools: parsed.trainingTools === true,
    };
  } catch {
    return DEFAULT_DEVELOPER_OPTIONS;
  }
}

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener("unsloth:developer-options-changed", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("unsloth:developer-options-changed", callback);
  };
}

export function useDeveloperOptions(): [
  DeveloperOptions,
  (options: DeveloperOptions) => void,
] {
  const options = useSyncExternalStore(
    subscribe,
    readDeveloperOptions,
    () => DEFAULT_DEVELOPER_OPTIONS,
  );
  const setOptions = useCallback((next: DeveloperOptions) => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(DEVELOPER_OPTIONS_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event("unsloth:developer-options-changed"));
  }, []);
  return [options, setOptions];
}
