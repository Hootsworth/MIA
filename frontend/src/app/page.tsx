// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Heading } from "@astryxdesign/core/Heading";
import { Section } from "@astryxdesign/core/Section";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCEPTED_FORMATS = ".pdf,.doc,.docx,.odt,.rtf,.txt,.text,.md,.markdown,.rst,.csv,.tsv,.json,.html,.htm,.xml,.yaml,.yml,.toml,.log,.tex,.ini,.conf";
type Detector = { name: string; status: string; revision: string; model_id: string; score_semantics: string; limitations: string[]; device: string | null };
type DocumentRecord = { id: string; filename: string; sha256: string; word_count: number; language_detection?: { name?: string; language?: string; confidence?: number | null; status?: string }; quality_flags: { code: string; message: string }[] };
type Prediction = { result_id: string; experiment_id: string; score: number | null; score_semantics: string; label: string | null; device: string | null; duration_ms: number; revision: string; raw_output: { chunk_count?: number } };
type Report = { id: string; markdown_url: string; csv_url: string };
type ApiError = { detail?: string | { message?: string; errors?: string[]; failure_reason?: string; existing_document_id?: string; existing_filename?: string } };
type Stage = "idle" | "uploading" | "checking" | "predicting" | "reporting" | "complete" | "error";

function message(body: ApiError, fallback: string): string {
  if (typeof body.detail === "string") return body.detail;
  return body.detail?.failure_reason ?? body.detail?.message ?? body.detail?.errors?.join(" ") ?? fallback;
}

