import type { Tokens } from "./theme";

/** Shared ECharts building blocks: recessive axes, hairline grid, value-led tooltips. */
export const baseText = (t: Tokens) => ({ color: t["text-secondary"], fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif" });

export const tooltip = (t: Tokens, extra: object = {}) => ({
  trigger: "axis",
  backgroundColor: t["surface-1"],
  borderColor: t["grid"],
  borderWidth: 1,
  textStyle: { color: t["text-primary"], fontSize: 12 },
  axisPointer: { type: "line", lineStyle: { color: t["axis"], width: 1 } },
  ...extra,
});

export const legend = (t: Tokens, extra: object = {}) => ({
  top: 0,
  right: 0,
  icon: "roundRect",
  itemWidth: 14,
  itemHeight: 3,
  textStyle: { color: t["text-secondary"], fontSize: 12 },
  ...extra,
});

export const axisCommon = (t: Tokens) => ({
  axisLine: { lineStyle: { color: t["axis"] } },
  axisTick: { show: false },
  axisLabel: { color: t["text-muted"], fontSize: 11 },
  splitLine: { lineStyle: { color: t["grid"], width: 1 } },
  nameTextStyle: { color: t["text-muted"], fontSize: 11 },
});

export const xCat = (t: Tokens, data: (string | number)[], extra: object = {}) => ({
  type: "category",
  data,
  boundaryGap: false,
  ...axisCommon(t),
  splitLine: { show: false },
  ...extra,
});

export const yVal = (t: Tokens, extra: object = {}) => ({ type: "value", ...axisCommon(t), ...extra });

export const grid = (extra: object = {}) => ({ left: 44, right: 16, top: 34, bottom: 28, containLabel: false, ...extra });

/** Fan chart: P10–P90 band (10 % wash) + median line, using stacked areas. */
export function fanSeries(name: string, color: string, bands: { p10: number[]; p50: number[]; p90: number[]; p25?: number[]; p75?: number[] }, stack: string) {
  const lower = bands.p10;
  const width = bands.p90.map((v, i) => v - lower[i]);
  return [
    { name: `${name} band-lo`, type: "line", data: lower, stack, lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
    { name: `${name} P10–P90`, type: "line", data: width, stack, lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color, opacity: 0.14 }, tooltip: { show: false }, silent: true },
    { name, type: "line", data: bands.p50, symbol: "none", lineStyle: { color, width: 2 }, itemStyle: { color } },
  ];
}
