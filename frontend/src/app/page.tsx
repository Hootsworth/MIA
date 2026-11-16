"use client";

import { Button } from "@astryxdesign/core/Button";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCEPTED_FORMATS = ".pdf,.doc,.docx,.odt,.rtf,.txt,.text,.md,.markdown,.rst,.csv,.tsv,.json,.html,.htm,.xml,.yaml,.yml,.toml,.log,.tex,.ini,.conf";

type DetectorStatus = {
  key: string; name: string; status: "operational" | "unavailable" | "not_checked";
  model_id: string; revision: string; score_semantics: string; minimum_words: number;
  training_summary: string; limitations: string[]; device: string | null;
  resource_available: boolean; failure_reason: string | null;
};
type StoredDocument = { id: string; filename: string; sha256: string; word_count: number; quality_flags: { code: string; message: string }[] };
type Prediction = { result_id: string; score: number | null; score_semantics: string; label: string | null; device: string | null; duration_ms: number; revision: string; raw_output: { chunk_count?: number } };
type ApiError = { detail?: string | { message?: string; errors?: string[]; failure_reason?: string; word_count?: number } };
type Provenance = "" | "HUMAN" | "AI_GENERATED" | "AI_ASSISTED";
type Stage = "idle" | "uploading" | "checking" | "predicting" | "complete" | "error";

function getErrorMessage(body: ApiError, fallback: string): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (detail?.failure_reason) return detail.failure_reason;
  if (detail?.message) return detail.message;
  if (detail?.errors?.length) return detail.errors.join(" ");
  return fallback;
}

