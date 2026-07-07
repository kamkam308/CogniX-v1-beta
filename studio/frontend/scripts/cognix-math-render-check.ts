// SPDX-License-Identifier: AGPL-3.0-only

import katex from "katex";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import "mathjax-full/js/input/tex/AllPackages.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { mathjax } from "mathjax-full/js/mathjax.js";
import { SVG } from "mathjax-full/js/output/svg.js";
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

  const mathJaxNode = mathJaxDocument.convert(formula, { display: true });
  const mathJaxHtml = adaptor.outerHTML(mathJaxNode);

  if (
    !mathJaxHtml.includes("<mjx-container") ||
    mathJaxHtml.includes("data-mjx-error") ||
    mathJaxHtml.includes("<mjx-merror")
  ) {
    throw new Error(`MathJax did not render cleanly: ${formula}`);
  }
}

process.stdout.write(
  `CogniX math rendering check passed (${FORMULAS.length} formulas, KaTeX + MathJax)\n`,
);
