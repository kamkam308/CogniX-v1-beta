export type CogniXPlanId =
  | "free"
  | "go"
  | "plus"
  | "pro"
  | "business"
  | "enterprise";

export type CogniXToolId =
  | "chat"
  | "search"
  | "hub"
  | "codex"
  | "images"
  | "library"
  | "pulse"
  | "gpts"
  | "scheduled"
  | "training"
  | "apps"
  | "admin";

export interface CogniXPlanOption {
  id: CogniXPlanId;
  label: string;
  audience: string;
  summary: string;
  guidance: string;
  highlights: string[];
  enabledTools: CogniXToolId[];
}

export interface CogniXPlanConfig {
  version: 1;
  planId: CogniXPlanId;
  source: "desktop-setup" | "default";
  configuredAt: string;
  enabledTools: CogniXToolId[];
}

export const COGNIX_PLAN_STORAGE_KEY = "cognix_plan_config_v1";
export const DEFAULT_COGNIX_PLAN_ID: CogniXPlanId = "pro";
export const RECOMMENDED_COGNIX_PLAN_ID: CogniXPlanId = "plus";

export const COGNIX_PLAN_OPTIONS: CogniXPlanOption[] = [
  {
    id: "free",
    label: "Free",
    audience: "Usage quotidien",
    summary: "Pour discuter, chercher, tester et garder CogniX léger.",
    guidance:
      "Choisis Free si tu veux une installation simple, peu d'outils visibles et un espace de travail centré sur le chat.",
    highlights: [
      "Chat, recherche et Hub",
      "Images et Codex en accès limité",
      "Interface volontairement minimale",
    ],
    enabledTools: ["chat", "search", "hub", "images", "codex"],
  },
  {
    id: "go",
    label: "Go",
    audience: "Usage personnel régulier",
    summary: "Pour plus de fichiers, d'images, de mémoire et de contexte.",
    guidance:
      "Choisis Go si CogniX devient ton assistant personnel principal, sans avoir besoin des outils avancés de développement.",
    highlights: [
      "Tout Free avec plus de marge",
      "Bibliothèque et images plus visibles",
      "Mémoire et contexte étendus",
    ],
    enabledTools: ["chat", "search", "hub", "images", "library", "codex"],
  },
  {
    id: "plus",
    label: "Plus",
    audience: "Créateur ou power user",
    summary: "Pour projets, GPTs, recherche approfondie et Codex plus présent.",
    guidance:
      "Choisis Plus si tu veux l'équilibre naturel entre productivité, création, projets et outils avancés.",
    highlights: [
      "Projets, GPTs et recherche",
      "Codex étendu",
      "Accès anticipé aux fonctions CogniX",
    ],
    enabledTools: [
      "chat",
      "search",
      "hub",
      "images",
      "library",
      "pulse",
      "gpts",
      "codex",
      "training",
    ],
  },
  {
    id: "pro",
    label: "Pro",
    audience: "Développeur, CEO ou recherche",
    summary: "Pour Codex intensif, training, tâches planifiées et gros contexte.",
    guidance:
      "Choisis Pro si tu développes, testes des modèles, pilotes CogniX comme OS personnel ou veux débloquer les outils avancés.",
    highlights: [
      "Codex et training prioritaires",
      "Tâches, recherche et contexte étendus",
      "Préversions et fonctions expérimentales",
    ],
    enabledTools: [
      "chat",
      "search",
      "hub",
      "codex",
      "images",
      "library",
      "pulse",
      "gpts",
      "scheduled",
      "training",
    ],
  },
  {
    id: "business",
    label: "Business",
    audience: "Start-up ou entreprise",
    summary: "Pour espace collaboratif, applications, rôles et sécurité d'équipe.",
    guidance:
      "Choisis Business si CogniX doit servir une équipe avec des applications, des rôles et une organisation plus contrôlée.",
    highlights: [
      "Apps, projets partagés et GPTs",
      "Gestion d'équipe et sécurité",
      "Outils professionnels visibles",
    ],
    enabledTools: [
      "chat",
      "search",
      "hub",
      "codex",
      "images",
      "library",
      "pulse",
      "gpts",
      "scheduled",
      "training",
      "apps",
      "admin",
    ],
  },
  {
    id: "enterprise",
    label: "Enterprise",
    audience: "Organisation à grande échelle",
    summary: "Pour gouvernance, conformité, support prioritaire et contrôle maximal.",
    guidance:
      "Choisis Enterprise pour une organisation réglementée ou multi-équipe qui exige gouvernance, audit, sécurité et support renforcés.",
    highlights: [
      "Contrôles avancés et conformité",
      "Support prioritaire et gouvernance",
      "Tous les outils CogniX activés",
    ],
    enabledTools: [
      "chat",
      "search",
      "hub",
      "codex",
      "images",
      "library",
      "pulse",
      "gpts",
      "scheduled",
      "training",
      "apps",
      "admin",
    ],
  },
];

export function getCogniXPlanOption(planId: CogniXPlanId): CogniXPlanOption {
  return (
    COGNIX_PLAN_OPTIONS.find((option) => option.id === planId) ??
    COGNIX_PLAN_OPTIONS.find((option) => option.id === DEFAULT_COGNIX_PLAN_ID) ??
    COGNIX_PLAN_OPTIONS[0]
  );
}

export function buildCogniXPlanConfig(
  planId: CogniXPlanId,
  source: CogniXPlanConfig["source"] = "desktop-setup",
): CogniXPlanConfig {
  const plan = getCogniXPlanOption(planId);
  return {
    version: 1,
    planId: plan.id,
    source,
    configuredAt: new Date().toISOString(),
    enabledTools: [...plan.enabledTools],
  };
}

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readCogniXPlanConfig(): CogniXPlanConfig | null {
  const storage = getStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(COGNIX_PLAN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CogniXPlanConfig>;
    if (parsed.version !== 1 || !parsed.planId) return null;
    const plan = getCogniXPlanOption(parsed.planId);
    return {
      version: 1,
      planId: plan.id,
      source: parsed.source === "desktop-setup" ? "desktop-setup" : "default",
      configuredAt:
        typeof parsed.configuredAt === "string"
          ? parsed.configuredAt
          : new Date().toISOString(),
      enabledTools: [...plan.enabledTools],
    };
  } catch {
    return null;
  }
}

export function getEffectiveCogniXPlanConfig(): CogniXPlanConfig {
  return (
    readCogniXPlanConfig() ??
    buildCogniXPlanConfig(DEFAULT_COGNIX_PLAN_ID, "default")
  );
}

export function saveCogniXPlanConfig(planId: CogniXPlanId): CogniXPlanConfig {
  const config = buildCogniXPlanConfig(planId);
  const storage = getStorage();
  if (!storage) return config;
  try {
    storage.setItem(COGNIX_PLAN_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // Storage can fail in restricted webviews; the app still proceeds with the
    // in-memory defaults for this session.
  }
  return config;
}
