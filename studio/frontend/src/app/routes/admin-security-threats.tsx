// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { SecurityThreatsPage } from "@/features/admin/security-threats-page";
import { createRoute } from "@tanstack/react-router";
import { requireAuth } from "../auth-guards";
import { Route as rootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/security-threats",
  staticData: { title: "Security Threats" },
  beforeLoad: () => requireAuth(),
  component: SecurityThreatsPage,
});
