"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Detector = {
  key: string; name: string; model_id: string; revision: string; version: string;
  labels: string[]; supported_languages: string[]; minimum_words: number;
  max_sequence_length: number; score_semantics: string; training_summary: string;
  limitations: string[]; status: "operational" | "unavailable" | "not_checked";
  device: string | null; last_health_check: { available: boolean; checked_at: string; duration_ms?: number; failure_reason?: string | null } | null;
  failure_reason: string | null; weights_cached: boolean;
};
type Document = { id: string; filename: string; metadata: { provenance: string }; word_count: number };
type Result = { result_id: string; label: string; score: number; score_semantics: string; duration_ms: number; device: string; revision: string; raw_output: { chunk_count: number; chunks: { probabilities: Record<string, number> }[] }; error?: { message: string } };

export default function DetectorsPage() {
  const [detectors, setDetectors] = useState<Detector[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const [detectorResponse, documentResponse] = await Promise.all([
      fetch(`${API}/api/detectors`), fetch(`${API}/api/documents`),
    ]);
    if (!detectorResponse.ok) throw new Error(`Detector registry failed (HTTP ${detectorResponse.status})`);
    if (!documentResponse.ok) throw new Error(`Document library failed (HTTP ${documentResponse.status})`);
    setDetectors(await detectorResponse.json() as Detector[]);
    setDocuments(await documentResponse.json() as Document[]);
  }, []);
  useEffect(() => { void refresh().catch((reason: unknown) => setNotice(reason instanceof Error ? reason.message : "Could not load detector registry.")); }, [refresh]);

  const checkHealth = async () => {
    setBusy(true); setNotice(""); setResult(null);
    try {
      const response = await fetch(`${API}/api/detectors/roberta-openai/health`, { method: "POST" });
      const body = await response.json() as Detector;
      await refresh();
      setNotice(body.status === "operational" ? `Real inference health check passed on ${body.device}.` : body.failure_reason ?? "Detector is unavailable.");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Health check failed."); }
    finally { setBusy(false); }
  };
  const predict = async () => {
    if (!selectedId) return;
    setBusy(true); setNotice(""); setResult(null);
    try {
      const response = await fetch(`${API}/api/detectors/roberta-openai/documents/${selectedId}/predict`, { method: "POST" });
      const body = await response.json() as Result & { detail?: { message?: string; failure_reason?: string; error?: { message: string } } };
      if (!response.ok) throw new Error(body.detail?.failure_reason ?? body.detail?.error?.message ?? body.detail?.message ?? JSON.stringify(body.detail));
      setResult(body);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Prediction failed."); }
    finally { setBusy(false); }
  };

  const detector = detectors[0];
  const eligible = documents.filter((document) => document.word_count >= (detector?.minimum_words ?? 50));
  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}><Stack hAlign="center"><Stack as="main" width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / DETECTORS</Text><Heading level={1} type="display-1">Detector registry</Heading><Text as="p" color="secondary">Availability is recorded only after the model performs real inference. Scores describe the model output, not authorship certainty.</Text></Stack>
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    {detector ? <Section variant="section" padding={5}><Stack gap={3}>
      <Stack direction="horizontal" gap={3} align="center" wrap="wrap"><StatusDot variant={detector.status === "operational" ? "success" : detector.status === "unavailable" ? "error" : "warning"} label={detector.status.replaceAll("_", " ")} /><Heading level={2}>{detector.name}</Heading></Stack>
      <Text as="p" type="supporting">Model · {detector.model_id} · pinned revision {detector.revision}</Text>
      <Text as="p">Weights cached: {detector.weights_cached ? "yes" : "no"} · last health check device: {detector.device ?? "not checked"}</Text>
      <Text as="p">Training basis: {detector.training_summary}</Text>
      <Text as="p">Output labels: {detector.labels.join(", ")} · minimum {detector.minimum_words} words · sequence limit {detector.max_sequence_length} tokens · score semantics: {detector.score_semantics}</Text>
      {detector.limitations.map((limitation) => <Text key={limitation} as="p" color="secondary">Limitation · {limitation}</Text>)}
      {detector.failure_reason && <Text as="p" color="accent">Unavailable reason · {detector.failure_reason}</Text>}
      {detector.last_health_check && <Text as="p">Last real inference check · {new Date(detector.last_health_check.checked_at).toLocaleString()} · {detector.last_health_check.available ? `passed in ${Math.round(detector.last_health_check.duration_ms ?? 0)} ms` : `failed: ${detector.last_health_check.failure_reason}`}</Text>}
      <Button type="button" label={busy ? "Running real health check…" : "Run real health check"} variant="primary" isDisabled={busy} onClick={() => void checkHealth()} />
    </Stack></Section> : <Text as="p">Loading detector registry…</Text>}
    <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Run on a stored document</Heading><Text as="p" color="secondary">Only documents long enough for this detector are selectable. Declared provenance is stored with the result and is never inferred.</Text>
      {eligible.length ? <><Selector label="Document" value={selectedId} onChange={setSelectedId} options={eligible.map((document) => ({ value: document.id, label: `${document.filename} · ${document.metadata.provenance} · ${document.word_count} words` }))} />
        <Button type="button" label={busy ? "Running inference…" : "Run detector"} variant="secondary" isDisabled={busy || detector?.status !== "operational" || !selectedId} onClick={() => void predict()} />
      </> : <Text as="p">No eligible documents. Add an English document of at least {detector?.minimum_words ?? 50} words in Documents.</Text>}
      {result && <Stack gap={2}><Heading level={3}>Stored inference result</Heading><Text as="p">Model label · {result.label} · Fake class score · {result.score.toFixed(6)} ({result.score_semantics})</Text><Text as="p">Chunks · {result.raw_output.chunk_count} · device · {result.device} · duration · {Math.round(result.duration_ms)} ms</Text><Text as="p">Result ID · {result.result_id} · revision · {result.revision}</Text><Text as="p" color="secondary">The Fake score is the unweighted mean of chunk softmax outputs. It is not calibrated and does not establish who wrote the text.</Text></Stack>}
    </Stack></Section>
    <Text as="p" type="supporting" color="secondary">This baseline was trained to distinguish GPT-2 1.5B outputs from WebText. See the model card and MIA limitations before interpreting any result.</Text>
  </Stack></Stack></Section>;
}
