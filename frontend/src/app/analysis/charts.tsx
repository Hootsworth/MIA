// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { Section } from "@astryxdesign/core/Section";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import type { ReactNode } from "react";
import {
  Bar, BarChart, CartesianGrid, ErrorBar, LabelList, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";

type CI = { lower: number; upper: number };
type AnalysisDetector = {
  roc_curve: { false_positive_rate: number; true_positive_rate: number }[];
  score_distribution: { label: string; counts: Record<string, number> }[];
  observations: { document_id: string; provenance: string; score: number; word_count: number | null }[];
  subgroups: Record<string, { value: string; n: number; unreliable: boolean; metrics: Record<string, number | null>; confidence_intervals: Record<string, CI> }[]>;
};
const SERIES_COLORS = ["var(--color-data-categorical-blue)", "var(--color-data-categorical-orange)",
  "var(--color-data-categorical-green)", "var(--color-data-categorical-purple)", "var(--color-data-neutral)"];

function ChartSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>{title}</Heading><Text as="p" color="secondary">{description}</Text>{children}</Stack></Section>;
}

export default function AnalysisCharts({ detector, provenances, grouping }: { detector: AnalysisDetector; provenances: string[]; grouping: string }) {
  const subgroupChart = (detector.subgroups[grouping] ?? []).flatMap((cell) => {
    const metric = Object.keys(cell.confidence_intervals)[0];
    const value = metric ? cell.metrics[metric] : null;
    const ci = metric ? cell.confidence_intervals[metric] : undefined;
    if (!metric || typeof value !== "number" || !ci) return [];
    return [{ group: cell.value, estimate: value, interval: [Math.max(0, value - ci.lower), Math.max(0, ci.upper - value)], n: cell.n, metric }];
  });
  const scoreByWordCount = detector.observations.filter((row) => row.word_count != null);

  return <Stack gap={6}>
    <ChartSection title="Score distribution by declared provenance" description="Counts are binned from stored numeric detector scores; the score scale follows the detector’s declared semantics.">
      {detector.score_distribution.length ? <ResponsiveContainer width="100%" height={300}><BarChart accessibilityLayer data={detector.score_distribution}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" /><YAxis allowDecimals={false} /><Tooltip /><Legend />{provenances.map((name, index) => <Bar key={name} dataKey={`counts.${name}`} name={name} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />)}</BarChart></ResponsiveContainer> : <Text as="p">No numeric scores to chart.</Text>}
    </ChartSection>
    <ChartSection title="Receiver operating characteristic" description="Threshold-free ROC points use the experiment’s frozen positive/negative provenance and score direction.">
      {detector.roc_curve.length ? <ResponsiveContainer width="100%" height={300}><LineChart accessibilityLayer data={detector.roc_curve}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey="false_positive_rate" domain={[0, 1]} label={{ value: "False positive rate", position: "insideBottom", offset: -4 }} /><YAxis type="number" dataKey="true_positive_rate" domain={[0, 1]} label={{ value: "True positive rate", angle: -90, position: "insideLeft" }} /><Tooltip /><ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="currentColor" strokeDasharray="4 4" /><Line dataKey="true_positive_rate" stroke="var(--color-data-categorical-blue)" dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer> : <Text as="p">ROC is unavailable until both declared classes have numeric scores.</Text>}
    </ChartSection>
    <ChartSection title="Length and score" description="Each point is one stored document output. No score is recomputed in the browser.">
      {scoreByWordCount.length ? <ResponsiveContainer width="100%" height={300}><ScatterChart accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey="word_count" name="Words" /><YAxis type="number" dataKey="score" name="Score" /><Tooltip cursor={{ strokeDasharray: "3 3" }} /><Legend />{provenances.map((name, index) => <Scatter key={name} name={name} data={scoreByWordCount.filter((row) => row.provenance === name)} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />)}</ScatterChart></ResponsiveContainer> : <Text as="p">No scored documents have word-count metadata for this chart.</Text>}
    </ChartSection>
    <ChartSection title="Subgroup estimates with confidence intervals" description="Bars use API estimates and whiskers use the API confidence intervals. Small cells are excluded from the plot and labeled below.">
      {subgroupChart.length ? <ResponsiveContainer width="100%" height={280}><BarChart accessibilityLayer data={subgroupChart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="group" /><YAxis domain={[0, 1]} /><Tooltip /><Bar dataKey="estimate" name={subgroupChart[0].metric} fill="var(--color-data-categorical-blue)"><ErrorBar dataKey="interval" direction="y" width={5} strokeWidth={1} /><LabelList dataKey="n" position="top" /></Bar></BarChart></ResponsiveContainer> : <Text as="p">No subgroup confidence intervals are available for this grouping; low-n cells remain visibly marked in the table.</Text>}
    </ChartSection>
  </Stack>;
}
