// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { createRoute } from "@tanstack/react-router";
import { AuthRoutePage } from "@/features/auth/login-page";
import { requireGuest } from "../auth-guards";
import { Route as rootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  staticData: { title: "Signup" },
  beforeLoad: () => requireGuest(),
  component: AuthRoutePage,
});