export default function Home() {
  const [backendState, setBackendState] = useState<"checking" | "online" | "offline">("checking");
  const [backendError, setBackendError] = useState("");
  const [detector, setDetector] = useState<DetectorStatus | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [provenance, setProvenance] = useState<Provenance>("");
  const [language, setLanguage] = useState("");
  const [authorLanguageBackground, setAuthorLanguageBackground] = useState("UNKNOWN");
  const [source, setSource] = useState("");
  const [license, setLicense] = useState("");
  const [consent, setConsent] = useState("");
  const [generatorModel, setGeneratorModel] = useState("");
  const [generatorVersion, setGeneratorVersion] = useState("");
  const [promptReference, setPromptReference] = useState("");
  const [editingHistory, setEditingHistory] = useState("");
  const [document, setDocument] = useState<StoredDocument | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [notice, setNotice] = useState("");
  const [stage, setStage] = useState<Stage>("idle");

  const refreshStatus = useCallback(async () => {
    const [healthResult, detectorResult] = await Promise.allSettled([
      fetch(`${API}/api/health`), fetch(`${API}/api/detectors`),
    ]);
    if (healthResult.status === "fulfilled" && healthResult.value.ok) {
      setBackendState("online"); setBackendError("");
    } else {
      setBackendState("offline"); setBackendError("MIA API is not responding. Start the app with ./start.sh.");
    }
    if (detectorResult.status === "fulfilled" && detectorResult.value.ok) {
      const rows = await detectorResult.value.json() as DetectorStatus[];
      setDetector(rows.find((row) => row.key === "roberta-openai") ?? null);
    } else {
      setDetector(null);
    }
  }, []);

  useEffect(() => { void refreshStatus(); }, [refreshStatus]);

  async function runDetection(documentId: string) {
    let activeDetector = detector;
    if (activeDetector?.status !== "operational") {
      setStage("checking"); setNotice("Checking the pinned model with a real inference. The first check may take a while while model resources are prepared.");
      const healthResponse = await fetch(`${API}/api/detectors/roberta-openai/health`, { method: "POST" });
      const healthBody = await healthResponse.json() as DetectorStatus & ApiError;
      if (!healthResponse.ok || healthBody.status !== "operational") {
        const reason = getErrorMessage(healthBody, healthBody.failure_reason ?? "The detector is unavailable.");
        setDetector(healthBody.key ? healthBody : activeDetector);
        throw new Error(`Your document is saved, but the MIA detector is unavailable: ${reason}`);
      }
      activeDetector = healthBody;
      setDetector(healthBody);
    }
    if (!activeDetector) throw new Error("The MIA AI detector is not registered.");
    setStage("predicting"); setNotice("Running the pinned MIA model on the extracted document text.");
    const response = await fetch(`${API}/api/detectors/roberta-openai/documents/${documentId}/predict`, { method: "POST" });
    const body = await response.json() as Prediction & ApiError;
    if (!response.ok) throw new Error(getErrorMessage(body, "MIA could not analyze this document."));
    setPrediction(body);
    setStage("complete");
    setNotice("Analysis complete. The result below is the model’s output, not proof of authorship.");
    await refreshStatus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice(""); setPrediction(null);
    if (!file) { setNotice("Choose a document to continue."); return; }
    if (backendState !== "online") { setNotice(backendError || "The MIA backend is unavailable."); return; }
    if (!provenance || !language) { setNotice("Declare the document provenance and language before analysis."); return; }
    if (!new Set(["en", "eng", "english"]).has(language.trim().toLowerCase())) {
      setNotice("The current MIA AI detector supports English only. You can still store other-language documents in the document library."); return;
    }
    setStage("uploading"); setNotice("Uploading the original and extracting its text with the format-specific parser.");
    try {
      const metadata: Record<string, string> = {
        provenance, language, author_language_background: authorLanguageBackground,
      };
      if (provenance === "HUMAN") Object.assign(metadata, { source, license, consent });
      if (provenance === "AI_GENERATED" || provenance === "AI_ASSISTED") {
        Object.assign(metadata, { generator_model: generatorModel, generator_version: generatorVersion });
      }
      if (provenance === "AI_GENERATED") Object.assign(metadata, { prompt_reference: promptReference });
      if (provenance === "AI_ASSISTED") Object.assign(metadata, { editing_history: editingHistory });
      const upload = new FormData(); upload.append("file", file); upload.append("metadata", JSON.stringify(metadata));
      const response = await fetch(`${API}/api/documents`, { method: "POST", body: upload });
      const body = await response.json() as StoredDocument & ApiError & { detail?: string | { message?: string; existing_document_id?: string; existing_filename?: string } };
      if (!response.ok) {
        if (response.status === 409 && typeof body.detail === "object" && body.detail.existing_document_id) {
          throw new Error(`This exact file is already stored as “${body.detail.existing_filename}”. Open the document library to review it before running another analysis.`);
        }
        throw new Error(getErrorMessage(body, "Document upload failed."));
      }
      setDocument(body);
      await runDetection(body.id);
    } catch (error) {
      setStage("error"); setNotice(error instanceof Error ? error.message : "MIA could not finish the analysis.");
    }
  }

  async function retryDetection() {
    if (!document) return;
    setNotice(""); setStage("checking");
    try { await runDetection(document.id); }
    catch (error) { setStage("error"); setNotice(error instanceof Error ? error.message : "MIA could not finish the analysis."); }
  }

  function startOver() {
    setFile(null); setDocument(null); setPrediction(null); setNotice(""); setStage("idle");
    setProvenance(""); setLanguage(""); setSource(""); setLicense(""); setConsent("");
    setGeneratorModel(""); setGeneratorVersion(""); setPromptReference(""); setEditingHistory("");
  }

  const backendVariant = backendState === "online" ? "success" : backendState === "offline" ? "error" : "warning";
  const backendLabel = backendState === "online" ? "Backend online" : backendState === "offline" ? "Backend offline" : "Checking backend";
  const detectorVariant = detector?.status === "operational" ? "success" : detector?.status === "unavailable" ? "error" : "warning";
  const detectorLabel = detector?.status === "operational" ? "Model ready" : detector?.status === "unavailable" ? "Model unavailable" : "Model not checked";
  const busy = ["uploading", "checking", "predicting"].includes(stage);

  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}>
    <Stack hAlign="center">
      <Stack as="main" width="100%" maxWidth="76rem" gap={6}>
        <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap">
          <Stack gap={0.5}><Text type="label" color="accent">MIA · LOCAL TEXT ANALYSIS</Text><Heading level={1} type="display-1">AI writing detection</Heading></Stack>
          <Stack direction="horizontal" gap={3} wrap="wrap" aria-label="Application status">
            <StatusDot variant={backendVariant} label={backendLabel} isPulsing={backendState === "checking"} />
            <StatusDot variant={detectorVariant} label={detectorLabel} />
          </Stack>
        </Stack>

        <Section variant="section" padding={5}>
          <Stack gap={3}>
            <Text type="label" color="secondary">A REAL MODEL. A CAREFUL READ OF ITS LIMITS.</Text>
            <Heading level={2} type="display-2">See what the text detector says.</Heading>
            <Text as="p" type="large" color="secondary">Upload a document and MIA will extract its text, run the pinned RoBERTa detector, and show the saved result with its model and version.</Text>
            <Text as="p" color="secondary">This installation sends the file to its configured MIA backend. Detection runs there with the open model; MIA does not call a commercial detector API.</Text>
          </Stack>
        </Section>

        {backendState === "offline" && <Section variant="section" padding={4}><Stack gap={2}><Heading level={3}>MIA backend unavailable</Heading><Text as="p" aria-live="polite" color="accent">{backendError}</Text><Button type="button" label="Retry connection" variant="secondary" onClick={() => void refreshStatus()} /></Stack></Section>}
        {notice && <Text as="p" aria-live="polite" color={stage === "error" ? "accent" : "secondary"}>{notice}</Text>}

        {!prediction && <Section variant="section" padding={5}>
          <Stack gap={4}>
            <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap">
              <Stack gap={1}><Text type="label" color="accent">01 / NEW ANALYSIS</Text><Heading level={2}>Choose a document</Heading></Stack>
              <Text as="p" type="supporting" color="secondary">PDF, DOC/DOCX, ODT, RTF, HTML, XML, Markdown, CSV, JSON, and text · up to 20 MB</Text>
            </Stack>
            <form onSubmit={(event) => void submit(event)}>
              <Stack gap={4}>
                <FileInput label="Drop a document here or browse files" value={file} onChange={(value) => { setFile(value instanceof File ? value : null); setDocument(null); setPrediction(null); setStage("idle"); setNotice(""); }} accept={ACCEPTED_FORMATS} maxSize={20 * 1024 * 1024} mode="dropzone" isRequired description="PDF and DOCX use document-aware parsers. Legacy DOC, ODT, and RTF need LibreOffice installed on the backend." />
                <Stack gap={3}>
                  <Stack gap={1}><Text type="label" color="accent">02 / RESEARCH CONTEXT</Text><Heading level={3}>Declare the text’s source</Heading><Text as="p" color="secondary">MIA stores this declaration with the document. It never guesses authorship from the detector score.</Text></Stack>
                  <Selector label="Declared provenance" value={provenance} onChange={(value) => setProvenance(value as Provenance)} placeholder="Choose the known source" isRequired options={[
                    { value: "HUMAN", label: "Human-written" },
                    { value: "AI_GENERATED", label: "AI-generated" },
                    { value: "AI_ASSISTED", label: "AI-assisted" },
                  ]} />
                  <TextInput label="Document language" value={language} onChange={setLanguage} isRequired placeholder="en (the current detector supports English)" />
                  <Selector label="Author language background" value={authorLanguageBackground} onChange={setAuthorLanguageBackground} options={[
                    { value: "UNKNOWN", label: "Unknown / not provided" }, { value: "NATIVE", label: "Native English" }, { value: "NON_NATIVE", label: "Non-native English" },
                  ]} />
                  {provenance === "HUMAN" && <Stack gap={3}><TextInput label="Source or collection" value={source} onChange={setSource} isRequired /><Stack direction="horizontal" gap={3} wrap="wrap"><TextInput label="License (if known)" value={license} onChange={setLicense} /><TextInput label="Consent record (if applicable)" value={consent} onChange={setConsent} /></Stack><Text as="p" type="supporting" color="secondary">A human document needs a source and either a license or consent record.</Text></Stack>}
                  {(provenance === "AI_GENERATED" || provenance === "AI_ASSISTED") && <Stack direction="horizontal" gap={3} wrap="wrap"><TextInput label="Generating model" value={generatorModel} onChange={setGeneratorModel} isRequired /><TextInput label="Model version" value={generatorVersion} onChange={setGeneratorVersion} isRequired /></Stack>}
                  {provenance === "AI_GENERATED" && <TextInput label="Prompt reference" value={promptReference} onChange={setPromptReference} isRequired />}
                  {provenance === "AI_ASSISTED" && <TextInput label="Editing history" value={editingHistory} onChange={setEditingHistory} isRequired />}
                </Stack>
                <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap">
                  <Text as="p" type="supporting" color="secondary">The model requires at least 50 English words.</Text>
                  <Button type="submit" label={busy ? "MIA is working…" : "Upload and run MIA detection"} variant="primary" isDisabled={busy || backendState !== "online" || !file || !provenance || !language} />
                </Stack>
              </Stack>
            </form>
            {stage === "error" && document && <Button type="button" label="Retry detection on saved document" variant="secondary" isDisabled={busy} onClick={() => void retryDetection()} />}
          </Stack>
        </Section>}

        {document && <Section variant="section" padding={5}>
          <Stack gap={3}>
            <Stack direction="horizontal" hAlign="between" vAlign="center" gap={3} wrap="wrap"><Stack gap={1}><Text type="label" color="accent">03 / SAVED DOCUMENT</Text><Heading level={3}>{document.filename}</Heading></Stack><Text as="p">{document.word_count} words</Text></Stack>
            <Text as="p" type="supporting">Document ID · {document.id}</Text>
            <Text as="p" type="supporting">Original SHA-256 · {document.sha256}</Text>
            {document.quality_flags.map((flag) => <Text key={flag.code} as="p" color="accent">Extraction note · {flag.message}</Text>)}
            <Stack direction="horizontal" gap={3} wrap="wrap"><Link href="/documents" isStandalone>Open document library</Link><Link href="/detectors" isStandalone>Detector details and model limits</Link></Stack>
          </Stack>
        </Section>}

        {prediction && document && <Section variant="section" padding={5}>
          <Stack gap={4}>
            <Stack gap={1}><Text type="label" color="accent">04 / MODEL OUTPUT</Text><Heading level={2}>MIA analysis</Heading></Stack>
            <Stack direction="horizontal" hAlign="between" vAlign="center" gap={4} wrap="wrap">
              <Stack gap={1}><Text as="p" color="secondary">Model label</Text><Heading level={3}>{prediction.label ?? "No label returned"}</Heading></Stack>
              <Stack gap={1}><Text as="p" color="secondary">{prediction.score_semantics === "probability" ? "Fake-class model output" : "Model score"}</Text><Heading level={2}>{prediction.score === null ? "Unavailable" : `${(prediction.score * 100).toFixed(1)}%`}</Heading></Stack>
            </Stack>
            <Text as="p" type="supporting">{detector?.name ?? "RoBERTa OpenAI Detector"} · revision {prediction.revision} · device {prediction.device ?? "not reported"} · {Math.round(prediction.duration_ms)} ms · {prediction.raw_output.chunk_count ?? 1} text segment(s)</Text>
            <Section variant="section" padding={4}><Stack gap={2}><Heading level={4}>How to read this result</Heading><Text as="p">This is the model’s output for its Fake class, shown as a percentage. The model was trained to distinguish GPT-2 outputs from WebText; its score is not calibrated truth and is not proof of authorship. It can be wrong, especially on current models, short passages, and non-native English writing.</Text></Stack></Section>
            <Stack direction="horizontal" gap={3} wrap="wrap"><Button type="button" label="Analyze another document" variant="primary" onClick={startOver} /><Link href="/experiments" isStandalone>Plan a reproducible experiment</Link></Stack>
          </Stack>
        </Section>}

        <Stack direction="horizontal" gap={4} wrap="wrap"><Link href="/documents" isStandalone>Document library</Link><Link href="/detectors" isStandalone>Detector registry</Link><Link href="/experiments" isStandalone>Experiments</Link><Link href="/turnitin-reports" isStandalone>Authorized report imports</Link></Stack>
        <Text as="p" type="supporting" color="secondary">MIA reports detector behavior, not authorship certainty. A score should never be the sole basis for an academic or professional decision.</Text>
      </Stack>
    </Stack>
  </Section>;
}
