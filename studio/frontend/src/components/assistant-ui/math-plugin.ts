// SPDX-License-Identifier: AGPL-3.0-only
// Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

import {
  COGNIX_KATEX_STREAMING_OPTIONS,
  COGNIX_MATHJAX_SVG_OPTIONS,
  COGNIX_MATHJAX_TEX_OPTIONS,
  COGNIX_MATH_HINT_RE,
} from "@/lib/math-rendering";
import { createMathPlugin } from "@streamdown/math";
import { useEffect, useState } from "react";
import type { MathPlugin } from "streamdown";

export const katexMath = createMathPlugin(COGNIX_KATEX_STREAMING_OPTIONS);

let mathJaxMathPromise: Promise<MathPlugin> | null = null;

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
        svg: COGNIX_MATHJAX_SVG_OPTIONS,
        tex: COGNIX_MATHJAX_TEX_OPTIONS,
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
  const shouldUseMathJax = !isStreaming && COGNIX_MATH_HINT_RE.test(content);

  useEffect(() => {
    if (!shouldUseMathJax) {
      return;
    }

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
