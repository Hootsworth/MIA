// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { useEffect, useState, type FormEvent } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCEPTED = ".pdf,.doc,.docx,.odt,.rtf,.txt,.text,.md,.markdown,.rst,.csv,.tsv,.json,.html,.htm,.xml,.yaml,.yml,.toml,.log,.tex,.ini,.conf";

type ErrorBody = { detail?: string | { message?: string; errors?: string[]; failure_reason?: string; existing_document_id?: string } };
type DetectionResult = {
  result_id: string; detector: string; name: string; model_id: string; revision: string;
  label: string | null; score: number; score_semantics: string; device: string;
  duration_ms: number; raw_output: Record<string, unknown>;
};
type ReviewSegment = { text: string; label: "human" | "ai" | "ai_edited" | "humanized" | null; ai_related_score?: number; class_probabilities?: Record<string, number> };
type SuiteResult = { experiment_id: string; filename: string; word_count: number; results: DetectionResult[]; review_segments: ReviewSegment[]; note: string };
type Phase = "idle" | "uploading" | "analyzing" | "error" | "complete";
type ModelState = "checking" | "ready" | "missing" | "offline";
const MODEL_CARDS: Record<string, string> = {
  "tropa-mini": "https://huggingface.co/wasitaigeneratedcom/tropa-mini-ai-text-detector",
  "modernbert-ai-text-detector": "https://huggingface.co/jaspai/modernbert-ai-text-detector",
};

function errorText(body: ErrorBody) {
  if (typeof body.detail === "string") return body.detail;
  return body.detail?.failure_reason ?? body.detail?.message ?? body.detail?.errors?.join(" ") ?? "The detector could not finish this document.";
}

function percent(value: unknown) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function ModelCard({ result }: { result: DetectionResult }) {
  const raw = result.raw_output;
  const classes = (raw.class_probabilities ?? raw.probabilities ?? {}) as Record<string, number>;
  const threshold = raw.reference_threshold as number | undefined;
  const aiScore = (raw.ai_related_score as number | undefined) ?? result.score;
  return <article className="model-card">
    <div className="model-topline"><p className="eyebrow">MODEL OUTPUT</p><span className="model-device">{result.device} · {Math.round(result.duration_ms)} ms</span></div>
    <h3>{result.name}</h3>
    <p className="model-label">{(result.label ?? "No label returned").replaceAll("_", " ")}</p>
    {result.detector === "tropa-mini" ? <>
      <div className="score-row"><span>AI-related score</span><strong>{percent(aiScore)}</strong></div>
      <p className="fineprint">1 − P(human); this model score is not a calibrated probability that a person used AI.</p>
      {threshold != null && <p className="threshold-note">{aiScore >= threshold ? "Above" : "Below"} the model publisher’s conservative reference threshold ({percent(threshold)}).</p>}
    </> : <>
      <div className="score-row"><span>Machine-class score</span><strong>{percent(result.score)}</strong></div>
      <p className="fineprint">Uncalibrated model output. Thresholds should be set on human writing from the target population.</p>
    </>}
    <div className="class-list" aria-label="Model class outputs">
      {Object.entries(classes).map(([name, value]) => <div className="class-row" key={name}>
        <span>{name.replaceAll("_", " ")}</span><div className="bar"><i style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} /></div><b>{percent(value)}</b>
      </div>)}
    </div>
    <p className="model-foot"><a href={MODEL_CARDS[result.detector]} target="_blank" rel="noreferrer">Model card ↗</a> · {result.model_id} · revision {result.revision}</p>
  </article>;
}

function PassageReview({ segments }: { segments: ReviewSegment[] }) {
  if (!segments.length) return null;
  const labels = ["ai", "ai_edited", "humanized", "human"] as const;
  const labelText: Record<NonNullable<ReviewSegment["label"]>, string> = {
    ai: "AI-like", ai_edited: "AI-edited-like", humanized: "Humanized-like", human: "Human-like",
  };
  let passageNumber = 0;
  return <section className="passage-review" aria-label="Tropa Mini passage review">
    <div className="passage-heading"><div><p className="eyebrow">TROPA MINI · TEXT HIGHLIGHTS</p><h3>Passages to review</h3></div><span>Extracted text · model-scored spans</span></div>
    <p className="passage-caveat">Colors mark sentence-aligned passages scored separately by Tropa Mini. They are coarse passage classifications, not word-level explanations or proof that text was AI-written.</p>
    <div className="passage-legend" aria-label="Passage label legend">{labels.map((label) => <span className={`passage-key passage-${label}`} key={label}><i />{labelText[label]}</span>)}</div>
    <div className="review-text">{segments.map((segment, index) => {
      if (!segment.label) return <span key={`plain-${index}`}>{segment.text}</span>;
      const number = ++passageNumber;
      return <mark className={`inline-mark mark-${segment.label}`} title={`${labelText[segment.label]} · AI-related score ${percent(segment.ai_related_score)}`} aria-label={`${labelText[segment.label]} passage ${number}`} key={`marked-${index}`}>{segment.text}</mark>;
    })}</div>
  </section>;
}

