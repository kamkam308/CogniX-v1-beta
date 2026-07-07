// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import { createMathPlugin } from "@streamdown/math";
import { useEffect, useState } from "react";
import type { MathPlugin } from "streamdown";

const TEX_PACKAGES = [
  "base",
  "ams",
  "newcommand",
  "bbox",
  "boldsymbol",
  "braket",
  "cancel",
  "color",
  "configmacros",
  "enclose",
  "extpfeil",
  "html",
  "mathtools",
  "mhchem",
  "noerrors",
  "noundefined",
  "physics",
  "tagformat",
  "textcomp",
  "unicode",
  "upgreek",
  "verb",
];

export const katexMath = createMathPlugin({
  errorColor: "var(--color-muted-foreground)",
  singleDollarTextMath: true,
});

let mathJaxMathPromise: Promise<MathPlugin> | null = null;

const MATH_HINT_RE =
  /(?:\$\$?|\\\(|\\\[|\\(?:begin|boxed|frac|sqrt|sum|int|lim|theta|alpha|beta|gamma|Delta|Omega|omega|mathbf|mathcal|mathrm|displaystyle|overline|underline|vec|dot|ddot|times|cdot|tag|qquad)\b)/;

function createMathJaxPlugin(): Promise<MathPlugin> {
  mathJaxMathPromise ??= Promise.all([
    import("remark-math"),
    import("rehype-mathjax/svg"),
  ]).then(([remarkMathModule, rehypeMathJaxModule]) => ({
    name: "katex",
    type: "math",
    remarkPlugin: [
      remarkMathModule.default,
      {
        singleDollarTextMath: true,
      },
    ],
    rehypePlugin: [
      rehypeMathJaxModule.default,
      {
        svg: {
          fontCache: "global",
          internalSpeechTitles: false,
        },
        tex: {
          displayMath: [
            ["$$", "$$"],
            ["\\[", "\\]"],
          ],
          inlineMath: [
            ["$", "$"],
            ["\\(", "\\)"],
          ],
          packages: TEX_PACKAGES,
          processEscapes: true,
          processEnvironments: true,
          processRefs: true,
          tags: "ams",
        },
      },
    ],
  }));
  return mathJaxMathPromise;
}

export function useMathPlugin(
  isStreaming: boolean,
  content: string,
): MathPlugin {
  const [mathJaxMath, setMathJaxMath] = useState<MathPlugin | null>(null);
  const shouldUseMathJax = !isStreaming && MATH_HINT_RE.test(content);

  useEffect(() => {
    if (!shouldUseMathJax) return;

    let isActive = true;
    createMathJaxPlugin().then((plugin) => {
      if (isActive) {
        setMathJaxMath(plugin);
      }
    });

    return () => {
      isActive = false;
    };
  }, [shouldUseMathJax]);

  return shouldUseMathJax && mathJaxMath ? mathJaxMath : katexMath;
}
