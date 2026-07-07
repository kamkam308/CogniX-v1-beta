// SPDX-License-Identifier: AGPL-3.0-only

import katex from "katex";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import "mathjax-full/js/input/tex/AllPackages.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { mathjax } from "mathjax-full/js/mathjax.js";
import { SVG } from "mathjax-full/js/output/svg.js";
import { preprocessLaTeX } from "../src/lib/latex.ts";
import {
  COGNIX_MATHJAX_SVG_OPTIONS,
  COGNIX_MATHJAX_TEX_OPTIONS,
} from "../src/lib/math-rendering.ts";

const FORMULAS = [
  String.raw`\boxed{r_e=l_0+\dfrac{mg}{k}}`,
  String.raw`\vec a=(\ddot r-r\dot\theta^2)\mathbf e_r+(r\ddot\theta+2\dot r\dot\theta)\mathbf e_\theta`,
  String.raw`\displaystyle \int_0^1 x^4\ln^2(x)\,dx`,
  String.raw`\mathcal{R}_s,\quad \varphi=\dfrac{\ell}{R}\theta`,
  String.raw`\begin{aligned} E &= mc^2 \\ F_g &= -mg\,\mathbf j \end{aligned}`,
];

const PREPROCESS_FIXTURES = [
  {
    name: "blockquote formulas",
    markdown: String.raw`> Exercice A – Ressort-masse tournant dans le plan vertical
>
> 1. Forces : F_g = -mg\mathbf j, (\mathbf{F}_{s}= -k(r-l_{0})\,\mathbf e_{r}).
> 2. Position d’équilibre : (k(r_{e}-l_{0})=mg;\Rightarrow\;r_{e}=l_{0}+mg/k).`,
  },
  {
    name: "table formulas",
    markdown: String.raw`| Formule | Utilisation |
|---|---|
| (\displaystyle \int\frac{dx}{\sqrt{x^{2}+a}} = \ln\!\bigl(x+\sqrt{x^{2}+a}\bigr)+C) | Racine carrée simple |
| $\displaystyle \int\frac{dx}{a\cos x+b\sin x}=\frac{1}{\sqrt{a^{2}+b^{2}}} | a\cos x+b\sin x\bigr |`,
  },
  {
    name: "malformed table continuation",
    markdown: String.raw`\boxed{\,R = R_{1}+R_{2}+r\,} $$ || **4** – Expression de (u_{1}(t)) | En écrivant la loi des mailles`,
  },
  {
    name: "physics table comments",
    markdown: String.raw`| Force | Expression vectorielle (dans (\mathcal{R}_{s})) |
| Poids | F_g = -mg\mathbf j |
| Tension | (\displaystyle \mathbf F_s=-k(r-l_{0})\,\mathbf e_r) |`,
  },
  {
    name: "full physics comment block",
    markdown: String.raw`> Exercice A – Ressort-masse tournant dans le plan vertical
>
> 1. Forces : F_g = -mg\mathbf j, (\mathbf{F}_{s}= -k(r-l_{0})\,\mathbf e_{r}).
> 2. Position d’équilibre : (k(r_{e}-l_{0})=mg;\Rightarrow\;r_{e}=l_{0}+mg/k).
> 3. j = \sin\theta e_r + \cos\theta e_\theta.
> 4. Vitesse : v = \dot r e_r + r\dot\theta e_\theta.
> 5. Accélération : (\mathbf a = (\ddot r-r\dot\theta^2)\mathbf e_r+(r\ddot\theta+2\dot r\dot\theta)\mathbf e_\theta).
>
> Valeurs numériques : k/m = 2.94\times 10^2 s^{-2} et r_e = 0.298 m ; k=1.47\times10^3 N m^{-1}, l_0=0.265 m.`,
  },
  {
    name: "physics answer table with prose and formulas",
    markdown: String.raw`| Question | Réponse & développement |
|---|---|
| 1 – Quelle grandeur est tracée sous le nom (u_{1}(t)) ? | La tension aux bornes de (R_{1}). |
| 2 – Valeur de l’EMF (E) | En régime permanent (t \to \infty), I_\infty = E/(R_1+R_2+r). La tension vaut u_1(\infty)=I_\infty R_1. |`,
  },
  {
    name: "physics continuation after broken table",
    markdown: String.raw`\boxed{\,R = R_{1}+R_{2}+r\,} $$ || **4** – Expression de (u_{1}(t)) | En écrivant la loi des mailles pour la boucle contenant (R_{1}) et la bobine, on obtient \frac{{\rm d}u_1}{{\rm d}t}+\frac{1}{\tau}u_1=\frac{E}{\tau}, \qquad \tau=\frac{L}{R}.`,
  },
  {
    name: "math substitution table",
    markdown: String.raw`| Condition sur f(t) | Substitution proposée |
|---|---|
| (f(-t)=-f(t)) | x = \cos t |
| (f(\pi-t)=-f(t)) | x = \sin t |
| (f(\pi+t)=f(t)) | x = \tan t |
| Aucun des cas précédents | x = \tan \frac{t}{2} |`,
  },
  {
    name: "math formula recap table",
    markdown: String.raw`| Formule | Utilisation |
|---|---|
| \int u'v = uv-\int uv' | Intégration par parties |
| (\displaystyle \int\frac{dx}{\sqrt{x^{2}+a}}=\ln\!\bigl(x+\sqrt{x^{2}+a}\bigr)+C) | Racine carrée simple |
| $\displaystyle \int\frac{dx}{a\cos x+b\sin x}=\frac{1}{\sqrt{a^{2}+b^{2}}} | a\cos x+b\sin x\bigr |`,
  },
];

