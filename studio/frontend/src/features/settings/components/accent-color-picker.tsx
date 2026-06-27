// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Tick02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { ACCENT_COLORS, useAccentColor } from "../stores/accent-color-store";

export function AccentColorPicker() {
  const { accentColor, setAccentColor } = useAccentColor();

  return (
    <div className="grid grid-cols-6 gap-2 sm:grid-cols-11">
      {ACCENT_COLORS.map((option) => {
        const active = accentColor === option.id;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => setAccentColor(option.id)}
            className="group relative flex size-8 items-center justify-center rounded-full border border-border bg-background transition-[border-color,box-shadow,transform] hover:scale-105 hover:border-foreground/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-label={`Use ${option.label} buttons`}
            aria-pressed={active}
            title={option.label}
          >
            <span
              className="size-5 rounded-full shadow-sm ring-1 ring-black/10"
              style={{ backgroundColor: option.color }}
            />
            {active ? (
              <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/5">
                <HugeiconsIcon
                  icon={Tick02Icon}
                  strokeWidth={2}
                  className="size-3.5"
                  style={{ color: option.foreground }}
                />
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
