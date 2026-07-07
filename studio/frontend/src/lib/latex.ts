// Adapted from LibreChat's latex.ts
// https://github.com/danny-avila/LibreChat/blob/main/client/src/utils/latex.ts
//
// Escapes currency dollar signs so they are not misinterpreted as LaTeX math
// delimiters when singleDollarTextMath is enabled.

/**
 * Matches a single $ followed by a number pattern (currency), e.g.:
 *   $5, $1,000, $5.99, $100K, $3.5M
 *
 * Does NOT match:
 *   $$ (display math), \$ (already escaped), $\alpha (LaTeX command)
 */
const CURRENCY_REGEX =
  /(?<![\\$])\$(?!\$)(?=\d+(?:,\d{3})*(?:\.\d+)?[KMBkmb]?(?:\s|$|[^a-zA-Z\d]))/g;

const LATEX_COMMAND_NAMES = [
  "alpha",
  "approx",
  "arccos",
  "arcsin",
  "arctan",
  "bar",
  "begin",
  "beta",
  "big",
  "Big",
  "bigg",
  "Bigg",
  "bigl",
  "Bigl",
  "biggl",
  "Biggl",
  "bigr",
  "Bigr",
  "biggr",
  "Biggr",
  "binom",
  "boxed",
  "boldsymbol",
  "cap",
  "cdot",
  "cdots",
  "choose",
  "cos",
  "cosh",
  "cot",
  "csc",
  "cup",
  "Delta",
  "delta",
  "det",
  "displaystyle",
  "dfrac",
  "dot",
  "ddot",
  "ell",
  "end",
  "epsilon",
  "equiv",
  "exists",
  "exp",
  "forall",
  "frac",
  "gamma",
  "ge",
  "geq",
  "hat",
  "infty",
  "in",
  "int",
  "lambda",
  "left",
  "Leftarrow",
  "Leftrightarrow",
  "le",
  "leq",
  "ldots",
  "lim",
  "liminf",
  "limsup",
  "lvert",
  "ln",
  "log",
  "Longleftrightarrow",
  "Longrightarrow",
  "mathbb",
  "mathcal",
  "mathfrak",
  "mathbf",
  "mathit",
  "mathrm",
  "max",
  "min",
  "mu",
  "nabla",
  "neq",
  "notin",
  "omega",
  "Omega",
  "overline",
  "overrightarrow",
  "partial",
  "phi",
  "Phi",
  "pi",
  "pmatrix",
  "prime",
  "quad",
  "qquad",
  "Rightarrow",
  "rightarrow",
  "right",
  "rm",
  "rvert",
  "sec",
  "sim",
  "sin",
  "sinh",
  "sqrt",
  "subset",
  "subseteq",
  "sum",
  "sup",
  "tag",
  "tan",
  "tanh",
  "tau",
  "tfrac",
  "text",
  "theta",
  "tilde",
  "to",
  "times",
  "underline",
  "varepsilon",
  "vec",
  "varphi",
  "widehat",
  "widetilde",
];

const LATEX_COMMAND_PATTERN = LATEX_COMMAND_NAMES.join("|");
const LATEX_IDENTIFIER_PATTERN = String.raw`[A-Za-z](?:[A-Za-z0-9]|_\{?[^{}\s]+\}?|\^\{?[^{}\s]+\}?)*`;
const LATEX_ASSIGNMENT_LEFT_PATTERN = String.raw`${LATEX_IDENTIFIER_PATTERN}(?:\s*/\s*${LATEX_IDENTIFIER_PATTERN})?`;
const LATEX_ASSIGNMENT_PATTERN = String.raw`${LATEX_ASSIGNMENT_LEFT_PATTERN}(?:\s*['’])?(?:\s*\([^()\n]{0,80}\))?\s*=`;
const LATEX_COMMAND_RE = new RegExp(
  `\\\\(?:${LATEX_COMMAND_PATTERN})(?![a-zA-Z])`,
);
const DELIMITED_MATH_RE =
  /((?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$[^$\n]*?(?<!\\)\$|\\\[[\s\S]*?\\\]|\\\([^)\n]*?\\\))/g;
