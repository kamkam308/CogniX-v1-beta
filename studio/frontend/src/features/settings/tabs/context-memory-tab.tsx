// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { authFetch } from "@/features/auth";
import { useEffect, useState } from "react";
import { SettingsRow } from "../components/settings-row";
import { SettingsSection } from "../components/settings-section";

type LoadState = "idle" | "loading" | "loaded" | "error" | "saving";

export function ContextMemoryTab() {
  const [memory, setMemory] = useState("");
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function loadMemory() {
    setState("loading");
    setMessage(null);
    try {
      const res = await authFetch("/api/cognix/context-memory");
      if (!res.ok) throw new Error("Context memory endpoint unavailable.");
      const data = (await res.json()) as { memory?: { content?: string } };
      setMemory(data.memory?.content ?? "");
      setState("loaded");
    } catch {
      setState("error");
      setMessage("Impossible de charger la memoire CogniX.");
    }
  }

  async function saveMemory() {
    setState("saving");
    setMessage(null);
    try {
      const res = await authFetch("/api/cognix/context-memory", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: memory }),
      });
      if (!res.ok) throw new Error("Save failed.");
      setState("loaded");
      setMessage("Memoire enregistree dans CogniX.");
      window.setTimeout(() => setMessage(null), 1400);
    } catch {
      setState("error");
      setMessage("Impossible d'enregistrer la memoire CogniX.");
    }
  }

  function clearMemory() {
    setMemory("");
    setMessage(null);
  }

  useEffect(() => {
    void loadMemory();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold font-heading">Context Memory</h1>
        <p className="text-xs text-muted-foreground">
          Memoire commune CogniX pour garder les consignes importantes entre les
          sessions.
        </p>
      </header>

      <SettingsSection
        title="Shared memory"
        description="Ajoute ici les directives stables que CogniX doit garder en contexte."
      >
        <div className="py-3">
          <textarea
            value={memory}
            onChange={(event) => {
              setMemory(event.target.value);
              setMessage(null);
            }}
            rows={8}
            className="min-h-[168px] w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
            placeholder="Ex: Toujours repondre au nom de CogniX, garder un ton professionnel, privilegier les explications courtes..."
            disabled={state === "loading" || state === "saving"}
          />
        </div>
        <SettingsRow
          label="Actions"
          description={
            message ??
            (state === "loading"
              ? "Chargement..."
              : "Sauvegarde native dans la base locale CogniX.")
          }
        >
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={clearMemory}>
              Clear
            </Button>
            <Button
              type="button"
              variant="dark"
              size="sm"
              onClick={() => void saveMemory()}
              disabled={state === "loading" || state === "saving"}
            >
              {state === "saving" ? "Saving..." : "Save"}
            </Button>
          </div>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