export default function DetectorPage() {
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<SuiteResult | null>(null);
  const [backend, setBackend] = useState<"checking" | "online" | "offline">("checking");
  const [models, setModels] = useState<ModelState>("checking");
  const [modernbertAvailable, setModernbertAvailable] = useState(false);
  const [includeModernbert, setIncludeModernbert] = useState(false);

  useEffect(() => {
    void Promise.all([fetch(`${API}/api/health`), fetch(`${API}/api/detectors`)]).then(async ([health, response]) => {
      setBackend(health.ok ? "online" : "offline");
      if (!health.ok || !response.ok) { setModels("offline"); return; }
      const detectors = await response.json() as { key: string; weights_cached: boolean }[];
      const tropa = detectors.find(({ key }) => key === "tropa-mini");
      const modernbert = detectors.find(({ key }) => key === "modernbert-ai-text-detector");
      setModels(tropa?.weights_cached ? "ready" : "missing");
      setModernbertAvailable(Boolean(modernbert?.weights_cached));
    }).catch(() => { setBackend("offline"); setModels("offline"); setModernbertAvailable(false); });
  }, []);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setNotice(""); setResult(null);
    if (models !== "ready") { setPhase("error"); setNotice("Download both local model checkpoints first with `make detector-models`."); return; }
    if (!file) { setPhase("error"); setNotice("Choose a document to continue."); return; }
    if (!consent) { setPhase("error"); setNotice("Confirm that you have permission to upload this document."); return; }
    setPhase("uploading"); setNotice("Extracting text with the local MIA backend.");
    try {
      const form = new FormData(); form.append("file", file);
      form.append("metadata", JSON.stringify({
        provenance: "UNKNOWN", language: "und", author_language_background: "UNKNOWN",
        consent: "Uploader confirmed permission or applicable public license for local MIA analysis.",
      }));
      const uploadResponse = await fetch(`${API}/api/documents`, { method: "POST", body: form });
      const document = await uploadResponse.json() as { id: string } & ErrorBody;
      let documentId = document.id;
      if (!uploadResponse.ok) {
        if (uploadResponse.status === 409 && typeof document.detail === "object" && document.detail.existing_document_id) {
          documentId = document.detail.existing_document_id;
        } else throw new Error(errorText(document));
      }
      setPhase("analyzing"); setNotice(includeModernbert ? "Running Tropa Mini and the optional ModernBERT comparison locally." : "Running Tropa Mini locally.");
      const response = await fetch(`${API}/api/detector-suite/documents/${documentId}/predict?include_modernbert=${includeModernbert}`, { method: "POST" });
      const body = await response.json() as SuiteResult & ErrorBody;
      if (!response.ok) throw new Error(errorText(body));
      setResult(body); setPhase("complete"); setNotice(includeModernbert ? "Analysis complete. Review the model outputs separately." : "Analysis complete. Review Tropa Mini’s output and passage highlights.");
    } catch (error) {
      setPhase("error"); setNotice(error instanceof Error ? error.message : "Analysis failed.");
    }
  }

  function reset() { setFile(null); setConsent(false); setPhase("idle"); setNotice(""); setResult(null); }
  const busy = phase === "uploading" || phase === "analyzing";
  const labels = result?.results.map((item) => item.label?.toLowerCase());
  const disagree = Boolean(labels?.length && new Set(labels).size > 1);

  return <main className="page-wrap">
    <header className="site-header">
      <a className="brand" href="http://localhost:3000/">MIA<span>.</span></a>
      <nav aria-label="App navigation"><a className="active" href="#analyze">Detector</a><a href="#method">How it works</a><a href="http://localhost:3000/">Research lab ↗</a></nav>
      <span className={`status ${backend === "online" && models === "ready" ? "online" : backend === "offline" || models === "offline" ? "offline" : "checking"}`}>{backend === "offline" || models === "offline" ? "Backend offline" : models === "ready" ? "Tropa Mini ready locally" : models === "missing" ? "Tropa Mini weights needed" : "Checking local models"}</span>
    </header>

    <section className="hero" id="analyze">
      <p className="eyebrow">A PRIVATE, LOCAL TEXT CHECK</p>
      <h1>Read the signals.<br /><em>Keep the context.</em></h1>
      <p className="intro">Tropa Mini reviews your document and highlights passages worth a closer look. Add ModernBERT only when you want a second, independent model output.</p>
    </section>

    {!result ? <div className="workspace-layout"><section className="upload-card">
      <form onSubmit={(event) => void analyze(event)}>
        <label className="dropzone" htmlFor="document-file" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setFile(event.dataTransfer.files?.[0] ?? null); }}>
          <span className="upload-icon" aria-hidden="true">↑</span>
          <strong>{file ? file.name : "Drop your document here"}</strong>
          <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · click to change` : "or browse your files · PDF, DOCX, TXT, Markdown and more"}</span>
          <input id="document-file" type="file" accept={ACCEPTED} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <div className="optional-model">
          <label className="optional-toggle">
            <input type="checkbox" checked={includeModernbert} disabled={!modernbertAvailable || busy} onChange={(event) => setIncludeModernbert(event.target.checked)} />
            <span className="toggle-copy"><strong>Include ModernBERT comparison</strong><small>{modernbertAvailable ? "Optional second model · runs locally" : "Optional model weights are not installed"}</small></span>
          </label>
          {modernbertAvailable ? <a href={MODEL_CARDS["modernbert-ai-text-detector"]} target="_blank" rel="noreferrer">About this model ↗</a> : <a href="#method">Setup details ↓</a>}
        </div>
        <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>I have permission or an applicable public license to upload this document for MIA analysis.</span></label>
        <div className="form-footer"><p>English · 50+ words · 20 MB max{models === "missing" && <> · run <code>make detector-models</code></>}</p><button className="primary" disabled={busy || !file || !consent || backend !== "online" || models !== "ready" || (includeModernbert && !modernbertAvailable)}>{busy ? "Analyzing…" : "Review document"}<span aria-hidden="true"> ↗</span></button></div>
      </form>
      {notice && <p className={`notice ${phase === "error" ? "error" : ""}`} role="status">{notice}</p>}
      <div className="privacy-note"><span className="privacy-mark" aria-hidden="true">●</span> Your document is processed and stored by this local MIA instance. Nothing is sent to a third-party detector.</div>
    </section><aside className="workflow-card"><p className="eyebrow">A SIMPLE REVIEW</p><h2>From file to context</h2><div className="workflow-step"><span>01</span><div><strong>Extract</strong><p>Read selectable text from your document locally.</p></div></div><div className="workflow-step"><span>02</span><div><strong>Review</strong><p>See Tropa Mini’s document class and highlighted passages.</p></div></div><div className="workflow-step"><span>03</span><div><strong>Compare, if useful</strong><p>Turn on ModernBERT only when you want another model’s view.</p></div></div><p className="workflow-foot">No combined score. No authorship verdict.</p></aside></div> : <section className="results" aria-live="polite">
      <div className="results-heading"><div><p className="eyebrow">ANALYSIS COMPLETE</p><h2>{result.filename}</h2><p className="result-meta">{result.word_count.toLocaleString()} extracted words · run {result.experiment_id.slice(0, 8)}</p></div><button className="secondary" onClick={reset}>New analysis</button></div>
      {disagree && <p className="disagreement"><strong>The models disagree.</strong> That is a limitation signal; MIA does not average these outputs into a single verdict.</p>}
      <div className={`model-grid ${result.results.length === 1 ? "primary-only" : "with-comparison"}`}>{result.results.map((item) => <ModelCard key={item.detector} result={item} />)}</div>
      <PassageReview segments={result.review_segments ?? []} />
      <div className="result-disclaimer"><strong>How to read this</strong><p>Model scores and passage colors are imperfect signals, not proof of authorship. Style, topic, historical language, edits, and newer generators can affect the output. Don’t use a detector result as the sole basis for a consequential decision.</p></div>
      <button className="secondary" onClick={reset}>Analyze another document</button>
      {notice && <p className="notice" role="status">{notice}</p>}
    </section>}

    <section className="method" id="method">
      <p className="eyebrow">THE APPROACH</p>
      <div className="method-grid">
        <article><span>01</span><h3>One clear starting point</h3><p>Tropa Mini returns human, AI, AI-edited, and humanized classes, with sentence-aligned passage highlights. <a href={MODEL_CARDS["tropa-mini"]} target="_blank" rel="noreferrer">Model card ↗</a></p></article>
        <article><span>02</span><h3>Optional second opinion</h3><p>ModernBERT can be enabled as a separate comparison. Install it with <code>make detector-models-all</code>. It may disagree with Tropa Mini; MIA never averages the outputs. <a href={MODEL_CARDS["modernbert-ai-text-detector"]} target="_blank" rel="noreferrer">Model card ↗</a></p></article>
        <article><span>03</span><h3>Local by default</h3><p>Documents and inference stay on this MIA instance. No content is sent to a third-party detector.</p></article>
      </div>
    </section>
    <footer><span>MIA · OPEN DETECTOR TOOLKIT</span><span>Local inference · Apache-2.0 application</span></footer>
  </main>;
}
