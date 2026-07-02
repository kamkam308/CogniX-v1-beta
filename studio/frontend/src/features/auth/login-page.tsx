// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { LightRays } from "@/components/ui/light-rays";
import { Card } from "@/components/ui/card";
import { useRouterState } from "@tanstack/react-router";
import { motion, useReducedMotion } from "motion/react";
import { AuthForm } from "./components/auth-form";

type AuthPageMode = "login" | "signup";

export function AuthRoutePage() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  return <AuthPage mode={pathname === "/signup" ? "signup" : "login"} />;
}

export function LoginPage() {
  return <AuthPage mode="login" />;
}

export function SignupPage() {
  return <AuthPage mode="signup" />;
}

function AuthPage({ mode }: { mode: AuthPageMode }) {
  const reduced = useReducedMotion();
  const pageTransition = reduced
    ? { duration: 0 }
    : { duration: 0.22, ease: [0.215, 0.61, 0.355, 1] as const };
  const cardTransition = reduced
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 320, damping: 34, mass: 0.82 };

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-background px-4 py-8 sm:px-6 sm:py-10 md:px-10">
      <motion.img
        layoutId="cognix-auth-logo"
        src="/cognix-logo.png"
        alt="CogniX"
        className="cognix-logo-mark absolute left-6 top-6 z-20 size-9 object-contain sm:left-8 sm:top-8"
        transition={cardTransition}
      />
      <LightRays
        count={6}
        color="rgba(0, 0, 0, 0.05)"
        blur={34}
        speed={15}
        length="70vh"
        className="pointer-events-none opacity-35 dark:opacity-15"
      />
      <motion.div
        layout
        initial={{ opacity: 0, y: reduced ? 0 : 14, scale: reduced ? 1 : 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={pageTransition}
        className="relative z-10 w-full max-w-[26rem]"
        data-auth-mode={mode}
      >
        <Card className="w-full rounded-[2rem] px-7 py-8 shadow-border ring-0 sm:px-8 sm:py-10">
          <AuthForm mode={mode} />
        </Card>
      </motion.div>
    </div>
  );
}
