import type { Tokens } from "./theme";

/** ECharts building blocks in the Ops Room style: graph-paper grid, mono ticks, square tooltips,
 *  and direct end-of-line labels instead of legend boxes where there are four series or fewer. */
export const MONO = "IBM Plex Mono, ui-monospace, monospace";
export const COND = "Barlow Condensed, Arial Narrow, sans-serif";

export const textStyle = (t: Tokens) => ({ color: t["ink-2"], fontFamily: MONO, fontSize: 11 });

export const tooltip = (t: Tokens, extra: object = {}) => ({
  trigger: "axis",
  backgroundColor: t.panel,
  borderColor: t.ink,
  borderWidth: 1,
  borderRadius: 0,
  padding: [6, 9],
  textStyle: { color: t.ink, fontSize: 12, fontFamily: MONO },
  extraCssText: "box-shadow:none;",
  axisPointer: { type: "line", lineStyle: { color: t["ink-3"], width: 1, type: "dashed" } },
  ...extra,
});

export const legend = (t: Tokens, extra: object = {}) => ({
  top: 0,
  left: 0,
  icon: "rect",
  itemWidth: 14,
  itemHeight: 4,
  itemGap: 16,
  textStyle: { color: t["ink-2"], fontSize: 11, fontFamily: MONO },
  ...extra,
});

export const axisCommon = (t: Tokens) => ({
  axisLine: { lineStyle: { color: t.ink, width: 1 } },
  axisTick: { show: true, length: 4, lineStyle: { color: t.ink } },
  axisLabel: { color: t["ink-2"], fontSize: 10.5, fontFamily: MONO },
  splitLine: { lineStyle: { color: t.grid, width: 1 } },
  nameTextStyle: { color: t["ink-3"], fontSize: 10.5, fontFamily: MONO },
});

export const xCat = (t: Tokens, data: (string | number)[], extra: object = {}) => ({
  type: "category",
  data,
  boundaryGap: false,
  ...axisCommon(t),
  splitLine: { show: true, lineStyle: { color: t.grid, width: 1 } },
  ...extra,
});

export const yVal = (t: Tokens, extra: object = {}) => ({ type: "value", ...axisCommon(t), axisLine: { show: false }, axisTick: { show: false }, ...extra });

export const grid = (extra: object = {}) => ({ left: 44, right: 16, top: 26, bottom: 26, containLabel: false, ...extra });

/** Direct label at the end of a line series (replaces a legend entry). */
export const endLabel = (t: Tokens, text: (v: number) => string, color?: string) => ({
  show: true,
  formatter: (p: any) => text(Array.isArray(p.value) ? p.value[1] : p.value),
  color: color ?? t.ink,
  fontFamily: MONO,
  fontSize: 11,
  fontWeight: 600,
  distance: 6,
});

/** Fan chart: P10–P90 band (light wash) + median line with optional direct end label. */
export function fanSeries(name: string, color: string, bands: { p10: number[]; p50: number[]; p90: number[] }, stack: string, label?: object, dashed = false) {
  const lower = bands.p10;
  const width = bands.p90.map((v, i) => v - lower[i]);
  return [
    { name: `${name} band-lo`, type: "line", data: lower, stack, lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
    { name: `${name} P10–P90`, type: "line", data: width, stack, lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color, opacity: 0.16 }, tooltip: { show: false }, silent: true },
    { name, type: "line", data: bands.p50, symbol: "none", lineStyle: { color, width: 2, type: dashed ? [5, 4] : "solid" }, itemStyle: { color }, ...(label ? { endLabel: label } : {}) },
  ];
}