export default function Home() {
  const [backend, setBackend] = useState<"checking" | "online" | "offline">("checking");
  const [detector, setDetector] = useState<Detector | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [context, setContext] = useState("");
  const [consent, setConsent] = useState(false);
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [notice, setNotice] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const refresh = useCallback(async () => {
    try {
      const [health, models] = await Promise.all([fetch(`${API}/api/health`), fetch(`${API}/api/detectors`)]);
      setBackend(health.ok ? "online" : "offline");
      if (models.ok) {
        const rows = await models.json() as (Detector & { key: string })[];
        setDetector(rows.find((row) => row.key === "roberta-openai") ?? null);
      } else setDetector(null);
    } catch { setBackend("offline"); setDetector(null); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function runModel(id: string): Promise<Prediction> {
    if (detector?.status !== "operational") {
      setStage("checking"); setNotice("Preparing MIA’s pinned model. The first check can take a few minutes.");
      const ready = await fetch(`${API}/api/detectors/roberta-openai/health`, { method: "POST" });
      const status = await ready.json() as Detector & ApiError & { status: string; failure_reason?: string };
      if (!ready.ok || status.status !== "operational") throw new Error(status.failure_reason ?? message(status, "The detector is unavailable."));
      setDetector(status);
    }
    setStage("predicting"); setNotice("MIA is analyzing the extracted text.");
    const response = await fetch(`${API}/api/detectors/roberta-openai/documents/${id}/predict`, { method: "POST" });
    const result = await response.json() as Prediction & ApiError;
    if (!response.ok) throw new Error(message(result, "MIA could not analyze this document."));
    setPrediction(result); setStage("complete"); setNotice("Analysis complete. This is a detector output, not proof of authorship.");
    await refresh();
    return result;
  }

  async function createReport(experimentId: string) {
    setStage("reporting"); setNotice("Creating a report from the saved detector result.");
    const response = await fetch(`${API}/api/experiments/${experimentId}/reports`, { method: "POST" });
    const body = await response.json() as Report & ApiError;
    if (!response.ok) throw new Error(message(body, "Report generation failed."));
    setReport(body); setStage("complete"); setNotice("Report ready.");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice(""); setPrediction(null); setReport(null);
    if (!file) { setNotice("Choose a document to continue."); return; }
    if (!consent) { setNotice("Confirm that you have permission to upload this document."); return; }
    if (backend !== "online") { setNotice("The MIA backend is unavailable. Start the app with ./start.sh."); return; }
    setStage("uploading"); setNotice("Uploading the document and extracting text.");
    try {
      const form = new FormData(); form.append("file", file);
      const metadata: Record<string, string> = { provenance: "UNKNOWN", language: "und", author_language_background: "UNKNOWN", consent: "Uploader confirmed permission or applicable public license for local MIA analysis." };
      if (context.trim()) metadata.context = context.trim();
      form.append("metadata", JSON.stringify(metadata));
      const uploaded = await fetch(`${API}/api/documents`, { method: "POST", body: form });
      const doc = await uploaded.json() as DocumentRecord & ApiError;
      if (!uploaded.ok) {
        if (uploaded.status === 409 && typeof doc.detail === "object" && doc.detail.existing_document_id) throw new Error(`This file is already stored as “${doc.detail.existing_filename}”. Review it in Documents before analyzing it again.`);
        throw new Error(message(doc, "Document upload failed."));
      }
      setDocument(doc);
      const result = await runModel(doc.id);
      await createReport(result.experiment_id);
    } catch (error) { setStage("error"); setNotice(error instanceof Error ? error.message : "MIA could not finish the analysis."); }
  }

  async function generateReport() {
    if (!prediction) return;
    try {
      await createReport(prediction.experiment_id);
    } catch (error) { setStage("error"); setNotice(error instanceof Error ? error.message : "Report generation failed."); }
  }

  function reset() { setFile(null); setContext(""); setConsent(false); setDocument(null); setPrediction(null); setReport(null); setNotice(""); setStage("idle"); }
  const busy = ["uploading", "checking", "predicting", "reporting"].includes(stage);

  return <Section width="100%" paddingInline={5} paddingBlock={6}><Stack hAlign="center"><Stack width="100%" maxWidth="47rem" gap={6}>
    <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap">
      <Stack gap={1}><Text type="label" color="accent">MIA · PRIVATE DOCUMENT ANALYSIS</Text><Heading level={1} type="display-1">A clearer read on your text.</Heading></Stack>
      <StatusDot variant={backend === "online" ? "success" : backend === "offline" ? "error" : "warning"} label={backend === "online" ? "Backend ready" : backend === "offline" ? "Backend offline" : "Connecting"} isPulsing={backend === "checking"} />
    </Stack>
    <Text as="p" type="large" color="secondary">Add a document. MIA handles extraction and language detection, then gives you a concise report from its open detector.</Text>
    {notice && <Text as="p" aria-live="polite" color={stage === "error" ? "accent" : "secondary"}>{notice}</Text>}
    {!prediction && <Section variant="section" padding={5}><Stack gap={4}>
      <Stack gap={1}><Text type="label" color="accent">NEW ANALYSIS</Text><Heading level={2}>Add your document</Heading><Text as="p" color="secondary">PDF, Word, OpenDocument, RTF, or text · up to 20 MB</Text></Stack>
      <form onSubmit={(event) => void submit(event)}><Stack gap={4}>
        <FileInput label="Drop a file here or browse" value={file} onChange={(value) => { setFile(value instanceof File ? value : null); setDocument(null); setPrediction(null); setReport(null); setStage("idle"); setNotice(""); }} accept={ACCEPTED_FORMATS} maxSize={20 * 1024 * 1024} mode="dropzone" isRequired description="Text is extracted by the local MIA backend. Legacy DOC, ODT, and RTF need LibreOffice installed." />
        <TextInput label="A little context (optional)" value={context} onChange={(value) => setContext(value.slice(0, 1000))} placeholder="For example, where the text came from" description="Stored as your note. MIA does not use it to infer authorship." />
        <CheckboxInput label="I have permission or an applicable public license to upload this document for MIA analysis." value={consent} onChange={setConsent} isRequired description="The original and extracted text stay in local MIA storage. Provenance remains undeclared unless you add it later." />
        <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap"><Text as="p" type="supporting" color="secondary">At least 50 English words are needed for this detector.</Text><Button type="submit" label={busy ? "Working…" : "Analyze and generate report"} variant="primary" isDisabled={busy || backend !== "online" || !file || !consent} /></Stack>
      </Stack></form>
    </Stack></Section>}
    {document && <Section variant="section" padding={4}><Stack gap={2}><Heading level={3}>{document.filename}</Heading><Text as="p" color="secondary">{document.word_count.toLocaleString()} words · {document.language_detection?.name ?? "Language not detected"}{document.language_detection?.confidence != null ? ` · ${Math.round(document.language_detection.confidence * 100)}% detection confidence` : ""}</Text>{document.quality_flags.map((flag) => <Text key={flag.code} as="p" color="accent">{flag.message}</Text>)}</Stack></Section>}
    {prediction && <Section variant="section" padding={5}><Stack gap={4}>
      <Stack gap={1}><Text type="label" color="accent">MIA RESULT</Text><Heading level={2}>{prediction.label ?? "Model output"}</Heading></Stack>
      <Stack direction="horizontal" hAlign="between" vAlign="center" gap={4} wrap="wrap"><Stack gap={1}><Text as="p" color="secondary">Raw model score</Text><Heading level={1}>{prediction.score == null ? "Unavailable" : prediction.score.toFixed(4)}</Heading></Stack><Text as="p" type="supporting" color="secondary">{prediction.score_semantics}</Text></Stack>
      <Text as="p" type="supporting" color="secondary">{detector?.name ?? "RoBERTa OpenAI Detector"} · revision {prediction.revision} · {Math.round(prediction.duration_ms)} ms · {prediction.raw_output.chunk_count ?? 1} segment(s)</Text>
      <Text as="p">This score describes one model’s output. It is not a calibrated probability or proof of who wrote the text. Detector results can be wrong and should not be the sole basis for a consequential decision.</Text>
      {report ? <Stack direction="horizontal" gap={3} wrap="wrap"><Button label="Download report" variant="primary" href={`${API}${report.markdown_url}`} /><Button label="Download data (CSV)" variant="secondary" href={`${API}${report.csv_url}`} /></Stack> : <Button type="button" label={stage === "reporting" ? "Preparing report…" : "Generate report"} variant="primary" isDisabled={busy} onClick={() => void generateReport()} />}
      <Button type="button" label="Analyze another document" variant="secondary" onClick={reset} />
    </Stack></Section>}
    <Text as="p" type="supporting" color="secondary">MIA processes files with your local backend. It does not infer provenance, author language background, or authorship certainty.</Text>
  </Stack></Stack></Section>;
}