const RAW_LATEX_OUTSIDE_MATH_RE =
  /\\(?![$\\])(?:[a-zA-Z]+|[,;:!])|(?:^|[\s([{])(?:[A-Za-z](?:_\{?[^{}\s]+\}?|\^\{?[^{}\s]+\}?|\([^)\n]{0,80}\))*|[A-Za-z]{1,4}_\{?[^{}\s]+\}?)\s*(?:=|<|>|≤|≥|≈|⇒|→)/;
const SPLIT_TEX_SPACING_RE = /\\\$[,;:!]/;

const NON_MATH_FIXTURES = [
  {
    name: "currency dollars stay escaped",
    markdown: "This costs $5 and $10, not a math formula.",
    expected: "This costs \\$5 and \\$10, not a math formula.",
  },
  {
    name: "config assignments stay prose",
    markdown: "Use repo=foo and branch=main in the config.",
    expected: "Use repo=foo and branch=main in the config.",
  },
];

function stripMathSpans(markdown: string): string {
  let out = "";
  let cursor = 0;

  while (cursor < markdown.length) {
    const displayStart = markdown.indexOf("$$", cursor);
    const inlineStart = markdown.indexOf("$", cursor);
    const start =
      displayStart >= 0 && (inlineStart < 0 || displayStart <= inlineStart)
        ? displayStart
        : inlineStart;

    if (start < 0) {
      out += markdown.slice(cursor);
      break;
    }

    out += markdown.slice(cursor, start);
    const isDisplay = markdown.slice(start, start + 2) === "$$";
    const delimiter = isDisplay ? "$$" : "$";
    const close = markdown.indexOf(delimiter, start + delimiter.length);
    if (close < 0) {
      out += markdown.slice(start);
      break;
    }
    cursor = close + delimiter.length;
  }

  return out;
}

function collectMathSpans(markdown: string): string[] {
  const spans: string[] = [];
  let cursor = 0;

  while (cursor < markdown.length) {
    const displayStart = markdown.indexOf("$$", cursor);
    const inlineStart = markdown.indexOf("$", cursor);
    const start =
      displayStart >= 0 && (inlineStart < 0 || displayStart <= inlineStart)
        ? displayStart
        : inlineStart;

    if (start < 0) {
      break;
    }

    const isDisplay = markdown.slice(start, start + 2) === "$$";
    const delimiter = isDisplay ? "$$" : "$";
    const bodyStart = start + delimiter.length;
    const close = markdown.indexOf(delimiter, bodyStart);
    if (close < 0) {
      spans.push(markdown.slice(start));
      break;
    }
    spans.push(markdown.slice(bodyStart, close).trim());
    cursor = close + delimiter.length;
  }

  return spans.filter(Boolean);
}

function assertMathJaxRenders(formula: string, label: string): void {
  const mathJaxNode = mathJaxDocument.convert(formula, { display: true });
  const mathJaxHtml = adaptor.outerHTML(mathJaxNode);

  if (
    !mathJaxHtml.includes("<mjx-container") ||
    mathJaxHtml.includes("data-mjx-error") ||
    mathJaxHtml.includes("<mjx-merror")
  ) {
    throw new Error(`MathJax did not render ${label}: ${formula}`);
  }
}

function assertPreprocessedMarkdownHasNoRawLatex(): void {
  for (const fixture of PREPROCESS_FIXTURES) {
    const processed = preprocessLaTeX(fixture.markdown);
    const outsideMath = stripMathSpans(processed);
    if (RAW_LATEX_OUTSIDE_MATH_RE.test(outsideMath)) {
      throw new Error(
        `Raw LaTeX remained outside math spans in ${fixture.name}:\n${processed}`,
      );
    }
    if (SPLIT_TEX_SPACING_RE.test(processed)) {
      throw new Error(
        `A TeX spacing command was split by a dollar delimiter in ${fixture.name}:\n${processed}`,
      );
    }
    for (const formula of collectMathSpans(processed)) {
      assertMathJaxRenders(formula, fixture.name);
    }
  }

  for (const fixture of NON_MATH_FIXTURES) {
    const processed = preprocessLaTeX(fixture.markdown);
    if (processed !== fixture.expected) {
      throw new Error(
        `Non-math fixture changed unexpectedly in ${fixture.name}:\n${processed}`,
      );
    }
  }
}

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX(COGNIX_MATHJAX_TEX_OPTIONS);
const svg = new SVG(COGNIX_MATHJAX_SVG_OPTIONS);
const mathJaxDocument = mathjax.document("", {
  // biome-ignore lint/style/useNamingConvention: MathJax expects this option name.
  InputJax: tex,
  // biome-ignore lint/style/useNamingConvention: MathJax expects this option name.
  OutputJax: svg,
});

for (const formula of FORMULAS) {
  const katexHtml = katex.renderToString(formula, {
    displayMode: false,
    strict: false,
    throwOnError: false,
  });

  if (
    !katexHtml.includes('class="katex"') ||
    katexHtml.includes("katex-error")
  ) {
    throw new Error(`KaTeX did not render cleanly: ${formula}`);
  }

  assertMathJaxRenders(formula, "fixture formula");
}

assertPreprocessedMarkdownHasNoRawLatex();

process.stdout.write(
  `CogniX math rendering check passed (${FORMULAS.length} formulas, ${PREPROCESS_FIXTURES.length} markdown fixtures, KaTeX + MathJax)\n`,
);
