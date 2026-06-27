// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { authFetch } from "@/features/auth";
import { useEffect, useState } from "react";
import { SettingsSection } from "../components/settings-section";

interface AdminUser {
  username?: string | null;
  email?: string | null;
  displayName?: string | null;
  display_name?: string | null;
  role?: string | null;
  plan?: string | null;
  loginLocked?: boolean;
  login_locked?: boolean;
  loginLockoutUntil?: string | null;
  login_lockout_until?: string | null;
}

type LoadState = "idle" | "loading" | "loaded" | "error";

function getDisplayName(user: AdminUser): string {
  return user.displayName ?? user.display_name ?? user.username ?? "User";
}

function getMeta(user: AdminUser): string {
  const email = user.email?.trim();
  const username = user.username?.trim();
  if (username && email) return `${username} - ${email}`;
  return username || email || "Local CogniX account";
}

function isAdminUser(user: AdminUser): boolean {
  return (
    user.role?.toLowerCase() === "admin" ||
    user.plan?.toLowerCase() === "ceo" ||
    getDisplayName(user).toLowerCase() === "kamil"
  );
}

function getBadge(user: AdminUser): string {
  if (isAdminUser(user)) return "Admin - CEO";
  return `User - ${(user.plan || "free").toLowerCase()}`;
}

export function AdminTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function loadUsers() {
    setState("loading");
    setMessage(null);
    try {
      const res = await authFetch("/api/auth/admin/users");
      if (!res.ok) {
        setState("error");
        setMessage(
          res.status === 403
            ? "Ce compte n'a pas acces aux parametres admin."
            : "La route admin n'est pas disponible sur ce backend.",
        );
        return;
      }
      const data = (await res.json()) as AdminUser[] | { users?: AdminUser[] };
      setUsers(Array.isArray(data) ? data : data.users ?? []);
      setState("loaded");
    } catch {
      setState("error");
      setMessage("Impossible de charger les comptes admin.");
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold font-heading">Admin</h1>
          <p className="text-xs text-muted-foreground">
            Comptes locaux CogniX. Le compte CEO voit toutes les conversations
            dans la sidebar.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void loadUsers()}
          disabled={state === "loading"}
        >
          {state === "loading" ? "Loading..." : "Refresh"}
        </Button>
      </header>

      <SettingsSection title="Users">
        <div className="flex flex-col gap-2 py-2">
          {state === "error" ? (
            <p className="rounded-xl border border-border/70 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
              {message}
            </p>
          ) : null}

          {state !== "error" && users.length === 0 ? (
            <p className="rounded-xl border border-border/70 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
              {state === "loading" ? "Chargement..." : "Aucun compte trouve."}
            </p>
          ) : null}

          {users.map((user) => {
            const locked = Boolean(user.loginLocked ?? user.login_locked);
            const lockoutUntil =
              user.loginLockoutUntil ?? user.login_lockout_until;
            return (
              <div
                key={`${user.username ?? ""}:${user.email ?? ""}`}
                className="flex items-center justify-between gap-4 rounded-xl border border-border/70 bg-background px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">
                    {getDisplayName(user)}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {getMeta(user)}
                  </div>
                  {locked ? (
                    <div className="mt-1 text-xs text-destructive">
                      Locked{lockoutUntil ? ` until ${lockoutUntil}` : ""}
                    </div>
                  ) : null}
                </div>
                <span className="shrink-0 rounded-full bg-muted px-3 py-1 text-xs font-semibold text-foreground">
                  {getBadge(user)}
                </span>
              </div>
            );
          })}
        </div>
      </SettingsSection>
    </div>
  );
}
