// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { MultiSelector } from "@astryxdesign/core/MultiSelector";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Table } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { TextInput } from "@astryxdesign/core/TextInput";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type DocumentRow = { id: string; filename: string; word_count: number; metadata: { provenance: string } };
type DetectorRow = { key: string; name: string; status: string; score_semantics?: string };
type ResultRow = { id: string; document_id: string; filename: string | null; detector_name?: string; output: { score?: number | null; label?: string | null; error?: { message?: string } | null; score_semantics?: string; device?: string; turnitin?: { ai_writing?: { raw?: string; state?: string }; similarity?: { raw?: string | null; state?: string } } } ; error?: { message?: string } | null };
type ExperimentRow = {
  id: string; name: string; status: string; research_question: string; hypothesis: string;
  protocol: { classification_rule: string | Record<string, unknown>; seed: number; protocol_version: string; document_snapshot: { id: string; filename: string; sha256: string }[]; detector_snapshot: { key: string; revision: string }[]; conditions: Record<string, unknown> };
  progress: { completed: number; total: number; failures: number };
  interruption_reason: string | null; results: ResultRow[];
};
type Option = { value: string; label: string };
type AnalysisMetricRow = Record<string, unknown> & { id: string; detector: string; metric: string; estimate: string; interval: string; n: number };
type AnalysisSubgroupRow = Record<string, unknown> & { id: string; detector: string; subgroup: string; value: string; n: number; reliability: string; estimates: string };
type AnalysisComparisonRow = Record<string, unknown> & { id: string; pair: string; n: number; kappa: string; spearman: string; mcnemar: string; aurocDifference: string };
type AnalysisResponse = {
  detectors?: { detector: string; n: number; metrics: Record<string, unknown>; confidence_intervals?: Record<string, { lower: number; upper: number }>; reason?: string;
    subgroups?: Record<string, { value: string; n: number; unreliable: boolean; metrics: Record<string, unknown>; confidence_intervals?: Record<string, { lower: number; upper: number }> }[]> }[];
  comparisons?: { first: string; second: string; n: number; agreement_kappa: number | null; spearman: number | null; mcnemar_p_exact: number; auroc_difference_first_minus_second: number | null; auroc_difference_ci?: { lower: number; upper: number } }[];
  note?: string;
};
const metricOptions: Option[] = ["accuracy", "precision", "recall", "specificity", "f1", "fpr", "fnr", "auroc", "auprc", "cohen_kappa", "confusion_matrix", "calibration", "ece"].map((value) => ({ value, label: value }));
const provenanceOptions: Option[] = ["HUMAN", "AI_GENERATED", "AI_ASSISTED"].map((value) => ({ value, label: value.replaceAll("_", " ") }));

