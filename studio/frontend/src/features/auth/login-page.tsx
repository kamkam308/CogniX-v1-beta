// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { LightRays } from "@/components/ui/light-rays";
import { Card } from "@/components/ui/card";
import { AuthForm } from "./components/auth-form";

export function LoginPage() {
  return (
    <div className="relative flex min-h-[calc(100dvh-var(--studio-titlebar-height,0px))] items-center justify-center overflow-hidden bg-background px-4 py-8 sm:px-6 sm:py-10 md:px-10">
      <img
        src="/cognix-logo.png"
        alt="CogniX"
        className="cognix-logo-mark absolute left-6 top-6 z-20 size-9 object-contain sm:left-8 sm:top-8"
      />
      <LightRays
        count={6}
        color="rgba(0, 0, 0, 0.05)"
        blur={34}
        speed={15}
        length="70vh"
        className="opacity-35 dark:opacity-15"
      />
      <Card className="relative z-10 w-full max-w-sm rounded-[2rem] px-7 py-8 shadow-border ring-0 sm:px-8 sm:py-10">
        <AuthForm mode="login" />
      </Card>
    </div>
  );
}

export function SignupPage() {
  return (
    <div className="relative flex min-h-[calc(100dvh-var(--studio-titlebar-height,0px))] items-center justify-center overflow-hidden bg-background px-4 py-8 sm:px-6 sm:py-10 md:px-10">
      <img
        src="/cognix-logo.png"
        alt="CogniX"
        className="cognix-logo-mark absolute left-6 top-6 z-20 size-9 object-contain sm:left-8 sm:top-8"
      />
      <Card className="relative z-10 w-full max-w-sm rounded-[2rem] px-7 py-8 shadow-border ring-0 sm:px-8 sm:py-10">
        <AuthForm mode="signup" />
      </Card>
    </div>
  );
}
