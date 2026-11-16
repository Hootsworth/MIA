// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { Table } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const AnalysisCharts = dynamic(() => import("./charts"), {
  ssr: false,
  loading: () => <Text as="p">Loading chart tools…</Text>,
});
type Experiment = { id: string; name: string; status: string };
type CI = { lower: number; upper: number };
type MetricValues = Record<string, unknown>;
type Metric = { detector: string; n: number; positive_n: number; negative_n: number; metrics: MetricValues; confidence_intervals: Record<string, CI>; subgroups: Record<string, { value: string; n: number; unreliable: boolean; metrics: Record<string, number | null>; confidence_intervals: Record<string, CI> }[]>; roc_curve: { false_positive_rate: number; true_positive_rate: number }[]; score_distribution: { label: string; counts: Record<string, number> }[]; observations: { document_id: string; provenance: string; score: number; word_count: number | null }[]; excluded: Record<string, number>; insufficient_classes: boolean };
type Analysis = { experiment_id: string; protocol_version: string; bootstrap_replicates: number; metrics_requested: string[]; detectors: Metric[]; comparisons: Record<string, unknown>[]; note: string };
type FlatRow = { id: string; detector: string; metric: string; estimate: string; interval: string; n: number };
type SubgroupRow = { id: string; detector: string; grouping: string; value: string; n: number; sample: string; estimates: string };

function format(value: unknown) {
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(3) : "—";
  return value == null ? "—" : String(value);
}

