// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

export const AUTH_TOKEN_KEY = "unsloth_auth_token";
export const AUTH_REFRESH_TOKEN_KEY = "unsloth_auth_refresh_token";

function canUseStorage(): boolean {
  return typeof window !== "undefined";
}

export function removeLegacyPersistentAuthTokens(): void {
  if (!canUseStorage()) return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
}

export function getStoredAuthToken(): string | null {
  if (!canUseStorage()) return null;
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  const legacy = localStorage.getItem(AUTH_TOKEN_KEY);
  if (legacy) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    if (!token) sessionStorage.setItem(AUTH_TOKEN_KEY, legacy);
  }
  return token || legacy;
}

export function hasStoredAuthToken(): boolean {
  return Boolean(getStoredAuthToken());
}

export function getStoredRefreshToken(): string | null {
  if (!canUseStorage()) return null;
  return sessionStorage.getItem(AUTH_REFRESH_TOKEN_KEY);
}

export function hasStoredRefreshToken(): boolean {
  return Boolean(getStoredRefreshToken());
}

export function storeAuthTokenPair(
  accessToken: string,
  refreshToken: string | null,
): void {
  if (!canUseStorage()) return;
  sessionStorage.setItem(AUTH_TOKEN_KEY, accessToken);
  removeLegacyPersistentAuthTokens();
  if (refreshToken) {
    sessionStorage.setItem(AUTH_REFRESH_TOKEN_KEY, refreshToken);
  } else {
    sessionStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
  }
}

export function clearStoredAuthTokens(): void {
  if (!canUseStorage()) return;
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
  sessionStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
  removeLegacyPersistentAuthTokens();
}
