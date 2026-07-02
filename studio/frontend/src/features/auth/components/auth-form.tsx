// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchDeviceType } from "@/config/env";
import { apiUrl } from "@/lib/api-base";
import { cn } from "@/lib/utils";
import { Link, useNavigate } from "@tanstack/react-router";
import { Eye, EyeOff } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactElement, SyntheticEvent } from "react";
import { refreshSession } from "../api";

// Bootstrap credentials injected into index.html by the backend (only present
// while default admin must_change_password is true).
declare global {
  interface Window {
    __UNSLOTH_BOOTSTRAP__?: { username: string; password: string };
  }
}

import {
  clearAuthTokens,
  getAuthToken,
  getPostAuthRoute,
  hasAuthToken,
  hasRefreshToken,
  mustChangePassword,
  resetOnboardingDone,
  setMustChangePassword,
  storeAuthTokens,
} from "../session";

type AuthMode = "login" | "signup" | "change-password";

type AuthStatusResponse = {
  initialized: boolean;
  default_username?: string;
  requires_password_change: boolean;
};

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  must_change_password: boolean;
};

type AuthFormProps = {
  mode: AuthMode;
};

const DEFAULT_LOGIN_IDENTIFIER = "";

async function loginWithPassword(
  identifier: string,
  password: string,
): Promise<TokenResponse> {
  const trimmedIdentifier = identifier.trim();
  const response = await fetch(apiUrl("/api/auth/login"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier: trimmedIdentifier,
      username: trimmedIdentifier,
      password,
    }),
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(errorPayload?.detail ?? "Connexion impossible.");
  }

  return (await response.json()) as TokenResponse;
}

async function registerWithPassword(params: {
  username: string;
  email: string;
  displayName: string;
  password: string;
}): Promise<TokenResponse> {
  const response = await fetch(apiUrl("/api/auth/register"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username: params.username.trim(),
      email: params.email.trim() || null,
      display_name: params.displayName.trim() || null,
      password: params.password,
    }),
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(errorPayload?.detail ?? "Inscription impossible.");
  }

  return (await response.json()) as TokenResponse;
}

