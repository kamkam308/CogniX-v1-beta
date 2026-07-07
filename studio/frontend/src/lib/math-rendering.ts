// SPDX-License-Identifier: AGPL-3.0-only

export const COGNIX_MATH_HINT_RE =
  /(?:\$\$?|\\\(|\\\[|\\(?:begin|boxed|dfrac|frac|sqrt|sum|int|lim|theta|alpha|beta|gamma|Delta|Omega|omega|varphi|phi|mathbf|boldsymbol|mathbb|mathcal|mathrm|displaystyle|overline|underline|vec|dot|ddot|times|cdot|tag|quad|qquad)\b)/;

export const COGNIX_MATHJAX_TEX_PACKAGES = [
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

export const COGNIX_MATHJAX_TEX_OPTIONS = {
  displayMath: [
    ["$$", "$$"],
    ["\\[", "\\]"],
  ],
  inlineMath: [
    ["$", "$"],
    ["\\(", "\\)"],
  ],
  packages: COGNIX_MATHJAX_TEX_PACKAGES,
  processEscapes: true,
  processEnvironments: true,
  processRefs: true,
  tags: "ams",
};

export const COGNIX_MATHJAX_SVG_OPTIONS = {
  fontCache: "global",
  internalSpeechTitles: false,
};

export const COGNIX_KATEX_STREAMING_OPTIONS = {
  errorColor: "var(--color-muted-foreground)",
  singleDollarTextMath: true,
};
