// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

export type ConnectivityMode = "online" | "offline";

export type ConnectivityOptions = {
  probeUrl?: string;
  timeoutMs?: number;
};

function hasNavigatorOnlineSignal(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  return navigator.onLine;
}

export async function isOnline(options: ConnectivityOptions = {}): Promise<boolean> {
  if (!hasNavigatorOnlineSignal()) {
    return false;
  }
  if (!options.probeUrl) {
    return true;
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    Math.max(options.timeoutMs ?? 2500, 250),
  );
  try {
    await fetch(options.probeUrl, {
      method: "HEAD",
      cache: "no-store",
      mode: "no-cors",
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getConnectivityMode(
  options: ConnectivityOptions = {},
): Promise<ConnectivityMode> {
  return (await isOnline(options)) ? "online" : "offline";
}
