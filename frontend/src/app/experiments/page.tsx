"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { MultiSelector } from "@astryxdesign/core/MultiSelector";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { TextInput } from "@astryxdesign/core/TextInput";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type DocumentRow = { id: string; filename: string; word_count: number; metadata: { provenance: string } };
type DetectorRow = { key: string; name: string; status: string };
type ResultRow = { id: string; document_id: string; filename: string | null; output: { score?: number | null; label?: string | null; error?: { message?: string } | null; score_semantics?: string; device?: string } ; error?: { message?: string } | null };
type ExperimentRow = {
  id: string; name: string; status: string; research_question: string; hypothesis: string;
  protocol: { classification_rule: string; seed: number; protocol_version: string; document_snapshot: { id: string; filename: string; sha256: string }[]; detector_snapshot: { key: string; revision: string }[]; conditions: Record<string, unknown> };
  progress: { completed: number; total: number; failures: number };
  interruption_reason: string | null; results: ResultRow[];
};
type Option = { value: string; label: string };

export default function ExperimentsPage() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [detectors, setDetectors] = useState<DetectorRow[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRow[]>([]);
  const [name, setName] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("RQ1");
  const [hypothesis, setHypothesis] = useState("");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [detectorKeys, setDetectorKeys] = useState<string[]>([]);
  const [classificationRule, setClassificationRule] = useState("");
  const [metrics, setMetrics] = useState("");
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
          detector_keys: detectorKeys, classification_rule: classificationRule,
          metrics: metrics.split(",").map((value) => value.trim()).filter(Boolean),
          conditions: { transformations }, seed: Number(seed), protocol_version: "m5.1",
        }),
      });
      const body = await response.json() as { detail?: string | { message?: string }; id?: string };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? JSON.stringify(body.detail));
      setNotice("Draft saved with a frozen dataset and detector snapshot. Review the rule, then queue the run below.");
      setName(""); setHypothesis(""); setClassificationRule(""); setMetrics(""); setTransformationsJson("[]"); setDocumentIds([]); setDetectorKeys([]);
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not create experiment."); }
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

  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}><Stack hAlign="center"><Stack as="main" width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / EXPERIMENTS</Text><Heading level={1} type="display-1">Experiments</Heading><Text as="p" color="secondary">Freeze the research protocol before running detector-document pairs. Scores are stored as observed outputs; this milestone does not compute statistics.</Text></Stack>
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    <Section variant="section" padding={5}><Stack gap={4}>
      <Heading level={2}>Create a draft</Heading>
      <TextInput label="Experiment name" value={name} onChange={setName} isRequired placeholder="A descriptive name" />
      <Selector label="Research question" value={researchQuestion} onChange={setResearchQuestion} options={["RQ1", "RQ2", "RQ3", "RQ4", "RQ5"].map((value) => ({ value, label: value }))} />
      <TextArea label="Hypothesis" value={hypothesis} onChange={setHypothesis} isRequired placeholder="State the hypothesis before reviewing detector results." />
      <MultiSelector label="Documents" value={documentIds} onChange={setDocumentIds} options={docOptions} placeholder="Select documents" hasSearch emptyText="No stored documents are available." />
      <MultiSelector label="Detectors" value={detectorKeys} onChange={setDetectorKeys} options={detectorOptions} placeholder="Select detectors" emptyText="No detectors are registered." />
      <TextInput label="Predeclared classification rule" value={classificationRule} onChange={setClassificationRule} isRequired description="Required before queueing. Record the intended interpretation explicitly; binary metrics are not computed in this milestone." placeholder="Describe the rule and any threshold before the run" />
      <TextInput label="Metrics to evaluate later" value={metrics} onChange={setMetrics} isOptional description="Comma-separated plan only; no metrics are calculated here." placeholder="e.g. AUROC, FPR" />
      <TextInput label="Random seed" value={seed} onChange={setSeed} inputMode="numeric" />
      <TextArea label="Transformations to record (JSON array)" value={transformationsJson} onChange={setTransformationsJson} description="Recorded in the frozen protocol; transformations are not applied in this milestone." />
      <Button label={busy ? "Saving…" : "Create draft"} variant="primary" isDisabled={busy || !name.trim() || !hypothesis.trim() || !classificationRule.trim() || documentIds.length === 0 || detectorKeys.length === 0 || !Number.isInteger(Number(seed))} onClick={() => void createExperiment()} />
    </Stack></Section>
    <Stack gap={4}><Heading level={2}>Saved experiments</Heading>
      {experiments.length === 0 ? <Text as="p" color="secondary">No experiments yet. Create a draft with a classification rule to begin.</Text> : experiments.map((experiment) => {
        const value = experiment.progress.total ? experiment.progress.completed : 0;
        const variant = experiment.status === "COMPLETED" ? "success" : experiment.status === "FAILED" ? "error" : experiment.status === "PARTIALLY_COMPLETED" ? "warning" : "accent";
        return <Section key={experiment.id} variant="section" padding={4}><Stack gap={3}>
          <Stack direction="horizontal" align="center" gap={3} wrap="wrap"><StatusDot variant={variant} label={experiment.status.replaceAll("_", " ")} /><Heading level={3}>{experiment.name}</Heading></Stack>
          <Text as="p">{experiment.research_question} · {experiment.progress.completed}/{experiment.progress.total} pairs · {experiment.progress.failures} failures</Text>
          {experiment.progress.total > 0 && <ProgressBar label={`Progress for ${experiment.name}`} value={value} max={experiment.progress.total} hasValueLabel />}
          <Text as="p" type="supporting">Classification rule · {experiment.protocol.classification_rule} · seed {experiment.protocol.seed} · protocol {experiment.protocol.protocol_version}</Text>
          {experiment.interruption_reason && <Text as="p" color="accent">{experiment.interruption_reason}</Text>}
          <Stack direction="horizontal" gap={2} wrap="wrap">
            {experiment.status === "DRAFT" && <Button label="Run experiment" variant="primary" isDisabled={busy} onClick={() => void action(experiment.id, "run")} />}
            {(experiment.status === "QUEUED" || experiment.status === "RUNNING") && <Button label="Cancel" variant="secondary" isDisabled={busy} onClick={() => void action(experiment.id, "cancel")} />}
            {experiment.status === "PARTIALLY_COMPLETED" && <Button label="Resume missing pairs" variant="primary" isDisabled={busy} onClick={() => void action(experiment.id, "resume")} />}
            <Button label="Duplicate as draft" variant="secondary" isDisabled={busy} onClick={() => void action(experiment.id, "duplicate")} />
          </Stack>
          {experiment.results.length > 0 && <Stack gap={2}><Heading level={4}>Per-item results</Heading>{experiment.results.map((result) => <Text key={result.id} as="p" type="supporting">{result.filename ?? result.document_id} · {result.error ? `failed: ${result.error.message ?? "unknown error"}` : `score ${result.output.score ?? "unavailable"} (${result.output.score_semantics ?? "unknown"})${result.output.label ? ` · ${result.output.label}` : ""}`}</Text>)}</Stack>}
        </Stack></Section>;
      })}
    </Stack>
  </Stack></Stack></Section>;
}
