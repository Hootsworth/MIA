// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
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
  failure_reason: string | null; resource_available: boolean; resource_label: string; weights_cached: boolean;
};
type Document = { id: string; filename: string; metadata: { provenance: string }; word_count: number };
type Result = { result_id: string; label: string | null; score: number; score_semantics: string; duration_ms: number; device: string; revision: string; raw_output: { chunk_count?: number; chunks?: { probabilities: Record<string, number> }[]; sources?: { source_id: string; title: string; source_url: string; license_name: string; overlap_percentage: number; matched_query_tokens: number; spans: { query_text: string; source_text: string }[] }[] }; error?: { message: string } };

export default function DetectorsPage() {
  const [detectors, setDetectors] = useState<Detector[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
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
    const detectorRows = await detectorResponse.json() as Detector[];
    setDetectors(detectorRows);
    setSelectedKey((current) => current || detectorRows[0]?.key || "");
    setDocuments(await documentResponse.json() as Document[]);
  }, []);
  useEffect(() => { void refresh().catch((reason: unknown) => setNotice(reason instanceof Error ? reason.message : "Could not load detector registry.")); }, [refresh]);

  const checkHealth = async () => {
    setBusy(true); setNotice(""); setResult(null);
    try {
      const response = await fetch(`${API}/api/detectors/${detector?.key}/health`, { method: "POST" });
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
      const response = await fetch(`${API}/api/detectors/${detector?.key}/documents/${selectedId}/predict`, { method: "POST" });
      const body = await response.json() as Result & { detail?: { message?: string; failure_reason?: string; error?: { message: string } } };
      if (!response.ok) throw new Error(body.detail?.failure_reason ?? body.detail?.error?.message ?? body.detail?.message ?? JSON.stringify(body.detail));
      setResult(body);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Prediction failed."); }
    finally { setBusy(false); }
  };

  const detector = detectors.find((item) => item.key === selectedKey) ?? detectors[0];
  const eligible = documents.filter((document) => document.word_count >= (detector?.minimum_words ?? 50));
  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}><Stack hAlign="center"><Stack as="main" width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / DETECTORS</Text><Heading level={1} type="display-1">Detector registry</Heading><Text as="p" color="secondary">Availability is recorded only after the model performs real inference. Scores describe the model output, not authorship certainty.</Text></Stack>
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    {detectors.length > 1 && <Selector label="Detector" value={selectedKey} onChange={(value) => { setSelectedKey(value); setResult(null); setNotice(""); }} options={detectors.map((item) => ({ value: item.key, label: `${item.name} · ${item.status.replaceAll("_", " ")}` }))} />}
    {detector ? <Section variant="section" padding={5}><Stack gap={3}>
      <Stack direction="horizontal" gap={3} align="center" wrap="wrap"><StatusDot variant={detector.status === "operational" ? "success" : detector.status === "unavailable" ? "error" : "warning"} label={detector.status.replaceAll("_", " ")} /><Heading level={2}>{detector.name}</Heading></Stack>
      <Text as="p" type="supporting">Implementation · {detector.model_id} · revision {detector.revision}</Text>
      <Text as="p">{detector.resource_label}: {detector.resource_available ? "available" : "unavailable"} · last health check device: {detector.device ?? "not checked"}</Text>
      <Text as="p">Training basis: {detector.training_summary}</Text>
      <Text as="p">Output labels: {detector.labels.join(", ") || "none"} · minimum {detector.minimum_words} words · sequence limit {detector.max_sequence_length > 0 ? `${detector.max_sequence_length} tokens` : "not applicable"} · score semantics: {detector.score_semantics}</Text>
      {detector.limitations.map((limitation) => <Text key={limitation} as="p" color="secondary">Limitation · {limitation}</Text>)}
      {detector.failure_reason && <Text as="p" color="accent">Unavailable reason · {detector.failure_reason}</Text>}
      {detector.last_health_check && <Text as="p">Last real inference check · {new Date(detector.last_health_check.checked_at).toLocaleString()} · {detector.last_health_check.available ? `passed in ${Math.round(detector.last_health_check.duration_ms ?? 0)} ms` : `failed: ${detector.last_health_check.failure_reason}`}</Text>}
      <Button type="button" label={busy ? "Running real health check…" : "Run real health check"} variant="primary" isDisabled={busy} onClick={() => void checkHealth()} />
    </Stack></Section> : <Text as="p">Loading detector registry…</Text>}
    <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Run on a stored document</Heading><Text as="p" color="secondary">Only documents long enough for this detector are selectable. Declared provenance is stored with the result and is never inferred.</Text>
      {eligible.length ? <><Selector label="Document" value={selectedId} onChange={setSelectedId} options={eligible.map((document) => ({ value: document.id, label: `${document.filename} · ${document.metadata.provenance} · ${document.word_count} words` }))} />
        <Button type="button" label={busy ? "Running inference…" : "Run detector"} variant="secondary" isDisabled={busy || detector?.status !== "operational" || !selectedId} onClick={() => void predict()} />
      </> : <Text as="p">No eligible documents. Add an English document of at least {detector?.minimum_words ?? 50} words in Documents.</Text>}
      {result && <Stack gap={2}><Heading level={3}>Stored inference result</Heading><Text as="p">Score · {result.score.toFixed(4)} {result.score_semantics}{result.label ? ` · label ${result.label}` : " · no authorship label"}</Text><Text as="p">{result.raw_output.chunk_count ? `Chunks · ${result.raw_output.chunk_count} · ` : ""}Device · {result.device} · duration · {Math.round(result.duration_ms)} ms</Text><Text as="p">Result ID · {result.result_id} · revision · {result.revision}</Text>
        {detector?.key === "roberta-openai" && <Text as="p" color="secondary">The Fake score is the unweighted mean of chunk softmax outputs. It is not calibrated and does not establish who wrote the text.</Text>}
        {result.raw_output.sources?.map((source) => <Section key={source.source_id} variant="section" padding={3}><Stack gap={2}><Heading level={4}>{source.title}</Heading>{source.source_url && <Link href={source.source_url} isExternalLink isStandalone>{source.source_url}</Link>}<Text as="p">Overlap · {source.overlap_percentage.toFixed(2)}% of query words · {source.matched_query_tokens} words · {source.license_name || "license not recorded"}</Text>{source.spans.map((span, index) => <Text key={`${source.source_id}-${index}`} as="p" type="supporting">Matched passage · {span.query_text}</Text>)}</Stack></Section>)}
      </Stack>}
    </Stack></Section>
    <Text as="p" type="supporting" color="secondary">Exact fingerprint overlap is neither a plagiarism judgment nor proof of authorship. A missing reference corpus leaves similarity unavailable; no matches only means no indexed fingerprints matched.</Text>
  </Stack></Stack></Section>;
}