export default function AnalysisPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedDetector, setSelectedDetector] = useState("");
  const [grouping, setGrouping] = useState("author_language_background");
  const [notice, setNotice] = useState("Loading completed experiments…");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void fetch(`${API}/api/experiments`).then(async (response) => {
      if (!response.ok) throw new Error("Could not load experiments from MIA.");
      return await response.json() as Experiment[];
    }).then((rows) => {
      if (!active) return;
      const completed = rows.filter((row) => row.status === "COMPLETED" || row.status === "PARTIALLY_COMPLETED");
      setExperiments(completed);
      setSelectedId(completed[0]?.id ?? "");
      setNotice(completed.length ? "Choose an experiment to inspect stored analysis." : "No completed experiments are available for analysis yet.");
    }).catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Could not load experiments."));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedId) { setAnalysis(null); return; }
    let active = true;
    setBusy(true); setAnalysis(null); setNotice("Loading statistics from persisted results…");
    void fetch(`${API}/api/analysis/experiments/${selectedId}`).then(async (response) => {
      const body = await response.json() as Analysis & { detail?: string | { message?: string } };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? "This experiment does not have an analyzable M6 protocol.");
      return body;
    }).then((body) => {
      if (!active) return;
      setAnalysis(body);
      setSelectedDetector(body.detectors[0]?.detector ?? "");
      setNotice(body.detectors.length ? "Statistics loaded from stored experiment outputs." : "No detector results are available for this experiment.");
    }).catch((error: unknown) => { if (active) setNotice(error instanceof Error ? error.message : "Could not analyze this experiment."); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [selectedId]);

  const detector = analysis?.detectors.find((row) => row.detector === selectedDetector) ?? analysis?.detectors[0];
  const matrixValue = detector?.metrics.confusion_matrix;
  const confusion = typeof matrixValue === "object" && matrixValue !== null && "tn" in matrixValue
    ? matrixValue as { tn: number; fp: number; fn: number; tp: number } : null;
  const provenances = useMemo(() => [...new Set(detector?.score_distribution.flatMap((bin) => Object.keys(bin.counts)) ?? [])], [detector]);
  const groupingOptions = useMemo(() => [...new Set(analysis?.detectors.flatMap((row) => Object.keys(row.subgroups)) ?? [])], [analysis]);
  const metricRows: FlatRow[] = (analysis?.detectors ?? []).flatMap((row) => Object.entries(row.metrics).filter(([, value]) => value !== null).map(([metric, value]) => {
    const ci = row.confidence_intervals[metric];
    return { id: `${row.detector}-${metric}`, detector: row.detector, metric, estimate: format(value),
      interval: ci ? `[${format(ci.lower)}, ${format(ci.upper)}]` : "—", n: row.n };
  }));
  const subgroupRows: SubgroupRow[] = (analysis?.detectors ?? []).flatMap((row) => Object.entries(row.subgroups).flatMap(([group, cells]) => cells.map((cell) => {
    const estimates = Object.entries(cell.metrics).map(([metric, value]) => {
      const ci = cell.confidence_intervals[metric];
      return `${metric}: ${format(value)}${ci ? ` [${format(ci.lower)}, ${format(ci.upper)}]` : ""}`;
    }).join(" · ") || "No estimate";
    return { id: `${row.detector}-${group}-${cell.value}`, detector: row.detector, grouping: group, value: cell.value,
      n: cell.n, sample: cell.unreliable ? "n too small · descriptive only" : "Estimate available", estimates };
  })));
  return <Section width="100%" paddingInline={5} paddingBlock={6}><Stack hAlign="center"><Stack width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / ANALYSIS</Text><Heading level={1} type="display-1">Analysis</Heading><Text as="p" color="secondary">Read-only charts and estimates from stored detector outputs. MIA never infers provenance from scores.</Text></Stack>
    {experiments.length > 0 && <Selector label="Finished experiment" value={selectedId} onChange={setSelectedId} options={experiments.map((row) => ({ value: row.id, label: `${row.name} · ${row.status}` }))} />}
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    {busy && <Text as="p">Computing the declared analysis, including deterministic bootstrap intervals. Larger datasets can take longer.</Text>}
    {analysis && detector && <>
      <Stack direction="horizontal" gap={3} wrap="wrap">
        <Section variant="section" padding={4}><Stack gap={1}><Text type="label">Scored observations</Text><Heading level={3}>{detector.n}</Heading></Stack></Section>
        <Section variant="section" padding={4}><Stack gap={1}><Text type="label">Positive class</Text><Heading level={3}>{detector.positive_n}</Heading></Stack></Section>
        <Section variant="section" padding={4}><Stack gap={1}><Text type="label">Negative class</Text><Heading level={3}>{detector.negative_n}</Heading></Stack></Section>
      </Stack>
      {analysis.detectors.length > 1 && <Selector label="Detector" value={detector.detector} onChange={setSelectedDetector} options={analysis.detectors.map((row) => ({ value: row.detector, label: row.detector }))} />}
      {groupingOptions.length > 0 && <Selector label="Subgroup dimension for interval chart" value={grouping} onChange={setGrouping} options={groupingOptions.map((value) => ({ value, label: value.replaceAll("_", " ") }))} />}
      <AnalysisCharts detector={detector} provenances={provenances} grouping={grouping} />
      <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Predeclared-threshold confusion matrix</Heading>
        {confusion ? <Table<{ id: string; predicted: string; negative: number; positive: number }> idKey="id" density="compact" dividers="rows" data={[{ id: "actual-negative", predicted: "Actual negative", negative: confusion.tn, positive: confusion.fp }, { id: "actual-positive", predicted: "Actual positive", negative: confusion.fn, positive: confusion.tp }]} columns={[{ key: "predicted", header: "Observed class" }, { key: "negative", header: "Predicted negative" }, { key: "positive", header: "Predicted positive" }]} /> : <Text as="p">The frozen rule has no threshold, so this matrix is not computed.</Text>}
      </Stack></Section>
      <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Subgroup estimates</Heading><Text as="p" color="secondary">Intervals and sample counts are returned by the analysis API. Cells below the configured floor are marked unreliable.</Text>
        <Table<SubgroupRow> idKey="id" density="compact" dividers="rows" data={subgroupRows} columns={[{ key: "detector", header: "Detector" }, { key: "grouping", header: "Grouping" }, { key: "value", header: "Group" }, { key: "n", header: "n" }, { key: "sample", header: "Reliability" }, { key: "estimates", header: "Estimates · 95% CI" }]} />
      </Stack></Section>
      <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Metric estimates</Heading><Text as="p" color="secondary">Bootstrap resamples · {analysis.bootstrap_replicates} · protocol {analysis.protocol_version}</Text>
        <Table<FlatRow> idKey="id" density="compact" dividers="rows" data={metricRows} columns={[{ key: "detector", header: "Detector" }, { key: "metric", header: "Metric" }, { key: "estimate", header: "Estimate" }, { key: "interval", header: "95% CI" }, { key: "n", header: "n" }]} />
        {detector.excluded && Object.values(detector.excluded).some((count) => count > 0) && <Text as="p">Excluded outputs: {Object.entries(detector.excluded).map(([state, count]) => `${state}: ${count}`).join(" · ")}. These are not treated as zero.</Text>}
        <Text as="p" color="secondary">{analysis.note}</Text>
      </Stack></Section>
    </>}
  </Stack></Stack></Section>;
}
