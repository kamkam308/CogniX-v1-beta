// SPDX-License-Identifier: AGPL-3.0-only

import { createMathPlugin } from "@streamdown/math";
import katex from "katex";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import "mathjax-full/js/input/tex/AllPackages.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { mathjax } from "mathjax-full/js/mathjax.js";
import { SVG } from "mathjax-full/js/output/svg.js";
import { parseFragment } from "parse5";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Streamdown } from "streamdown";
import { preprocessLaTeX } from "../src/lib/latex.ts";
import {
  COGNIX_KATEX_STREAMING_OPTIONS,
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
    name: "physics table with prose comments and small scripted variables",
    markdown: String.raw`| Question | Réponse & développement |
|---|---|
| 1 – Quelle grandeur est tracée sous le nom (u_{1}(t)) ? | La courbe montre une tension qui augmente de façon exponentielle. C’est donc la tension aux bornes de la résistance (R_{1}). |
| 2 – Valeur de l’EMF (E) | En régime permanent (t \to \infty) le courant est constant. Le courant total est I_\infty = E/(R_1+R_2+r). La tension aux bornes de (R_{1}) vaut alors (\displaystyle u_1(\infty)=I_\infty R_1). La lecture du graphe donne u_{1}(\infty)=6.0\,{\rm V}. |`,
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
  {
    name: "compact math formula table without spaced pipes",
    markdown: String.raw`|Formule|Utilisation|
|---|---|
|(\displaystyle \int\frac{dx}{\sqrt{x^{2}+a}} = \ln\!\bigl(x+\sqrt{x^{2}+a}\bigr)+C)|Racine carrée simple|
|$\displaystyle \int\frac{dx}{a\cos x+b\sin x}=\frac{1}{\sqrt{a^{2}+b^{2}}}|a\cos x+b\sin x\bigr|`,
  },
  {
    name: "labeled physics table display math",
    markdown: String.raw`| Action | Direction | Expression (module) |
|---|---|---|
| $Poids $$\displaystyle\vec P =-m_{p}g;\vec\rho$$ | $-\vec\rho$ | $m_pg$ |
| Frottement\displaystyle\vec f_x = -\lambda \dot x;\vec\rho$$ | $-\vec\rho$ | $\lambda\dot x$ |
| $Force supplémentaire $$\displaystyle\vec F = -F_{0}\sin\theta;\vec\rho$$$ | $-\vec\rho$ | $F_0\sin\theta$ |`,
  },
  {
    name: "pulley equations with tags",
    markdown: String.raw`On utilise les deux équations de dynamique :

m_{1};\ddot{x}_1 = m_1g - T . \tag{18}

**Poulie mobile (masse $m_{2}$)** : la corde tire la poulie par deux segments.
m_{2};\ddot{x}_2 = 2T - m_2g . \tag{19}

$\begin{aligned}$ m_{2}\,a &=2\bigl(m_{1}g-2m_{1}a\bigr)-m_{2}g, $\qquad a\equiv\ddot x_{2}$,\\[2mm] $\bigl(m_{2}+4m_{1}\bigr)a &=g\,(2m_{1}-m_{2}), $\end{aligned}$

$\boxed{a=\ddot x_{2}=g\,\frac{2m_{1}-m_{2}}{m_{2}+4m_{1}}}. $\tag{20}$`,
  },
  {
    name: "physics prose continuation with boxed and differential equation",
    markdown: String.raw`Le point (5) du sujet fournit la valeur numérique de (E). || 3 – Expression de la résistance totale (R) | Le circuit vu par la source comprend les deux résistances extérieures et la résistance interne de la bobine :

\boxed{\,R = R_{1}+R_{2}+r\,}. $$ || **4** – Expression de (u_{1}(t)) | En écrivant la loi des mailles, on obtient \frac{{\rm d}u_{1}}{{\rm d}t}+\frac{1}{\tau}u_{1}=\frac{E}{\tau}, \qquad \tau=\frac{L}{R}.`,
  },
  {
    name: "physics prose with compact numeric relations",
    markdown: String.raw`Avec (A=R_{1}/R = 10/(20+r)). Avec (A=0.50) on trouve 0.50 = \frac{10}{20+r};\Longrightarrow;20+r=20;\Longrightarrow;\boxed{r=0;\Omega}.

La constante de temps \tau (lecture graphique) correspond à l'abscisse où la courbe atteint (1-1/e)\approx0.632 de sa valeur finale.

La poulie descend si 2m_1 > m_2 et monte si m_2 < 4m_1.`,
  },
  {
    name: "physics vector comments and orphan tag",
    markdown: String.raw`Projection de \vec F_{t\to p} sur \vec\rho :

Comme \vec F_{t\to p} = -\vec F_{p\to t}, le module est exactement le même.

Le résultat devient \boxed{F_{t\to p}=F_p}. \tag{9}$`,
  },
  {
    name: "escaped parenthesis summary table",
    markdown: String.raw`| # | Formule |
|---|---|
| (3) | (\displaystyle x\simeq l+R\cos\theta; A=R;B=l\) |
| (4) | (\displaystyle v(t)=-R\omega_{0}\sin(\omega_{0}t)\) |
| (5) | (\displaystyle \gamma(t)=-R\omega_{0}^{2}\cos(\omega_{0}t)\) |`,
  },
];

