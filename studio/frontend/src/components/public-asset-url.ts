// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

const LEADING_SLASH = /^\//;

export function publicAssetUrl(path: string): string {
  return encodeURI(import.meta.env.BASE_URL + path.replace(LEADING_SLASH, ""));
}