export default function ExperimentsPage() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [detectors, setDetectors] = useState<DetectorRow[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRow[]>([]);
  const [name, setName] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("RQ1");
  const [hypothesis, setHypothesis] = useState("");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [detectorKeys, setDetectorKeys] = useState<string[]>([]);
  const [positiveProvenance, setPositiveProvenance] = useState<string[]>(["AI_GENERATED"]);
  const [negativeProvenance, setNegativeProvenance] = useState<string[]>(["HUMAN"]);
  const [direction, setDirection] = useState("higher");
  const [thresholds, setThresholds] = useState<Record<string, string>>({});
  const [metrics, setMetrics] = useState<string[]>(["auroc"]);
  const [analyses, setAnalyses] = useState<Record<string, AnalysisResponse>>({});
  const [transformationsJson, setTransformationsJson] = useState("[]");
  const [seed, setSeed] = useState("0");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [documentResponse, detectorResponse, experimentResponse] = await Promise.all([
      fetch(`${API}/api/documents`), fetch(`${API}/api/detectors`), fetch(`${API}/api/experiments`),
    ]);
    if (!documentResponse.ok || !detectorResponse.ok || !experimentResponse.ok) throw new Error("Could not load experiment workspace data.");
    setDocuments(await documentResponse.json() as DocumentRow[]);
    setDetectors(await detectorResponse.json() as DetectorRow[]);
    setExperiments(await experimentResponse.json() as ExperimentRow[]);
  }, []);

  useEffect(() => {
    void refresh().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Could not load experiment data."));
    const timer = window.setInterval(() => { void refresh().catch(() => undefined); }, 2000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function createExperiment() {
    setBusy(true); setNotice("");
    try {
      const transformations: unknown = JSON.parse(transformationsJson);
      if (!Array.isArray(transformations)) throw new Error("Recorded transformations must be a JSON array.");
      const response = await fetch(`${API}/api/experiments`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name, research_question: researchQuestion, hypothesis, document_ids: documentIds,
          detector_keys: detectorKeys, classification_rule: {
            version: "m6.1", positive_provenance: positiveProvenance, negative_provenance: negativeProvenance,
            detectors: Object.fromEntries(detectorKeys.map((key) => [key, { direction, threshold: Number(thresholds[key]) }])),
          },
          metrics,
          conditions: { transformations }, seed: Number(seed), protocol_version: "m6.1",
        }),
      });
      const body = await response.json() as { detail?: string | { message?: string }; id?: string };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? JSON.stringify(body.detail));
      setNotice("Draft saved with a frozen dataset and detector snapshot. Review the rule, then queue the run below.");
      setName(""); setHypothesis(""); setMetrics(["auroc"]); setTransformationsJson("[]"); setDocumentIds([]); setDetectorKeys([]);
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not create experiment."); }
    finally { setBusy(false); }
  }

  async function analyze(id: string) {
    setBusy(true); setNotice("");
    try {
      const response = await fetch(`${API}/api/analysis/experiments/${id}`);
      const body = await response.json() as AnalysisResponse & { detail?: string | { message?: string } };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? JSON.stringify(body.detail));
      setAnalyses((current) => ({ ...current, [id]: body }));
      setNotice("Analysis loaded from persisted experiment results.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not analyze this experiment."); }
    finally { setBusy(false); }
  }

  async function action(id: string, operation: "run" | "cancel" | "resume" | "duplicate") {
    setBusy(true); setNotice("");
    try {
      const response = await fetch(`${API}/api/experiments/${id}/${operation}`, { method: "POST" });
      const body = await response.json() as { detail?: string | { message?: string }; name?: string };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? JSON.stringify(body.detail));
      setNotice(operation === "duplicate" ? `Created draft: ${body.name ?? "experiment copy"}.` : `Experiment ${operation === "cancel" ? "cancellation requested" : `${operation} request accepted`}.`);
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : `Could not ${operation} experiment.`); }
    finally { setBusy(false); }
  }

  const docOptions: Option[] = documents.map((doc) => ({ value: doc.id, label: `${doc.filename} · ${doc.metadata.provenance} · ${doc.word_count} words` }));
  const detectorOptions: Option[] = detectors.map((detector) => ({ value: detector.key, label: `${detector.name} · ${detector.status.replaceAll("_", " ")}` }));
  const detectorSemantics = Object.fromEntries(detectors.map((detector) => [detector.key, detector.score_semantics ?? "unknown"]));

  return <Section width="100%" paddingInline={5} paddingBlock={6}><Stack hAlign="center"><Stack width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / EXPERIMENTS</Text><Heading level={1} type="display-1">Experiments</Heading><Text as="p" color="secondary">Freeze provenance labels, score direction, and threshold before running. Analysis uses the stored results and reports sample sizes and uncertainty.</Text></Stack>
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    <Section variant="section" padding={5}><Stack gap={4}>
      <Heading level={2}>Create a draft</Heading>
      <TextInput label="Experiment name" value={name} onChange={setName} isRequired placeholder="A descriptive name" />
      <Selector label="Research question" value={researchQuestion} onChange={setResearchQuestion} options={["RQ1", "RQ2", "RQ3", "RQ4", "RQ5"].map((value) => ({ value, label: value }))} />
      <TextArea label="Hypothesis" value={hypothesis} onChange={setHypothesis} isRequired placeholder="State the hypothesis before reviewing detector results." />
      <MultiSelector label="Documents" value={documentIds} onChange={setDocumentIds} options={docOptions} placeholder="Select documents" hasSearch emptyText="No stored documents are available." />
      <MultiSelector label="Detectors" value={detectorKeys} onChange={setDetectorKeys} options={detectorOptions} placeholder="Select detectors" emptyText="No detectors are registered." />
      <MultiSelector label="Positive class provenance" value={positiveProvenance} onChange={setPositiveProvenance} options={provenanceOptions} placeholder="Select positive labels" />
      <MultiSelector label="Negative class provenance" value={negativeProvenance} onChange={setNegativeProvenance} options={provenanceOptions} placeholder="Select negative labels" />
      <Selector label="Positive score direction" value={direction} onChange={setDirection} options={[{ value: "higher", label: "Higher score means positive" }, { value: "lower", label: "Lower score means positive" }]} />
      {detectorKeys.map((key) => <TextInput key={key} label={`Threshold · ${key} (${detectorSemantics[key]})`} value={thresholds[key] ?? ""} onChange={(value) => setThresholds((current) => ({ ...current, [key]: value }))} inputMode="decimal" isRequired description="Use the detector's native score scale. Do not tune on the evaluation set." />)}
      <MultiSelector label="Metrics to calculate" value={metrics} onChange={setMetrics} options={metricOptions} placeholder="Select metrics" />
      <TextInput label="Random seed" value={seed} onChange={setSeed} inputMode="numeric" />
      <TextArea label="Transformations to record (JSON array)" value={transformationsJson} onChange={setTransformationsJson} description="Recorded in the frozen protocol; transformations are not applied in this milestone." />
      <Button label={busy ? "Saving…" : "Create draft"} variant="primary" isDisabled={busy || !name.trim() || !hypothesis.trim() || positiveProvenance.length === 0 || negativeProvenance.length === 0 || positiveProvenance.some((value) => negativeProvenance.includes(value)) || metrics.length === 0 || detectorKeys.some((key) => thresholds[key] === undefined || !Number.isFinite(Number(thresholds[key]))) || documentIds.length === 0 || detectorKeys.length === 0 || !Number.isInteger(Number(seed))} onClick={() => void createExperiment()} />
    </Stack></Section>
    <Stack gap={4}><Heading level={2}>Saved experiments</Heading>
      {experiments.length === 0 ? <Text as="p" color="secondary">No experiments yet. Create a draft with a classification rule to begin.</Text> : experiments.map((experiment) => {
        const value = experiment.progress.total ? experiment.progress.completed : 0;
        const variant = experiment.status === "COMPLETED" ? "success" : experiment.status === "FAILED" ? "error" : experiment.status === "PARTIALLY_COMPLETED" ? "warning" : "accent";
        return <Section key={experiment.id} variant="section" padding={4}><Stack gap={3}>
          <Stack direction="horizontal" align="center" gap={3} wrap="wrap"><StatusDot variant={variant} label={experiment.status.replaceAll("_", " ")} /><Heading level={3}>{experiment.name}</Heading></Stack>
          <Text as="p">{experiment.research_question} · {experiment.progress.completed}/{experiment.progress.total} pairs · {experiment.progress.failures} failures</Text>
          {experiment.progress.total > 0 && <ProgressBar label={`Progress for ${experiment.name}`} value={value} max={experiment.progress.total} hasValueLabel />}
          <Text as="p" type="supporting">Frozen protocol · seed {experiment.protocol.seed} · protocol {experiment.protocol.protocol_version}</Text>
          {experiment.interruption_reason && <Text as="p" color="accent">{experiment.interruption_reason}</Text>}
          <Stack direction="horizontal" gap={2} wrap="wrap">
            {experiment.status === "DRAFT" && <Button label="Run experiment" variant="primary" isDisabled={busy} onClick={() => void action(experiment.id, "run")} />}
            {(experiment.status === "QUEUED" || experiment.status === "RUNNING") && <Button label="Cancel" variant="secondary" isDisabled={busy} onClick={() => void action(experiment.id, "cancel")} />}
            {experiment.status === "PARTIALLY_COMPLETED" && <Button label="Resume missing pairs" variant="primary" isDisabled={busy} onClick={() => void action(experiment.id, "resume")} />}
            {(experiment.status === "COMPLETED" || experiment.status === "PARTIALLY_COMPLETED") && <Button label="Analyze results" variant="secondary" isDisabled={busy} onClick={() => void analyze(experiment.id)} />}
            <Button label="Duplicate as draft" variant="secondary" isDisabled={busy} onClick={() => void action(experiment.id, "duplicate")} />
          </Stack>
          {experiment.results.length > 0 && <Stack gap={2}><Heading level={4}>Per-item results</Heading>{experiment.results.map((result) => <Text key={result.id} as="p" type="supporting">{result.filename ?? result.document_id} · {result.detector_name ? `${result.detector_name} · ` : ""}{result.output.turnitin ? `AI writing ${result.output.turnitin.ai_writing?.raw} · ${result.output.turnitin.ai_writing?.state?.replaceAll("_", " ")} · similarity ${result.output.turnitin.similarity?.raw ?? "not displayed"} · percentage semantics` : result.error ? `failed: ${result.error.message ?? "unknown error"}` : `score ${result.output.score ?? "unavailable"} (${result.output.score_semantics ?? "unknown"})${result.output.label ? ` · ${result.output.label}` : ""}`}</Text>)}</Stack>}
          {analyses[experiment.id] && <Stack gap={3}><Heading level={4}>Statistics</Heading><Table<AnalysisMetricRow> idKey="id" density="compact" dividers="rows" data={(analyses[experiment.id].detectors ?? []).flatMap((row) => {
            const entries = Object.entries(row.metrics);
            if (entries.length === 0) return [{ id: `${row.detector}-none`, detector: row.detector, metric: "Not estimable", estimate: row.reason ?? "No metric could be estimated", interval: "—", n: row.n }];
            return entries.map(([metric, value]) => { const interval = row.confidence_intervals?.[metric]; return { id: `${row.detector}-${metric}`, detector: row.detector, metric, estimate: JSON.stringify(value), interval: interval ? `${interval.lower.toFixed(4)} to ${interval.upper.toFixed(4)}` : "—", n: row.n }; });
          })} columns={[{ key: "detector", header: "Detector" }, { key: "metric", header: "Metric" }, { key: "estimate", header: "Estimate" }, { key: "interval", header: "95% CI" }, { key: "n", header: "n" }]} />
          <Heading level={5}>Subgroups</Heading><Table<AnalysisSubgroupRow> idKey="id" density="compact" dividers="rows" data={(analyses[experiment.id].detectors ?? []).flatMap((row) => Object.entries(row.subgroups ?? {}).flatMap(([group, cells]) => cells.map((cell) => ({
            id: `${row.detector}-${group}-${cell.value}`, detector: row.detector, subgroup: group, value: cell.value, n: cell.n,
            reliability: cell.unreliable ? "Unreliable · low n" : "n meets floor",
            estimates: Object.entries(cell.metrics).map(([metric, value]) => { const ci = cell.confidence_intervals?.[metric]; return ci ? `${metric}: ${JSON.stringify(value)} (${ci.lower.toFixed(4)} to ${ci.upper.toFixed(4)})` : `${metric}: ${JSON.stringify(value)}`; }).join(" · ") || "No metric estimable",
          }))))} columns={[{ key: "detector", header: "Detector" }, { key: "subgroup", header: "Grouping" }, { key: "value", header: "Group" }, { key: "n", header: "n" }, { key: "reliability", header: "Sample note" }, { key: "estimates", header: "Estimates · 95% CI" }]} />
          {(analyses[experiment.id].comparisons?.length ?? 0) > 0 && <><Heading level={5}>Detector comparisons</Heading><Table<AnalysisComparisonRow> idKey="id" density="compact" dividers="rows" data={(analyses[experiment.id].comparisons ?? []).map((row) => ({
            id: `${row.first}-${row.second}`, pair: `${row.first} / ${row.second}`, n: row.n,
            kappa: row.agreement_kappa === null ? "—" : row.agreement_kappa.toFixed(4),
            spearman: row.spearman === null ? "—" : row.spearman.toFixed(4), mcnemar: row.mcnemar_p_exact.toFixed(4),
            aurocDifference: row.auroc_difference_ci ? `${row.auroc_difference_first_minus_second?.toFixed(4)} (${row.auroc_difference_ci.lower.toFixed(4)} to ${row.auroc_difference_ci.upper.toFixed(4)})` : "Not estimable",
          }))} columns={[{ key: "pair", header: "Detector pair" }, { key: "n", header: "Paired n" }, { key: "kappa", header: "Agreement κ" }, { key: "spearman", header: "Spearman ρ" }, { key: "mcnemar", header: "Exact McNemar p" }, { key: "aurocDifference", header: "AUROC difference · 95% CI" }]} /></>}
          <Text as="p" type="supporting">{analyses[experiment.id].note}</Text></Stack>}
        </Stack></Section>;
      })}
    </Stack>
  </Stack></Stack></Section>;
}