const BRACKETED_BARE_LATEX_LINE_RE = new RegExp(
  `(^|\\n)([ \\t]*)\\[\\s*([^\\n\\]]*\\\\(?:${LATEX_COMMAND_PATTERN})(?![a-zA-Z])[^\\n\\]]*)\\s*\\](?=\\s*(?:\\n|$))`,
  "g",
);
const SENTENCE_BARE_LATEX_RE = new RegExp(
  `(^|[\\s:;,.])((?:\\\\(?:${LATEX_COMMAND_PATTERN})(?![a-zA-Z])|${LATEX_ASSIGNMENT_PATTERN})(?:\\.(?=\\d)|\\\\[,;:!]|[^\\n.!?;:,|[\\]]|\\([^()\\n]*\\)|\\{[^\\n{}]*\\})*)`,
  "g",
);
const URL_IN_TEXT_RE = /\shttps?:\/\//i;
const BARE_LATEX_MATH_CHAR_RE = /[\\^_{}=+\-*/<>]/;
const ANY_LATEX_COMMAND_RE = /\\[a-zA-Z]+/;
const RELATION_COMMAND_RE =
  /\\(?:to|rightarrow|Rightarrow|Longrightarrow|Leftarrow|Leftrightarrow|Longleftrightarrow|leq?|geq?|neq|approx|sim|equiv)(?![a-zA-Z])/;
