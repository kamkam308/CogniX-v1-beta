// SPDX-License-Identifier: AGPL-3.0-only

import { createRoute } from "@tanstack/react-router";
import { lazy } from "react";
import { requireAuth } from "../auth-guards";
import { Route as rootRoute } from "./__root";

const AppsPage = lazy(() =>
  import("@/features/cognix-modules/module-pages").then((m) => ({
    default: m.AppsPage,
  })),
);

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apps",
  staticData: { title: "Apps" },
  beforeLoad: () => requireAuth(),
  component: AppsPage,
});
