// SPDX-License-Identifier: AGPL-3.0-only

import { createRoute } from "@tanstack/react-router";
import { lazy } from "react";
import { requireAuth } from "../auth-guards";
import { Route as rootRoute } from "./__root";

const ScheduledPage = lazy(() =>
  import("@/features/cognix-modules/module-pages").then((m) => ({
    default: m.ScheduledPage,
  })),
);

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/scheduled",
  staticData: { title: "Scheduled" },
  beforeLoad: () => requireAuth(),
  component: ScheduledPage,
});
