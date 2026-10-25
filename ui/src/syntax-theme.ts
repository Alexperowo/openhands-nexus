import { getSyntaxHighlighterTheme as canvasTheme } from "../node_modules/@openhands/agent-canvas/dist/themes/syntax-highlighter-themes.js";

// Replaces Canvas's themes/syntax-highlighter-themes.js. Its dark theme (VS Code Dark+) is set
// as inline styles at 13px, and several token colours are 4–6:1 on the #1e1e1e block. Here the
// same theme keeps its hues, each colour lifted to at least 7:1 (shades calculated by Gemini),
// at the chosen text size, without dimmed or slanted tokens. Long lines wrap: at full size
// a block would otherwise scroll sideways, which is hard to follow and unreachable by keyboard.
const LIFTED: Record<string, string> = {
  "#569cd6": "#77afde",
  "#ce9178": "#d39d87",
  "#6a9955": "#8cb579",
  "#c586c0": "#ce99ca",
  "#d16969": "#df9696",
  "#808080": "#a9a9a9",
  "#db4c69": "#e990a2",
};

type Theme = Record<string, Record<string, string>>;

function readable(theme: Theme): Theme {
  return Object.fromEntries(Object.entries(theme).map(([selector, style]) => {
    const { Opacity, fontStyle, ...rest } = style;
    const lifted: Record<string, string> = { ...rest };
    if (lifted.color) lifted.color = LIFTED[lifted.color.toLowerCase()] ?? lifted.color;
    if (lifted.fontSize) lifted.fontSize = "1rem";
    if (lifted.whiteSpace === "pre") Object.assign(lifted, { whiteSpace: "pre-wrap", overflowWrap: "anywhere" });
    if (fontStyle && fontStyle !== "italic") lifted.fontStyle = fontStyle;
    return [selector, lifted];
  }));
}

const cache = new Map<string, Theme>();

export function getSyntaxHighlighterTheme(name: string) {
  const theme = canvasTheme(name) as Theme | undefined;
  if (!theme) return theme;
  if (!cache.has(name)) cache.set(name, readable(theme));
  return cache.get(name);
}
