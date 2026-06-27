// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { useEffect, useState } from "react";

const DEVELOPER_MODE_KEY = "cognix_developer_mode";
const DEVELOPER_MODE_EVENT = "cognix-developer-mode-change";
const DEVELOPER_OPTIONS_KEY = "cognix_developer_options";
const DEVELOPER_OPTIONS_EVENT = "cognix-developer-options-change";

export interface DeveloperOptions {
  rightSidebar: boolean;
  trainingTools: boolean;
}

const DEFAULT_DEVELOPER_OPTIONS: DeveloperOptions = {
  rightSidebar: false,
  trainingTools: false,
};

function readDeveloperMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(DEVELOPER_MODE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setDeveloperMode(enabled: boolean): void {
  try {
    if (enabled) {
      window.localStorage.setItem(DEVELOPER_MODE_KEY, "1");
    } else {
      window.localStorage.removeItem(DEVELOPER_MODE_KEY);
    }
  } catch {
    // ignore storage failures
  }
  window.dispatchEvent(new CustomEvent(DEVELOPER_MODE_EVENT));
}

export function useDeveloperMode(): [boolean, (enabled: boolean) => void] {
  const [enabled, setEnabled] = useState(readDeveloperMode);

  useEffect(() => {
    const sync = () => setEnabled(readDeveloperMode());
    window.addEventListener("storage", sync);
    window.addEventListener(DEVELOPER_MODE_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(DEVELOPER_MODE_EVENT, sync);
    };
  }, []);

  return [
    enabled,
    (nextEnabled: boolean) => {
      setDeveloperMode(nextEnabled);
      setEnabled(nextEnabled);
    },
  ];
}

function readDeveloperOptions(): DeveloperOptions {
  if (typeof window === "undefined") return DEFAULT_DEVELOPER_OPTIONS;
  try {
    const raw = window.localStorage.getItem(DEVELOPER_OPTIONS_KEY);
    if (!raw) return DEFAULT_DEVELOPER_OPTIONS;
    const parsed = JSON.parse(raw) as Partial<DeveloperOptions>;
    return {
      rightSidebar: parsed.rightSidebar === true,
      trainingTools: parsed.trainingTools === true,
    };
  } catch {
    return DEFAULT_DEVELOPER_OPTIONS;
  }
}

export function setDeveloperOptions(options: DeveloperOptions): void {
  try {
    window.localStorage.setItem(DEVELOPER_OPTIONS_KEY, JSON.stringify(options));
  } catch {
    // ignore storage failures
  }
  window.dispatchEvent(new CustomEvent(DEVELOPER_OPTIONS_EVENT));
}

export function useDeveloperOptions(): [
  DeveloperOptions,
  (options: DeveloperOptions) => void,
] {
  const [options, setOptionsState] = useState(readDeveloperOptions);

  useEffect(() => {
    const sync = () => setOptionsState(readDeveloperOptions());
    window.addEventListener("storage", sync);
    window.addEventListener(DEVELOPER_OPTIONS_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(DEVELOPER_OPTIONS_EVENT, sync);
    };
  }, []);

  return [
    options,
    (nextOptions: DeveloperOptions) => {
      setDeveloperOptions(nextOptions);
      setOptionsState(nextOptions);
    },
  ];
}