export function AuthForm({ mode }: AuthFormProps): ReactElement | null {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const isLoginMode = mode === "login";
  const isSignupMode = mode === "signup";
  const isPasswordSetupMode = mode === "change-password";
  const identifierRef = useRef<HTMLInputElement | null>(null);
  const signupUsernameRef = useRef<HTMLInputElement | null>(null);
  const newPasswordRef = useRef<HTMLInputElement | null>(null);
  const previousModeRef = useRef<AuthMode>(mode);
  const [showPassword, setShowPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [identifier, setIdentifier] = useState(DEFAULT_LOGIN_IDENTIFIER);
  const [signupUsername, setSignupUsername] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupDisplayName, setSignupDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [requiresPasswordChange, setRequiresPasswordChange] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    if (previousModeRef.current === mode) return;
    previousModeRef.current = mode;
    setError(null);
    setLoading(false);
    setShowPassword(false);
    setShowNewPassword(false);
    setPassword("");
    setConfirmPassword("");
  }, [mode]);

  useEffect(() => {
    let canceled = false;

    async function initializeAuthForm(): Promise<void> {
      try {
        const response = await fetch(apiUrl("/api/auth/status"));
        if (!response.ok) {
          throw new Error("Impossible de charger l'etat de l'authentification.");
        }
        const result = (await response.json()) as AuthStatusResponse;
        if (canceled) return;

        setInitialized(result.initialized);
        setRequiresPasswordChange(result.requires_password_change);
        if (result.default_username) {
          setIdentifier((current) =>
            current === DEFAULT_LOGIN_IDENTIFIER ? result.default_username! : current,
          );
        }

        if (result.requires_password_change !== mustChangePassword()) {
          setMustChangePassword(result.requires_password_change);
        }

        if ((isLoginMode || isSignupMode) && result.requires_password_change) {
          navigate({ to: "/change-password" });
          return;
        }
        if (isPasswordSetupMode && !result.requires_password_change) {
          navigate({ to: "/login" });
          return;
        }

        if ((isLoginMode || isSignupMode) && !result.requires_password_change) {
          if (hasRefreshToken()) {
            const refreshed = await refreshSession();
            if (refreshed) {
              await fetchDeviceType({ force: true }).catch(() => undefined);
              if (!canceled) setStatusLoading(false);
              navigate({ to: getPostAuthRoute() });
              return;
            }
          }
          if (hasAuthToken()) {
            await fetchDeviceType({ force: true }).catch(() => undefined);
            if (!canceled) setStatusLoading(false);
            navigate({ to: getPostAuthRoute() });
            return;
          }
        }
      } catch (err: unknown) {
        if (!canceled) {
          setError(err instanceof Error ? err.message : "Chargement impossible.");
        }
      } finally {
        if (!canceled) setStatusLoading(false);
      }
    }

    void initializeAuthForm();

    return () => {
      canceled = true;
    };
  }, [isLoginMode, isPasswordSetupMode, isSignupMode, navigate]);

  useEffect(() => {
    const bootstrap = window.__UNSLOTH_BOOTSTRAP__;
    if (bootstrap && isPasswordSetupMode && !password) {
      if (bootstrap.username.trim()) {
        setIdentifier(bootstrap.username);
      }
      setPassword(bootstrap.password);
    }
  }, [isPasswordSetupMode, password]);

  useEffect(() => {
    if (statusLoading) return;
    const delay = reduced ? 0 : 220;
    const timeout = window.setTimeout(() => {
      const target = isLoginMode
        ? identifierRef.current
        : isSignupMode
          ? signupUsernameRef.current
          : newPasswordRef.current;
      target?.focus({ preventScroll: true });
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [isLoginMode, isSignupMode, isPasswordSetupMode, reduced, statusLoading]);

  const hasBootstrapPassword = Boolean(window.__UNSLOTH_BOOTSTRAP__?.password);
  const currentPassword = password || window.__UNSLOTH_BOOTSTRAP__?.password || "";
  const passwordHint = "Au moins 8 caracteres, avec deux types de caracteres, sans reprendre votre identifiant.";

  const title = useMemo(() => {
    if (isLoginMode || isSignupMode) return null;
    return "Securiser votre acces";
  }, [isLoginMode, isSignupMode]);

  const subtitle = useMemo(() => {
    if (isLoginMode) return "Accedez a votre espace local securise.";
    if (isSignupMode) return "Inscription locale avec mot de passe renforce.";
    return "Remplacez le mot de passe temporaire avant d'ouvrir CogniX.";
  }, [isLoginMode, isSignupMode]);

  const submitLabel = useMemo(() => {
    if (isLoginMode) return "Se connecter";
    if (isSignupMode) return "Creer le compte";
    return "Activer CogniX";
  }, [isLoginMode, isSignupMode]);

  const activeAuthMode = isLoginMode ? "login" : "signup";
  const authDirection = isSignupMode ? 1 : -1;
  const authModeTransition = reduced
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 420, damping: 34, mass: 0.55 };
  const panelTransition = reduced
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 360, damping: 32, mass: 0.72 };
  const layoutTransition = reduced
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 340, damping: 36, mass: 0.85 };
  const copyVariants = useMemo(
    () => ({
      initial: (direction: number) => ({
        opacity: 0,
        x: reduced ? 0 : direction * 8,
        y: reduced ? 0 : 5,
        scale: reduced ? 1 : 0.99,
        filter: reduced ? "none" : "blur(2px)",
      }),
      animate: {
        opacity: 1,
        x: 0,
        y: 0,
        scale: 1,
        filter: "blur(0px)",
      },
      exit: (direction: number) => ({
        opacity: 0,
        x: reduced ? 0 : direction * -8,
        y: reduced ? 0 : -4,
        scale: reduced ? 1 : 0.995,
        filter: reduced ? "none" : "blur(1px)",
      }),
    }),
    [reduced],
  );
  const fieldVariants = useMemo(
    () => ({
      initial: (direction: number) => ({
        opacity: 0,
        x: reduced ? 0 : direction * 18,
        scale: reduced ? 1 : 0.99,
        filter: reduced ? "none" : "blur(2px)",
      }),
      animate: {
        opacity: 1,
        x: 0,
        scale: 1,
        filter: "blur(0px)",
      },
      exit: (direction: number) => ({
        opacity: 0,
        x: reduced ? 0 : direction * -14,
        scale: reduced ? 1 : 0.995,
        filter: reduced ? "none" : "blur(1px)",
      }),
    }),
    [reduced],
  );
  const blockedByState =
    initialized === false ||
    ((isLoginMode || isSignupMode) && requiresPasswordChange) ||
    (isPasswordSetupMode && !requiresPasswordChange);

  let helperText: string | null = null;
  if (initialized === false) {
    helperText = "Auth est encore en initialisation.";
  } else if ((isLoginMode || isSignupMode) && requiresPasswordChange) {
    helperText = "Le mot de passe admin temporaire doit etre remplace avant l'inscription.";
  } else if (isPasswordSetupMode && !requiresPasswordChange) {
    helperText = "Le mot de passe initial a deja ete remplace.";
  }

  const invalidLoginForm = identifier.trim().length < 3 || password.length < 8;
  const signupPasswordMismatch =
    isSignupMode &&
    password.length > 0 &&
    confirmPassword.length > 0 &&
    password !== confirmPassword;
  const invalidSignupForm =
    signupUsername.trim().length < 3 ||
    password.length < 8 ||
    password !== confirmPassword;
  const setupPasswordMismatch =
    isPasswordSetupMode &&
    newPassword.length > 0 &&
    confirmPassword.length > 0 &&
    newPassword !== confirmPassword;
  const invalidPasswordSetupForm =
    currentPassword.length < 8 ||
    newPassword.length < 8 ||
    newPassword !== confirmPassword ||
    currentPassword === newPassword;

  async function handlePasswordSetup(): Promise<TokenResponse> {
    let accessToken = getAuthToken();

    if (hasRefreshToken()) {
      const refreshed = await refreshSession();
      accessToken = getAuthToken();
      if (!refreshed) {
        clearAuthTokens();
        accessToken = null;
      }
    }

    if (!accessToken) {
      const bootstrapToken = await loginWithPassword(identifier, currentPassword);
      storeAuthTokens(
        bootstrapToken.access_token,
        bootstrapToken.refresh_token,
      );
      setMustChangePassword(bootstrapToken.must_change_password);
      accessToken = bootstrapToken.access_token;
    }

    const response = await fetch(apiUrl("/api/auth/change-password"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });

    if (!response.ok) {
      const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(errorPayload?.detail ?? "Mise a jour du mot de passe impossible.");
    }

    return (await response.json()) as TokenResponse;
  }

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (isLoginMode && invalidLoginForm) {
      setError("Identifiant ou mot de passe invalide.");
      return;
    }
    if (isSignupMode && invalidSignupForm) {
      setError(
        password !== confirmPassword
          ? "Les mots de passe doivent correspondre."
          : "Completez le formulaire d'inscription.",
      );
      return;
    }
    if (isPasswordSetupMode) {
      if (currentPassword.length < 8) {
        setError("Mot de passe temporaire introuvable. Rechargez la page.");
        return;
      }
      if (newPassword.length < 8) {
        setError("Le nouveau mot de passe doit contenir au moins 8 caracteres.");
        return;
      }
      if (newPassword !== confirmPassword) {
        setError("Les mots de passe doivent correspondre.");
        return;
      }
      if (currentPassword === newPassword) {
        setError("Le nouveau mot de passe doit etre different.");
        return;
      }
    }

    setLoading(true);
    try {
      let token: TokenResponse;

      if (isLoginMode) {
        token = await loginWithPassword(identifier, password);
      } else if (isSignupMode) {
        token = await registerWithPassword({
          username: signupUsername,
          email: signupEmail,
          displayName: signupDisplayName,
          password,
        });
        resetOnboardingDone();
      } else {
        token = await handlePasswordSetup();
        resetOnboardingDone();
        setRequiresPasswordChange(false);
      }

      setMustChangePassword(token.must_change_password);
      storeAuthTokens(token.access_token, token.refresh_token);
      await fetchDeviceType({ force: true });
      navigate({ to: getPostAuthRoute() });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Authentification impossible.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      layout
      transition={layoutTransition}
      className="w-full space-y-6"
      aria-busy={statusLoading}
    >
      {!isPasswordSetupMode && (
        <div
          role="tablist"
          aria-label="Mode d'authentification"
          className="grid grid-cols-2 gap-1 rounded-full border border-black/10 bg-black/[0.045] p-1 dark:border-white/10 dark:bg-white/[0.06]"
        >
          {[
            { key: "login", label: "Connexion", to: "/login" },
            { key: "signup", label: "Inscription", to: "/signup" },
          ].map((item) => (
            <Link
              key={item.key}
              to={item.to}
              role="tab"
              aria-selected={activeAuthMode === item.key}
              className={cn(
                "relative flex min-h-10 items-center justify-center overflow-hidden rounded-full px-3 text-sm font-semibold transition-colors",
                activeAuthMode === item.key
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {activeAuthMode === item.key && (
                <motion.span
                  layoutId="cognix-auth-mode-pill"
                  className="absolute inset-0 rounded-full bg-background shadow-sm"
                  transition={authModeTransition}
                />
              )}
              <span className="relative z-10">{item.label}</span>
            </Link>
          ))}
        </div>
      )}

      <AnimatePresence initial={false} mode="popLayout" custom={authDirection}>
        <motion.div
          key={`${mode}-copy`}
          layout="position"
          variants={copyVariants}
          custom={authDirection}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={panelTransition}
          className="space-y-2"
        >
          {title && (
            <h2 className="text-[2rem] font-semibold leading-none tracking-normal text-foreground">
              {title}
            </h2>
          )}
          <p className="text-muted-foreground">{subtitle}</p>
        </motion.div>
      </AnimatePresence>

      <motion.form
        layout
        transition={layoutTransition}
        className="grid gap-4"
        onSubmit={handleSubmit}
      >
        <AnimatePresence initial={false} mode="popLayout" custom={authDirection}>
          <motion.div
            key={`${mode}-fields`}
            layout="position"
            variants={fieldVariants}
            custom={authDirection}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={panelTransition}
            className="grid gap-4"
          >
            {isLoginMode && (
              <>
                <div className="grid gap-2">
                  <Label htmlFor="identifier">Identifiant ou email</Label>
                  <Input
                    id="identifier"
                    ref={identifierRef}
                    className="h-12 rounded-2xl bg-background"
                    autoComplete="username"
                    value={identifier}
                    onChange={(event) => setIdentifier(event.target.value)}
                    minLength={3}
                    maxLength={254}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="password">Mot de passe</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      className="h-12 rounded-2xl bg-background pr-11"
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      minLength={8}
                      maxLength={128}
                      required
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground hover:bg-transparent"
                      onClick={() => setShowPassword((prev) => !prev)}
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </>
            )}

            {isSignupMode && (
              <>
                <div className="grid gap-2">
                  <Label htmlFor="signup-username">Nom d'utilisateur</Label>
                  <Input
                    id="signup-username"
                    ref={signupUsernameRef}
                    className="h-12 rounded-2xl bg-background"
                    autoComplete="username"
                    value={signupUsername}
                    onChange={(event) => setSignupUsername(event.target.value)}
                    minLength={3}
                    maxLength={32}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="signup-email">Email</Label>
                  <Input
                    id="signup-email"
                    type="email"
                    className="h-12 rounded-2xl bg-background"
                    autoComplete="email"
                    value={signupEmail}
                    onChange={(event) => setSignupEmail(event.target.value)}
                    maxLength={254}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="display-name">Nom affiche</Label>
                  <Input
                    id="display-name"
                    className="h-12 rounded-2xl bg-background"
                    autoComplete="name"
                    value={signupDisplayName}
                    onChange={(event) => setSignupDisplayName(event.target.value)}
                    maxLength={80}
                  />
                </div>
                <PasswordFields
                  password={password}
                  confirmPassword={confirmPassword}
                  showPassword={showPassword}
                  onPasswordChange={setPassword}
                  onConfirmPasswordChange={setConfirmPassword}
                  onTogglePassword={() => setShowPassword((prev) => !prev)}
                />
                <PasswordHint warning={signupPasswordMismatch} text={passwordHint} />
              </>
            )}

            {isPasswordSetupMode && (
              <>
                {!hasBootstrapPassword && (
                  <div className="grid gap-2">
                    <Label htmlFor="current-password">Mot de passe temporaire</Label>
                    <div className="relative">
                      <Input
                        id="current-password"
                        type={showPassword ? "text" : "password"}
                        className="h-12 rounded-2xl bg-background pr-11"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        minLength={8}
                        maxLength={128}
                        required
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                        className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground hover:bg-transparent"
                        onClick={() => setShowPassword((prev) => !prev)}
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                )}
                <div className="grid gap-2">
                  <Label htmlFor="new-password">Nouveau mot de passe</Label>
                  <div className="relative">
                    <Input
                      id="new-password"
                      ref={newPasswordRef}
                      type={showNewPassword ? "text" : "password"}
                      className="h-12 rounded-2xl bg-background pr-11"
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      minLength={8}
                      maxLength={128}
                      required
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={showNewPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground hover:bg-transparent"
                      onClick={() => setShowNewPassword((prev) => !prev)}
                    >
                      {showNewPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="confirm-new-password">Confirmer le mot de passe</Label>
                  <Input
                    id="confirm-new-password"
                    type="password"
                    className="h-12 rounded-2xl bg-background"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                </div>
                <PasswordHint warning={setupPasswordMismatch} text={passwordHint} />
              </>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="grid min-h-9 gap-1 pt-1" aria-live="polite">
          {helperText && (
            <p className="text-center text-sm leading-relaxed text-amber-600">{helperText}</p>
          )}
          {error && (
            <p className="text-center text-sm leading-relaxed text-destructive">{error}</p>
          )}
        </div>

        <Button
          type="submit"
          className="h-12 w-full rounded-2xl bg-foreground text-background hover:bg-foreground/85"
          disabled={
            loading ||
            statusLoading ||
            blockedByState ||
            (isLoginMode && invalidLoginForm) ||
            (isSignupMode && invalidSignupForm) ||
            (isPasswordSetupMode && invalidPasswordSetupForm)
          }
        >
          {loading ? "Veuillez patienter..." : submitLabel}
        </Button>
      </motion.form>

      <p className="text-sm leading-relaxed text-muted-foreground">
        {isLoginMode
          ? "Connexion protegee par verrouillage progressif et session locale."
          : isSignupMode
            ? "Votre compte reste local a cette installation CogniX."
            : "Cette etape protege le compte admin de depart."}
      </p>
    </motion.div>
  );
}

function PasswordFields({
  password,
  confirmPassword,
  showPassword,
  onPasswordChange,
  onConfirmPasswordChange,
  onTogglePassword,
}: {
  password: string;
  confirmPassword: string;
  showPassword: boolean;
  onPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
  onTogglePassword: () => void;
}) {
  return (
    <>
      <div className="grid gap-2">
        <Label htmlFor="signup-password">Mot de passe</Label>
        <div className="relative">
          <Input
            id="signup-password"
            type={showPassword ? "text" : "password"}
            className="h-12 rounded-2xl bg-background pr-11"
            autoComplete="new-password"
            value={password}
            onChange={(event) => onPasswordChange(event.target.value)}
            minLength={8}
            maxLength={128}
            required
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
            className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground hover:bg-transparent"
            onClick={onTogglePassword}
          >
            {showPassword ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="signup-confirm-password">Confirmer le mot de passe</Label>
        <Input
          id="signup-confirm-password"
          type="password"
          className="h-12 rounded-2xl bg-background"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => onConfirmPasswordChange(event.target.value)}
          minLength={8}
          maxLength={128}
          required
        />
      </div>
    </>
  );
}

function PasswordHint({ warning, text }: { warning: boolean; text: string }) {
  return (
    <p
      className={cn(
        "min-h-4 text-xs leading-relaxed",
        warning ? "text-destructive" : "text-muted-foreground",
      )}
      aria-live="polite"
    >
      {warning ? "Les mots de passe doivent correspondre." : text}
    </p>
  );
}
