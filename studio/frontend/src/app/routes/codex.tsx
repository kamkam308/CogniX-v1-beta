// SPDX-License-Identifier: AGPL-3.0-only

import { createRoute } from "@tanstack/react-router";
import { lazy } from "react";
import { requireAuth } from "../auth-guards";
import { Route as rootRoute } from "./__root";

const CodexPage = lazy(() =>
  import("@/features/cognix-modules/module-pages").then((m) => ({
    default: m.CodexPage,
  })),
);

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/codex",
  staticData: { title: "Codex" },
  beforeLoad: () => requireAuth(),
  component: CodexPage,
});
