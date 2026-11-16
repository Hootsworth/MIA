// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Heading } from "@astryxdesign/core/Heading";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { Table } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { TextInput } from "@astryxdesign/core/TextInput";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type DocumentRow = { id: string; filename: string; sha256: string; word_count: number; deleted?: boolean };
type ScoreState = "value" | "censored_low" | "not_displayed";
type ReportRow = {
  id: string; document_id: string; submission_reference: string; report_timestamp: string;
  ai_writing: { raw: string; state: ScoreState; value: number | null; censoring_upper_bound?: number | null };
  similarity: { raw: string | null; state: ScoreState; value: number | null };
  eligible_word_count: number; report_file_name: string; report_file_sha256: string; score_semantics: string;
};
type TableRow = Record<string, unknown> & { id: string; document: string; submitted: string; similarity: string; ai: string; file: string };
type Option = { value: string; label: string };

const stateOptions: Option[] = [
  { value: "value", label: "Numeric value shown" },
  { value: "censored_low", label: "Censored low score" },
  { value: "not_displayed", label: "Not displayed" },
];

export default function TurnitinReportsPage() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [submissionReference, setSubmissionReference] = useState("");
  const [reportTimestamp, setReportTimestamp] = useState("");
  const [eligibleWordCount, setEligibleWordCount] = useState("");
  const [wordCountTolerance, setWordCountTolerance] = useState("10");
  const [similarityRaw, setSimilarityRaw] = useState("");
  const [similarityState, setSimilarityState] = useState<ScoreState>("not_displayed");
  const [aiRaw, setAiRaw] = useState("");
  const [aiState, setAiState] = useState<ScoreState>("not_displayed");
  const [aiUpperBound, setAiUpperBound] = useState("");
  const [similarityUpperBound, setSimilarityUpperBound] = useState("");
  const [detectorVersion, setDetectorVersion] = useState("");
  const [passagesJson, setPassagesJson] = useState("[]");
  const [reportFile, setReportFile] = useState<File | null>(null);
  const [identityConfirmed, setIdentityConfirmed] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [docResponse, reportResponse] = await Promise.all([fetch(`${API}/api/documents`), fetch(`${API}/api/turnitin-reports`)]);
    if (!docResponse.ok || !reportResponse.ok) throw new Error("Could not load documents or imported Turnitin reports.");
    setDocuments((await docResponse.json() as DocumentRow[]).filter((row) => !row.deleted));
    setReports(await reportResponse.json() as ReportRow[]);
  }, []);

  useEffect(() => {
    void refresh().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Could not load reports."));
  }, [refresh]);

  const selectedDocument = documents.find((row) => row.id === documentId);
  const documentOptions = documents.map((row) => ({ value: row.id, label: `${row.filename} · ${row.id} · ${row.word_count} words` }));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setNotice("");
    try {
      if (!selectedDocument || !reportFile) throw new Error("Select a document and its original report file.");
      let passages: unknown;
      try { passages = JSON.parse(passagesJson); } catch { throw new Error("Passage annotations must be valid JSON."); }
      if (!Array.isArray(passages)) throw new Error("Passage annotations must be a JSON array.");
      const body = new FormData();
      body.append("file", reportFile);
      body.append("payload", JSON.stringify({
        document_id: selectedDocument.id, confirmed_document_id: selectedDocument.id, identity_confirmed: identityConfirmed,
        submission_reference: submissionReference, report_timestamp: reportTimestamp,
        submitted_file_sha256: selectedDocument.sha256, eligible_word_count: Number(eligibleWordCount),
        word_count_tolerance: Number(wordCountTolerance), similarity_raw_value: similarityRaw || null,
        similarity_state: similarityState, similarity_censoring_upper_bound: similarityUpperBound === "" ? null : Number(similarityUpperBound),
        ai_raw_value: aiRaw, ai_state: aiState, ai_censoring_upper_bound: aiUpperBound === "" ? null : Number(aiUpperBound),
        detector_version: detectorVersion || null, passages,
      }));
      const response = await fetch(`${API}/api/turnitin-reports`, { method: "POST", body });
      const result = await response.json() as { detail?: string | { message?: string; difference?: number; tolerance?: number }; id?: string };
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message ?? JSON.stringify(result.detail));
      setNotice(`Imported and stored original report · ${result.id}`);
      setSubmissionReference(""); setEligibleWordCount(""); setSimilarityRaw(""); setAiRaw("");
      setDetectorVersion(""); setPassagesJson("[]"); setReportFile(null); setIdentityConfirmed(false);
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not import report."); }
    finally { setBusy(false); }
  }

  function displayScore(score: { raw: string | null; state: ScoreState; value: number | null }) {
    return score.state === "value" ? `${score.raw} (${score.value}%)` : `${score.raw ?? ""} · ${score.state.replaceAll("_", " ")}`;
  }

  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}><Stack hAlign="center"><Stack as="main" width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / REPORT IMPORT</Text><Heading level={1} type="display-1">Turnitin reports</Heading><Text as="p" color="secondary">Manual import only. Use this only for institution-authorised reports. MIA has no Turnitin API access and does not submit documents.</Text></Stack>
    {notice && <Text as="p" aria-live="polite" color="secondary">{notice}</Text>}
    <Section variant="section" padding={5}><Stack gap={4}><Heading level={2}>Import an original report</Heading>
      <Text as="p" color="secondary">Select the exact stored document and compare its original SHA-256 before attaching a report. The form records your identity confirmation; eligible word count must match within the tolerance shown.</Text>
      <form onSubmit={(event) => void submit(event)}><Stack gap={3}>
        <Selector label="Stored document · UUID" value={documentId} onChange={(value) => { setDocumentId(value); setEligibleWordCount(""); setIdentityConfirmed(false); }} isRequired options={documentOptions} />
        {selectedDocument && <Text as="p" type="supporting">Original SHA-256 · {selectedDocument.sha256}</Text>}
        <TextInput label="Submission reference" value={submissionReference} onChange={setSubmissionReference} isRequired />
        <TextInput label="Report timestamp shown by Turnitin (ISO 8601, timezone required)" value={reportTimestamp} onChange={setReportTimestamp} isRequired placeholder="2026-11-16T10:30:00Z" />
        <TextInput label="Eligible word count shown by Turnitin" value={eligibleWordCount} onChange={setEligibleWordCount} inputMode="numeric" isRequired />
        <TextInput label="Allowed word-count difference (words)" value={wordCountTolerance} onChange={setWordCountTolerance} inputMode="numeric" isRequired description={`Stored document count: ${selectedDocument?.word_count ?? "select a document"}.`} />
        <TextInput label="Similarity percentage exactly as displayed (optional)" value={similarityRaw} onChange={setSimilarityRaw} placeholder="e.g. 12% or *" />
        {similarityRaw && <Selector label="Similarity value state" value={similarityState} onChange={(value) => setSimilarityState(value as ScoreState)} options={stateOptions} />}
        {similarityState === "censored_low" && <TextInput label="Similarity censoring upper bound (optional)" value={similarityUpperBound} onChange={setSimilarityUpperBound} inputMode="decimal" />}
        <TextInput label="AI-writing value exactly as displayed" value={aiRaw} onChange={setAiRaw} isRequired placeholder="Enter the exact displayed text, including an asterisk if present" />
        <Selector label="AI-writing value state" value={aiState} onChange={(value) => setAiState(value as ScoreState)} options={stateOptions} />
        {aiState === "censored_low" && <TextInput label="AI-writing censoring upper bound (optional)" value={aiUpperBound} onChange={setAiUpperBound} inputMode="decimal" />}
        <TextInput label="Turnitin version (if disclosed)" value={detectorVersion} onChange={setDetectorVersion} />
        <TextArea label="Flagged-passage annotations (JSON array)" value={passagesJson} onChange={setPassagesJson} description={'Example: [{"passage":"quoted snippet","page":1}]. Do not include extra personal data.'} />
        <FileInput label="Original report file (PDF, PNG, or JPEG; max 20 MB)" value={reportFile} onChange={(value) => setReportFile(value instanceof File ? value : null)} accept=".pdf,.png,.jpg,.jpeg" maxSize={20 * 1024 * 1024} isRequired />
        <CheckboxInput label="I confirm the report's reference matches this document UUID and the submitted file is the stored original." value={identityConfirmed} onChange={setIdentityConfirmed} isRequired />
        <Button type="submit" label={busy ? "Importing…" : "Validate and import report"} variant="primary" isDisabled={busy || !selectedDocument || !reportFile || !identityConfirmed || !submissionReference.trim() || !eligibleWordCount || !aiRaw.trim()} />
      </Stack></form>
    </Stack></Section>
    <Stack gap={3}><Heading level={2}>Imported reports · {reports.length}</Heading>
      {reports.length === 0 ? <Text as="p" color="secondary">No reports have been imported.</Text> : <Table<TableRow> idKey="id" density="compact" dividers="rows" data={reports.map((row) => ({ id: row.id, document: documents.find((doc) => doc.id === row.document_id)?.filename ?? row.document_id, submitted: row.submission_reference, similarity: displayScore(row.similarity), ai: displayScore(row.ai_writing), file: row.report_file_name }))} columns={[{ key: "document", header: "Document" }, { key: "submitted", header: "Submission" }, { key: "similarity", header: "Similarity" }, { key: "ai", header: "AI writing" }, { key: "file", header: "Original report" }]} />}
    </Stack>
  </Stack></Stack></Section>;
}
