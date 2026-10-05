import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, MarkPointComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { LabelLayout } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/lib/core";
import { MONO } from "../lib/charts";

// register only what the boards draw (keeps the chart chunk small)
echarts.use([LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
  MarkAreaComponent, MarkPointComponent, LabelLayout, CanvasRenderer]);

export function Chart({ option, height = 260, onEvents }: { option: object; height?: number; onEvents?: Record<string, (p: any) => void> }) {
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{ backgroundColor: "transparent", animationDuration: 300, textStyle: { fontFamily: MONO }, ...option }}
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
      onEvents={onEvents}
    />
  );
}