const RAW_LATEX_OUTSIDE_MATH_RE =
  /\\(?![$\\])(?:[a-zA-Z]+|[,;:!])|(?:^|[\s([{])(?:[A-Za-z](?:_\{?[^{}\s]+\}?|\^\{?[^{}\s]+\}?|\([^)\n]{0,80}\))*|[A-Za-z]{1,4}_\{?[^{}\s]+\}?)\s*(?:=|<|>|≤|≥|≈|⇒|→)/;
const VISIBLE_RAW_LATEX_RE =
  /\\[a-zA-Z]+|(?:^|[\s([{])(?:[A-Za-z](?:_\{?[^{}\s]+\}?|\^\{?[^{}\s]+\}?|\([^)\n]{0,80}\))*|[A-Za-z]{1,4}_\{?[^{}\s]+\}?)\s*(?:=|<|>|≤|≥|≈|⇒|→)/;
const RAW_SCRIPTED_IDENTIFIER_RE =
  /(?:^|[\s([{;:,|])(?:[A-Za-z]{1,4}|\\[a-zA-Z]+)(?:_\{[^{}\s]+\}|_\\[a-zA-Z]+|_[0-9A-Za-z](?![A-Za-z])|\^\{[^{}\s]+\}|\^\\[a-zA-Z]+|\^[0-9A-Za-z](?![A-Za-z]))+(?:\([^)\n]{0,80}\))?/;
const SPLIT_TEX_SPACING_RE = /\\\$[,;:!]/;
const CLASS_NAME_SPLIT_RE = /\s+/;

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
  {
    name: "snake case identifiers stay prose",
    markdown: "Use repo_name and branch_name in the config.",
    expected: "Use repo_name and branch_name in the config.",
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

type ParseNode = {
  attrs?: Array<{ name: string; value: string }>;
  childNodes?: ParseNode[];
  nodeName?: string;
  tagName?: string;
  value?: string;
};

const streamdownMath = createMathPlugin(COGNIX_KATEX_STREAMING_OPTIONS);

function getAttr(node: ParseNode, name: string): string {
  return node.attrs?.find((attr) => attr.name === name)?.value ?? "";
}

function shouldSkipVisibleText(node: ParseNode): boolean {
  const tagName = node.tagName ?? "";
  if (
    tagName === "annotation" ||
    tagName === "math" ||
    tagName === "mjx-container" ||
    tagName === "script" ||
    tagName === "style" ||
    tagName === "svg"
  ) {
    return true;
  }
  return getAttr(node, "class").split(CLASS_NAME_SPLIT_RE).includes("katex");
}

function collectVisibleText(node: ParseNode): string {
  if (node.nodeName === "#text") {
    return node.value ?? "";
  }
  if (shouldSkipVisibleText(node)) {
    return "";
  }
  return (node.childNodes ?? []).map(collectVisibleText).join(" ");
}

function renderMarkdownVisibleText(markdown: string): string {
  const html = renderToStaticMarkup(
    React.createElement(
      Streamdown,
      {
        mode: "streaming",
        plugins: { math: streamdownMath },
      },
      markdown,
    ),
  );
  const fragment = parseFragment(html) as ParseNode;
  return collectVisibleText(fragment).replace(/\s+/g, " ").trim();
}

function assertPreprocessedMarkdownHasNoRawLatex(): void {
  for (const fixture of PREPROCESS_FIXTURES) {
    const processed = preprocessLaTeX(fixture.markdown);
    const outsideMath = stripMathSpans(processed);
    if (
      RAW_LATEX_OUTSIDE_MATH_RE.test(outsideMath) ||
      RAW_SCRIPTED_IDENTIFIER_RE.test(outsideMath)
    ) {
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
    const visibleText = renderMarkdownVisibleText(processed);
    if (
      VISIBLE_RAW_LATEX_RE.test(visibleText) ||
      RAW_SCRIPTED_IDENTIFIER_RE.test(visibleText)
    ) {
      throw new Error(
        `Raw LaTeX remained visible after Streamdown render in ${fixture.name}:\n${visibleText}\n\nProcessed markdown:\n${processed}`,
      );
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
