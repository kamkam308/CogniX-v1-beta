// SPDX-License-Identifier: AGPL-3.0-only

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  asArray,
  asRecord,
  cognixJson,
  jsonBody,
  readNumber,
  readString,
  readStringList,
  type JsonRecord,
} from "@/features/cognix-modules/api";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { Check, LibraryBig, Plus, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type SkillCatalogState = {
  skills: JsonRecord[];
  summary: JsonRecord;
};

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "approved") return "default";
  if (status === "pending_approval") return "secondary";
  if (status === "disabled" || status === "denied") return "destructive";
  return "outline";
}

function roleLabel(skill: JsonRecord): string {
  const roles = readStringList(skill.allowedRoles);
  if (roles.length === 0) return "admin";
  return roles.slice(0, 3).join(", ");
}

function skillId(skill: JsonRecord): string {
  return readString(skill.id) || readString(skill.skillId);
}

export function InternalSkillsMarketplace({
  className,
}: { className?: string }) {
  const [catalog, setCatalog] = useState<SkillCatalogState>({
    skills: [],
    summary: {},
  });
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [category, setCategory] = useState("operations");
  const [instructions, setInstructions] = useState("");
  const [allowedRoles, setAllowedRoles] = useState("admin, ceo");
  const visibleSkills = useMemo(
    () => catalog.skills.slice(0, 5),
    [catalog.skills],
  );

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await cognixJson("/api/cognix/skills/marketplace");
      const marketplace = asRecord(payload.skillMarketplaceCatalog);
      setCatalog({
        skills: asArray(marketplace.skills),
        summary: asRecord(marketplace.summary),
      });
    } catch (error) {
      toast.error("Internal skills unavailable", {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const publishSkill = async () => {
    const name = displayName.trim();
    const prompt = instructions.trim();
    if (!name || !prompt) return;
    setPublishing(true);
    try {
      await cognixJson("/api/cognix/skills/marketplace/skills", {
        method: "POST",
        body: jsonBody({
          displayName: name,
          category,
          instructions: prompt,
          allowedRoles: allowedRoles
            .split(",")
            .map((role) => role.trim())
            .filter(Boolean),
        }),
      });
      setDisplayName("");
      setInstructions("");
      setFormOpen(false);
      toast.success("Skill published");
      await loadCatalog();
    } catch (error) {
      toast.error("Publish failed", {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setPublishing(false);
    }
  };

  const decideSkill = async (id: string, status: "approved" | "disabled") => {
    try {
      await cognixJson(
        `/api/cognix/skills/marketplace/skills/${encodeURIComponent(id)}/approval`,
        {
          method: "PATCH",
          body: jsonBody({ status }),
        },
      );
      toast.success(
        status === "approved" ? "Skill approved" : "Skill disabled",
      );
      await loadCatalog();
    } catch (error) {
      toast.error("Decision failed", {
        description: error instanceof Error ? error.message : undefined,
      });
    }
  };

  const useSkill = async (id: string) => {
    try {
      await cognixJson("/api/cognix/skills/marketplace/usage", {
        method: "POST",
        body: jsonBody({ skillId: id, action: "use" }),
      });
      toast.success("Skill usage logged");
      await loadCatalog();
    } catch (error) {
      toast.error("Skill blocked", {
        description: error instanceof Error ? error.message : undefined,
      });
    }
  };

  return (
    <section
      className={cn("border-b border-border/70 bg-background", className)}
    >
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-3 px-5 py-4 sm:px-8 lg:px-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70 dark:bg-card">
              <LibraryBig className="size-4" strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-foreground">
                Internal skills
              </h2>
              <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                <span>{readNumber(catalog.summary.skillCount)} skills</span>
                <span>
                  {readNumber(catalog.summary.pendingApprovalCount)} pending
                </span>
                <span>{readNumber(catalog.summary.usageLogCount)} uses</span>
              </div>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-2"
            onClick={() => setFormOpen((value) => !value)}
          >
            {formOpen ? (
              <X className="size-3.5" />
            ) : (
              <Plus className="size-3.5" />
            )}
            Publish
          </Button>
        </div>

        {formOpen && (
          <div className="grid gap-2 border-t border-border/70 pt-3 md:grid-cols-[1fr_140px_1fr_auto]">
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Skill name"
            />
            <Input
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="Category"
            />
            <Input
              value={allowedRoles}
              onChange={(event) => setAllowedRoles(event.target.value)}
              placeholder="Roles"
            />
            <Button
              size="sm"
              className="h-9"
              disabled={
                publishing || !displayName.trim() || !instructions.trim()
              }
              onClick={() => void publishSkill()}
            >
              Publish
            </Button>
            <Textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="Instructions"
              className="min-h-20 resize-none md:col-span-4"
            />
          </div>
        )}

        <div className="grid gap-2 md:grid-cols-5">
          {loading
            ? Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={index}
                  className="h-[88px] animate-pulse rounded-lg bg-muted/70 dark:bg-card"
                />
              ))
            : visibleSkills.map((skill) => {
                const id = skillId(skill);
                const status = readString(skill.status, "approved");
                return (
                  <div
                    key={id}
                    className="min-h-[88px] rounded-lg border border-border/70 bg-card/60 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-1 text-sm font-medium text-foreground">
                        {readString(skill.displayName, "Skill")}
                      </p>
                      <Badge
                        variant={statusVariant(status)}
                        className="shrink-0 text-[10px]"
                      >
                        {status.replaceAll("_", " ")}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-1 text-[11px] text-muted-foreground">
                      {roleLabel(skill)}
                    </p>
                    <div className="mt-3 flex gap-1.5">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        onClick={() => void useSkill(id)}
                      >
                        Use
                      </Button>
                      {status === "pending_approval" && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7"
                          onClick={() => void decideSkill(id, "approved")}
                        >
                          <Check className="size-3.5" />
                        </Button>
                      )}
                      {status !== "disabled" && !id.startsWith("builtin_") && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7"
                          onClick={() => void decideSkill(id, "disabled")}
                        >
                          <ShieldCheck className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
        </div>
      </div>
    </section>
  );
}
