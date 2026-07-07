// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { Switch } from "@/components/ui/switch";
import { useDeveloperOptions } from "@/hooks/use-developer-mode";
import { SettingsRow } from "../components/settings-row";
import { SettingsSection } from "../components/settings-section";

export function DeveloperTab() {
  const [options, setOptions] = useDeveloperOptions();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold font-heading">Developer</h1>
        <p className="text-xs text-muted-foreground">
          Choose which advanced CogniX surfaces are visible.
        </p>
      </header>

      <SettingsSection title="Interface">
        <SettingsRow
          label="Right sidebar"
          description="Show the advanced conversation sidebar on the right."
        >
          <Switch
            checked={options.rightSidebar}
            onCheckedChange={(rightSidebar) =>
              setOptions({ ...options, rightSidebar })
            }
          />
        </SettingsRow>
        <SettingsRow
          label="Training tools"
          description="Show Train, Recipes, Export, and training recents."
        >
          <Switch
            checked={options.trainingTools}
            onCheckedChange={(trainingTools) =>
              setOptions({ ...options, trainingTools })
            }
          />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