const SUBSCRIPT_OR_SUPERSCRIPT_RE = /[A-Za-z0-9)}]\s*(?:[_^]\{?[^{}\s]+\}?)/;
const UNICODE_MATH_SIGNAL_RE = /[∫∑∏√∞≈≠≤≥→⇒↔±×÷πθτφϕΩωαβγδλμσΔΣ]/;
const COMPACT_EQUATION_RE =
  /(?:^|[\s([{])(?:[A-Za-z](?:_\{?[^{}\s]+\}?|\^\{?[^{}\s]+\}?|\([^)\n]{0,80}\))*|[A-Za-z]{1,4}_\{?[^{}\s]+\}?|\\[a-zA-Z]+(?:\{[^{}\n]*\})?)\s*(?:=|<|>|≤|≥|≈|\\leq?|\\geq?|\\neq|\\approx|\\Rightarrow|\\Longrightarrow|⇒|→)/;
const FUNCTION_EQUATION_RE =
  /(?:^|[\s([{])(?:[A-Za-z]|\\[a-zA-Z]+)\s*\([^)\n]{1,80}\)\s*(?:=|<|>|≤|≥|≈|\\leq?|\\geq?|\\neq|\\approx)/;
const PLAIN_FUNCTION_MATH_RE =
  /\b(?:sin|cos|tan|ln|log|exp|lim|arctan|arcsin|arccos)\s*(?:[A-Za-z0-9({\\]|$)/;
const COMPACT_OPERATOR_CHAIN_RE =
  /(?:[A-Za-z0-9)}\]]|\\[a-zA-Z]+)\s*(?:[+\-*/=<>]|≤|≥|≈|⇒|→)\s*(?:[A-Za-z0-9({\\[]|[-+])/;
const MAX_PROSE_WORDS_IN_BARE_MATH = 3;
const LEADING_SPACE_RE = /^\s*/;
const TRAILING_SPACE_RE = /\s*$/;
const BACKSLASH_DISPLAY_MATH_RE = /\\\[([\s\S]*?)\\\]/g;
const BACKSLASH_INLINE_MATH_RE = /\\\(([^)\n]*?)\\\)/g;
const UNESCAPED_DOLLAR_GLOBAL_RE = /(?<!\\)\$/g;
const SPACED_TABLE_SEPARATOR_RE = /\s+\|\s+/;
const TABLE_LINE_SPLIT_RE = /(\s+\|\s+)/;
const TABLE_CELL_LEADING_RE = /^\s*\|\s*/;
const TABLE_CELL_TRAILING_RE = /\s*\|\s*$/;
const MARKDOWN_TABLE_SEPARATOR_RE = /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$/;
const PROSE_WORD_RE =
  /\b(?:avec|alors|aucun|comme|condition|dans|de|des|donc|du|en|est|et|la|le|les|nom|on|ou|par|pour|regime|régime|sur|une|un|valeur|voir)\b/i;
const MATH_LEADING_BODY_RE = new RegExp(
  `^\\s*(?:\\\\(?:${LATEX_COMMAND_PATTERN})(?![a-zA-Z])|${LATEX_ASSIGNMENT_PATTERN}|[A-Za-z0-9_{}\\\\^]+\\s*[+\\-*/=<>])`,
);
const TABLE_CELL_DISPLAYSTYLE_RE = /^\(?\s*\\displaystyle\b/;
const NEWLINE_SPLIT_RE = /(\n)/;
const WHITESPACE_RE = /\s/;
const MATH_OPERATOR_CHAR_RE = /[=+\-*/<>]/;
const DIGIT_RE = /\d/;
const MATH_IDENTIFIER_SUFFIX_RE = /[A-Za-z0-9}_]$/;
const MAX_INLINE_MATH_SPAN = 200;
const DANGLING_DELIMITER_SIZE_RE =
  /\\(?:(?:bigl|Bigl|biggl|Biggl|bigr|Bigr|biggr|Biggr)(?!\s*(?:[()[\]{}|.]|\\(?:lvert|rvert|vert|lbrace|rbrace|langle|rangle|lfloor|rfloor|lceil|rceil)))|(?:big|Big|bigg|Bigg)(?![a-zA-Z])(?!\s*(?:[()[\]{}|.]|\\(?:lvert|rvert|vert|lbrace|rbrace|langle|rangle|lfloor|rfloor|lceil|rceil))))/g;
const ORPHAN_DISPLAY_CLOSER_RE =
  /(^|[\n\s])((?:\\(?:boxed|displaystyle|frac|sqrt|int)[^\n$]*?))\s*\$\$(?=\s*(?:\|\||\||$))/g;
const DOUBLE_PIPE_DISPLAY_RE = /\$\$\s+\|\|\s+/g;
const WORD_RE = /[\p{L}]+/gu;
const WRAPPABLE_COMMANDS_WITH_ARGUMENT_RE = /\\boxed\{(?:[^{}]|\{[^{}]*\})*\}/g;
const FORMULA_CONNECTOR_SPLIT_RE = new RegExp(
  String.raw`(\s+(?:et|ou|donc|avec)\s+)(?=${LATEX_ASSIGNMENT_LEFT_PATTERN}(?:\s*['’])?(?:\s*\([^()\n]{0,80}\))?\s*=)`,
  "i",
);

/**
 * Find code-block regions (``` ... ``` and ` ... `) to skip.
 * Returns a sorted array of [start, end] index pairs.
 */
function findCodeBlockRegions(content: string): [number, number][] {
  const regions: [number, number][] = [];

  // Fenced code blocks: ```...```
  const fencedRe = /```[\s\S]*?```/g;
  let match: RegExpExecArray | null = fencedRe.exec(content);
  while (match !== null) {
    regions.push([match.index, match.index + match[0].length]);
    match = fencedRe.exec(content);
  }

  // Inline code: `...` (skip spans inside fenced blocks, filtered below)
  const inlineRe = /`[^`\n]+`/g;
  match = inlineRe.exec(content);
  while (match !== null) {
    const start = match.index;
    const end = start + match[0].length;
    let inside = false;
    for (const [rs, re] of regions) {
      if (start >= rs && end <= re) {
        inside = true;
        break;
      }
    }
    if (!inside) {
      regions.push([start, end]);
    }
    match = inlineRe.exec(content);
  }

  // Sort by start position for binary search.
  regions.sort((a, b) => a[0] - b[0]);
  return regions;
}

/**
 * Binary search to check if a position falls inside any code region.
 */
function isInCodeBlock(position: number, regions: [number, number][]): boolean {
  let lo = 0;
  let hi = regions.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    const [start, end] = regions[mid];
    if (position < start) {
      hi = mid - 1;
    } else if (position >= end) {
      lo = mid + 1;
    } else {
      return true;
    }
  }
  return false;
}

function processOutsideRegions(
  content: string,
  regions: [number, number][],
  process: (value: string) => string,
): string {
  if (regions.length === 0) {
    return process(content);
  }
  let out = "";
  let cursor = 0;
  for (const [start, end] of regions) {
    if (cursor < start) {
      out += process(content.slice(cursor, start));
    }
    out += content.slice(start, end);
    cursor = end;
  }
  if (cursor < content.length) {
    out += process(content.slice(cursor));
  }
  return out;
}

function processOutsideMathDelimiters(
  content: string,
  process: (value: string) => string,
): string {
  let out = "";
  let cursor = 0;
  DELIMITED_MATH_RE.lastIndex = 0;
  let match: RegExpExecArray | null = DELIMITED_MATH_RE.exec(content);
  while (match !== null) {
    if (cursor < match.index) {
      out += process(content.slice(cursor, match.index));
    }
    out += match[0];
    cursor = match.index + match[0].length;
    match = DELIMITED_MATH_RE.exec(content);
  }
  if (cursor < content.length) {
    out += process(content.slice(cursor));
  }
  return out;
}

function normalizeBackslashMathDelimiters(content: string): string {
  return content
    .replace(BACKSLASH_DISPLAY_MATH_RE, (_match, body: string) => {
      const trimmed = body.trim();
      if (!looksLikeBareLatexMath(trimmed)) {
        return _match;
      }
      return `$$\n${trimmed}\n$$`;
    })
    .replace(BACKSLASH_INLINE_MATH_RE, (_match, body: string) => {
      const trimmed = body.trim();
      if (!looksLikeBareLatexMath(trimmed)) {
        return _match;
      }
      return `$${trimmed}$`;
    });
}

function looksLikeBareLatexMath(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  if (URL_IN_TEXT_RE.test(trimmed)) {
    return false;
  }
  if (LATEX_COMMAND_RE.test(trimmed)) {
    return (
      BARE_LATEX_MATH_CHAR_RE.test(trimmed) || RELATION_COMMAND_RE.test(trimmed)
    );
  }
  if (
    SUBSCRIPT_OR_SUPERSCRIPT_RE.test(trimmed) ||
    UNICODE_MATH_SIGNAL_RE.test(trimmed)
  ) {
    return hasMathStructure(trimmed) && !looksLikeMostlyProse(trimmed);
  }
  if (COMPACT_EQUATION_RE.test(trimmed) || FUNCTION_EQUATION_RE.test(trimmed)) {
    return !looksLikeMostlyProse(trimmed);
  }
  return (
    PLAIN_FUNCTION_MATH_RE.test(trimmed) &&
    COMPACT_OPERATOR_CHAIN_RE.test(trimmed) &&
    !looksLikeMostlyProse(trimmed)
  );
}

function hasBareMathSignal(value: string): boolean {
  return (
    ANY_LATEX_COMMAND_RE.test(value) ||
    SUBSCRIPT_OR_SUPERSCRIPT_RE.test(value) ||
    UNICODE_MATH_SIGNAL_RE.test(value) ||
    COMPACT_EQUATION_RE.test(value) ||
    FUNCTION_EQUATION_RE.test(value)
  );
}

function hasMathStructure(value: string): boolean {
  return (
    BARE_LATEX_MATH_CHAR_RE.test(value) ||
    COMPACT_OPERATOR_CHAIN_RE.test(value) ||
    PLAIN_FUNCTION_MATH_RE.test(value)
  );
}

function looksLikeMostlyProse(value: string): boolean {
  const words = value.match(WORD_RE) ?? [];
  if (words.length <= MAX_PROSE_WORDS_IN_BARE_MATH) {
    return false;
  }
  return PROSE_WORD_RE.test(value);
}

function hasOddUnescapedDollars(value: string): boolean {
  UNESCAPED_DOLLAR_GLOBAL_RE.lastIndex = 0;
  let count = 0;
  while (UNESCAPED_DOLLAR_GLOBAL_RE.exec(value) !== null) {
    count += 1;
  }
  return count % 2 === 1;
}

function closeUnbalancedInlineMath(value: string): string {
  if (!(hasOddUnescapedDollars(value) && hasBareMathSignal(value))) {
    return value;
  }

  const trailing = value.match(TRAILING_SPACE_RE)?.[0] ?? "";
  const body = value.slice(0, value.length - trailing.length);
  return `${body}$${trailing}`;
}

function normalizeTableVerticalBars(value: string): string {
  let nextLeft = true;
  return value
    .replace(/\\(bigl|Bigl|biggl|Biggl)\|/g, "\\$1\\lvert ")
    .replace(/\\(bigr|Bigr|biggr|Biggr)\|/g, "\\$1\\rvert ")
    .replace(/\\\|/g, "\\vert ")
    .replace(/(?<!\\)\|/g, () => {
      const replacement = nextLeft ? "\\lvert " : "\\rvert ";
      nextLeft = !nextLeft;
      return replacement;
    });
}

function normalizeBareLatexBody(
  value: string,
  options: { tableCell?: boolean } = {},
): string {
  const withoutDanglingDelimiters = value.replace(
    DANGLING_DELIMITER_SIZE_RE,
    "",
  );
  return options.tableCell
    ? normalizeTableVerticalBars(withoutDanglingDelimiters)
    : withoutDanglingDelimiters;
}

function wrapSplitBareLatexBody(
  body: string,
  options: { tableCell?: boolean } = {},
): string | null {
  const split = body.match(FORMULA_CONNECTOR_SPLIT_RE);
  if (!split?.index) {
    return null;
  }

  const connector = split[1];
  const left = body.slice(0, split.index);
  const right = body.slice(split.index + connector.length);
  if (!(looksLikeBareLatexMath(left) && looksLikeBareLatexMath(right))) {
    return null;
  }

  return `${wrapInlineBareLatex(left, options)}${connector}${wrapInlineBareLatex(right, options)}`;
}

function wrapInlineBareLatex(
  value: string,
  options: { tableCell?: boolean } = {},
): string {
  const balancedValue = closeUnbalancedInlineMath(value);
  if (balancedValue !== value) {
    return balancedValue;
  }
  const trimmed = value.trim();
  if (!(trimmed && looksLikeBareLatexMath(trimmed))) {
    return value;
  }
  const leading = value.match(LEADING_SPACE_RE)?.[0] ?? "";
  const trailing = value.match(TRAILING_SPACE_RE)?.[0] ?? "";
  const body = normalizeBareLatexBody(
    value.slice(leading.length, value.length - trailing.length),
    options,
  );
  const splitBody = wrapSplitBareLatexBody(body, options);
  if (splitBody !== null) {
    return `${leading}${splitBody}${trailing}`;
  }
  if (
    body.startsWith("$") ||
    body.startsWith("\\(") ||
    body.startsWith("\\[") ||
    body.startsWith("\\]")
  ) {
    return value;
  }
  return `${leading}$${body}$${trailing}`;
}

function shouldWrapParenthesizedLatex(body: string): boolean {
  const trimmed = body.trim();
  if (!looksLikeBareLatexMath(trimmed)) {
    return false;
  }
  if (MATH_LEADING_BODY_RE.test(trimmed)) {
    return true;
  }
  if (!WHITESPACE_RE.test(trimmed)) {
    return true;
  }
  return (
    !PROSE_WORD_RE.test(trimmed) &&
    (MATH_OPERATOR_CHAR_RE.test(trimmed) ||
      RELATION_COMMAND_RE.test(trimmed) ||
      UNICODE_MATH_SIGNAL_RE.test(trimmed))
  );
}

function shouldSkipParenthesizedBody(
  content: string,
  openIndex: number,
): boolean {
  const previous = content
    .slice(Math.max(0, openIndex - 8), openIndex)
    .trimEnd();
  const immediatePrevious = content[openIndex - 1] ?? "";
  return (
    (immediatePrevious !== "" &&
      !WHITESPACE_RE.test(immediatePrevious) &&
      MATH_IDENTIFIER_SUFFIX_RE.test(immediatePrevious)) ||
    previous.endsWith("/") ||
    previous.endsWith("\\Bigl") ||
    previous.endsWith("\\bigl") ||
    previous.endsWith("\\left")
  );
}

function findClosingParenthesis(content: string, openIndex: number): number {
  let depth = 0;
  for (let i = openIndex; i < content.length; i++) {
    const char = content[i];
    if (char === "\\") {
      i += 1;
      continue;
    }
    if (char === "(") {
      depth += 1;
      continue;
    }
    if (char !== ")") {
      continue;
    }
    depth -= 1;
    if (depth === 0) {
      return i;
    }
  }
  return -1;
}

function wrapParenthesizedBareLatex(
  content: string,
  options: { tableCell?: boolean } = {},
): string {
  let out = "";
  let cursor = 0;

  while (cursor < content.length) {
    const openIndex = content.indexOf("(", cursor);
    if (openIndex < 0) {
      out += content.slice(cursor);
      break;
    }
    const closeIndex = findClosingParenthesis(content, openIndex);
    if (closeIndex < 0) {
      out += content.slice(cursor);
      break;
    }
    if (shouldSkipParenthesizedBody(content, openIndex)) {
      out += content.slice(cursor, closeIndex + 1);
      cursor = closeIndex + 1;
      continue;
    }

    const body = content.slice(openIndex + 1, closeIndex);
    out += content.slice(cursor, openIndex + 1);
    if (shouldWrapParenthesizedLatex(body)) {
      out += wrapInlineBareLatex(body, options);
    } else {
      out += body.includes("(")
        ? wrapParenthesizedBareLatex(body, options)
        : body;
    }
    out += ")";
    cursor = closeIndex + 1;
  }

  return out;
}

function isSeparatorPipe(line: string, index: number): boolean {
  if (line[index] !== "|") {
    return false;
  }
  if (line[index - 1] === "\\") {
    return false;
  }
  if (index === 0 || index === line.length - 1) {
    return true;
  }
  return (
    WHITESPACE_RE.test(line[index - 1] ?? "") &&
    WHITESPACE_RE.test(line[index + 1] ?? "")
  );
}

function protectMathPipesInTableLine(line: string): string {
  let nextLeft = true;
  let out = "";
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char !== "|" || isSeparatorPipe(line, i)) {
      out += char;
      continue;
    }
    out += nextLeft ? "\\lvert " : "\\rvert ";
    nextLeft = !nextLeft;
  }
  return out;
}

function isSpacedMarkdownTableLine(line: string): boolean {
  return (
    hasBareMathSignal(line) &&
    SPACED_TABLE_SEPARATOR_RE.test(line) &&
    !MARKDOWN_TABLE_SEPARATOR_RE.test(line.trim())
  );
}

function splitTableLine(line: string): string[] {
  return line.split(TABLE_LINE_SPLIT_RE);
}

function splitCellChrome(part: string): {
  body: string;
  leading: string;
  trailing: string;
} {
  const leading = part.match(TABLE_CELL_LEADING_RE)?.[0] ?? "";
  let body = part.slice(leading.length);
  const trailing = body.match(TABLE_CELL_TRAILING_RE)?.[0] ?? "";
  if (trailing) {
    body = body.slice(0, body.length - trailing.length);
  }
  return { body, leading, trailing };
}

function shouldWrapWholeTableCell(body: string): boolean {
  const trimmed = body.trim();
  if (!looksLikeBareLatexMath(trimmed)) {
    return false;
  }
  return (
    MATH_LEADING_BODY_RE.test(trimmed) ||
    !PROSE_WORD_RE.test(trimmed) ||
    TABLE_CELL_DISPLAYSTYLE_RE.test(trimmed)
  );
}

function wrapTableCell(part: string): string {
  if (!hasBareMathSignal(part)) {
    return part;
  }

  const { body, leading, trailing } = splitCellChrome(part);
  const closedBody = closeUnbalancedInlineMath(body);
  const wrappedBody = shouldWrapWholeTableCell(closedBody)
    ? wrapInlineBareLatex(closedBody, { tableCell: true })
    : wrapBareLatexSegments(closedBody, { tableCell: true });
  return `${leading}${wrappedBody}${trailing}`;
}

function wrapSpacedMarkdownTableLines(content: string): string {
  return content
    .split(NEWLINE_SPLIT_RE)
    .map((part) => {
      if (part === "\n" || !isSpacedMarkdownTableLine(part)) {
        return part;
      }

      const protectedLine = protectMathPipesInTableLine(part);
      return splitTableLine(protectedLine)
        .map((cellOrSeparator, index) =>
          index % 2 === 1 ? cellOrSeparator : wrapTableCell(cellOrSeparator),
        )
        .join("");
    })
    .join("");
}

function normalizeOrphanDisplayClosers(content: string): string {
  return content
    .replace(
      ORPHAN_DISPLAY_CLOSER_RE,
      (match, prefix: string, body: string) => {
        if (!looksLikeBareLatexMath(body)) {
          return match;
        }
        return `${prefix}$$\n${normalizeBareLatexBody(body.trim())}\n$$`;
      },
    )
    .replace(DOUBLE_PIPE_DISPLAY_RE, () => "$$\n\n");
}

function wrapWrappableCommandExpressions(content: string): string {
  return content.replace(WRAPPABLE_COMMANDS_WITH_ARGUMENT_RE, (match) =>
    looksLikeBareLatexMath(match) ? wrapInlineBareLatex(match) : match,
  );
}

function wrapBareLatexSegments(
  content: string,
  options: { tableCell?: boolean } = {},
): string {
  const normalizedDelimiters = normalizeBackslashMathDelimiters(content);

  const withDisplayBlocks = processOutsideMathDelimiters(
    normalizedDelimiters,
    (segment) =>
      segment.replace(
        BRACKETED_BARE_LATEX_LINE_RE,
        (match, prefix: string, indent: string, body: string) => {
          if (!looksLikeBareLatexMath(body)) {
            return match;
          }
          return `${prefix}${indent}$$\n${body.trim()}\n$$`;
        },
      ),
  );

  const withCommandExpressions = processOutsideMathDelimiters(
    withDisplayBlocks,
    wrapWrappableCommandExpressions,
  );

  const withParentheses = processOutsideMathDelimiters(
    withCommandExpressions,
    (segment) => wrapParenthesizedBareLatex(segment, options),
  );

  return processOutsideMathDelimiters(withParentheses, (segment) =>
    segment.replace(
      SENTENCE_BARE_LATEX_RE,
      (match, prefix: string, body: string) => {
        if (!looksLikeBareLatexMath(body)) {
          return match;
        }
        return `${prefix}${wrapInlineBareLatex(body, options)}`;
      },
    ),
  );
}

function wrapBareLaTeX(content: string): string {
  if (!hasBareMathSignal(content)) {
    return content;
  }
  const normalizedDisplayClosers = normalizeOrphanDisplayClosers(content);
  const withTableRows = wrapSpacedMarkdownTableLines(normalizedDisplayClosers);
  return wrapBareLatexSegments(withTableRows);
}

function escapeCurrencyDollars(content: string): string {
  const codeRegions = findCodeBlockRegions(content);
  return content.replace(CURRENCY_REGEX, (match, offset) => {
    if (isInCodeBlock(offset, codeRegions)) {
      return match;
    }
    if (hasInlineMathCloser(content, offset)) {
      return match;
    }
    return `\\${match}`;
  });
}

/** A whitespace-free token that looks purely like currency, e.g. `5`, `1,000`, `5.99`, `100K`, `3.5M`. */
const CURRENCY_BODY_RE = /^\d+(?:,\d{3})*(?:\.\d+)?[KMBkmb]?$/;

/** Body characters that almost always indicate real LaTeX. */
const LATEX_CHAR_RE = /[\\^_{}]/;

/**
 * Operators that strongly suggest math. Omits `^` and `_` since
 * `LATEX_CHAR_RE` short-circuits on those before this regex runs.
 */
const MATH_OP_RE = /[=+\-<>/*]/;

/**
 * Trailing chars stripped before the currency check: prose punctuation
 * plus `-` and `/` from compact ranges like `$5-$10`; without them the
 * body `5-` or `5/` would slip through the single-token math shortcut.
 */
const TRAIL_PUNCT_RE = /[.,;:!?\-/]+$/;

/**
 * A standalone single-letter variable, not part of a longer word, so
 * prose like "5 to attend" isn't misread as math with variable `t`.
 */
const LONE_LETTER_RE = /(?<![a-zA-Z])[a-zA-Z](?![a-zA-Z])/;

/**
 * Numeric or single-letter operands joined by math operators (optional
 * whitespace): `2 + 2`, `100 < 200`, `1,000 - 500`, `x + y`. Recognises
 * numeric-only expressions like `$2 + 2$` without a lone variable token.
 */
const SIMPLE_MATH_RE =
  /^(?:\d+(?:,\d{3})*(?:\.\d+)?|[a-zA-Z])(?:\s*[=+\-<>/*]\s*(?:\d+(?:,\d{3})*(?:\.\d+)?|[a-zA-Z]))+$/;

/**
 * True if the substring between two `$` delimiters looks like LaTeX
 * rather than prose between two currency tokens.
 *
 * Rule of thumb:
 *   - `$30^\circ$`  -> math (LaTeX chars)
 *   - `$x$`         -> math (single non-currency token)
 *   - `$90 - x$`    -> math (math op + lone variable)
 *   - `$5 to $10`   -> NOT math (multi-token prose, no math op)
 *   - `$5, $10`     -> NOT math (currency-like token + trailing punct)
 *   - `$1,000$`     -> NOT math (single currency-like token)
 */
function looksLikeMathBody(body: string): boolean {
  if (LATEX_CHAR_RE.test(body)) {
    return true;
  }
  const trimmed = body.trim().replace(TRAIL_PUNCT_RE, "");
  if (!trimmed) {
    return false;
  }
  if (CURRENCY_BODY_RE.test(trimmed)) {
    return false;
  }
  // Numeric-only operator forms: `2 + 2`, `100 < 200`, `1,000 - 500`.
  // Recognised without requiring a lone-variable letter.
  if (SIMPLE_MATH_RE.test(trimmed)) {
    return true;
  }
  if (!WHITESPACE_RE.test(trimmed)) {
    return true;
  }
  if (!MATH_OP_RE.test(trimmed)) {
    return false;
  }
  return LONE_LETTER_RE.test(trimmed);
}

function isBoldWrappedMath(
  content: string,
  openIndex: number,
  closeIndex: number,
): boolean {
  if (openIndex < 2) {
    return false;
  }
  const wrapper = content[openIndex - 1];
  return (
    (wrapper === "*" || wrapper === "_") &&
    content[openIndex - 2] === wrapper &&
    content[closeIndex + 1] === wrapper &&
    content[closeIndex + 2] === wrapper
  );
}

function isInlineMathCloserCandidate(content: string, index: number): boolean {
  return (
    content[index] === "$" &&
    content[index - 1] !== "\\" &&
    content[index + 1] !== "$" &&
    !DIGIT_RE.test(content[index + 1] ?? "")
  );
}

/**
 * True if the `$` at `offset` opens a balanced inline math span (`$...$`)
 * on the same line. The closer must be unescaped, not part of `$$`, and
 * within 200 chars. The body must look like LaTeX so we don't pair two
 * currency tokens on a line (e.g. "$5 to $10"). Bold-wrapped spans
 * (`**$X$**`, `__$X$__`) are always math: LLMs use that for "bold math"
 * and the heuristic would otherwise reject prose-shaped bodies like "90 - x".
 */
function hasInlineMathCloser(content: string, offset: number): boolean {
  const limit = Math.min(content.length, offset + 1 + MAX_INLINE_MATH_SPAN);
  for (let i = offset + 1; i < limit; i++) {
    const c = content[i];
    if (c === "\n") {
      return false;
    }
    if (c !== "$" || content[i - 1] === "\\") {
      continue;
    }
    if (content[i + 1] === "$") {
      i++;
      continue;
    }
    // A `$` followed by a digit is more likely another currency token than
    // the closer. Keep scanning so prose like `$5 + a $10 add-on` doesn't
    // pair the two currency markers as a math span.
    if (!isInlineMathCloserCandidate(content, i)) {
      continue;
    }
    if (isBoldWrappedMath(content, offset, i)) {
      return true;
    }
    return looksLikeMathBody(content.slice(offset + 1, i));
  }
  return false;
}

/**
 * Preprocess a markdown string to escape currency dollar signs so they are not
 * parsed as LaTeX math delimiters.
 *
 * - `$5` alone becomes `\$5` (currency, not math)
 * - `$\alpha$` is untouched (real LaTeX)
 * - `$30^\circ$` is untouched (LaTeX whose body starts with a digit)
 * - `**$30^\circ$**` is untouched (LaTeX wrapped in bold)
 * - `$$E = mc^2$$` is untouched (display math)
 * - Currency inside code blocks/spans is untouched
 */
export function preprocessLaTeX(content: string): string {
  const currencySafeContent = escapeCurrencyDollars(content);
  const codeRegions = findCodeBlockRegions(currencySafeContent);
  const withBareLatex = processOutsideRegions(
    currencySafeContent,
    codeRegions,
    wrapBareLaTeX,
  );
  return withBareLatex;
}
