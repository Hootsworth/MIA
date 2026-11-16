"use client";

import { Button } from "@astryxdesign/core/Button";
import { Table } from "@astryxdesign/core/Table";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Heading } from "@astryxdesign/core/Heading";
import { List, ListItem } from "@astryxdesign/core/List";
import { Section } from "@astryxdesign/core/Section";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Metadata = { provenance: string; language: string; author_language_background: string; domain?: string; genre?: string; source?: string; license?: string; consent?: string; generator_model?: string; generator_version?: string; prompt_reference?: string; editing_history?: string };
type Doc = { id: string; filename: string; sha256: string; metadata: Metadata; word_count: number; quality_flags: {code:string;message:string;encoding?:string}[]; duplicate_flags: {document_id:string;filename:string;jaccard:number}[]; pages?: {page:number|null;text:string}[] };
type ImportedReport = { id: string; submission_reference: string; report_timestamp: string; ai_writing: { raw: string; state: string; value: number | null }; similarity: { raw: string | null; state: string; value: number | null }; eligible_word_count: number; report_file_sha256: string };
type ImportedReportRow = Record<string, unknown> & { id: string; submission: string; timestamp: string; similarity: string; aiWriting: string; eligibleWords: number; reportHash: string };
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const blank: Metadata = { provenance: "HUMAN", language: "en", author_language_background: "UNKNOWN" };

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<Doc | null>(null);
  const [uploadMetadata, setUploadMetadata] = useState<Metadata>(blank);
  const [editMetadata, setEditMetadata] = useState<Metadata>(blank);
  const [filter, setFilter] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<{id:string;filename:string} | null>(null);
  const [audit, setAudit] = useState<{event_type:string;created_at:string}[]>([]);
  const [turnitinReports, setTurnitinReports] = useState<ImportedReport[]>([]);
  const refresh = useCallback(async () => {
    const response = await fetch(`${API}/api/documents`);
    if (!response.ok) throw new Error(`Unable to load documents (HTTP ${response.status})`);
    setDocs(await response.json() as Doc[]);
  }, []);
  useEffect(() => { void refresh().catch((e: unknown) => setNotice(e instanceof Error ? e.message : "Request failed")); }, [refresh]);

  const setUploadField = (key: keyof Metadata, value: string) => setUploadMetadata((current) => ({ ...current, [key]: value }));
  const setEditField = (key: keyof Metadata, value: string) => setEditMetadata((current) => ({ ...current, [key]: value }));
  const loadDocument = async (id: string) => {
    const response = await fetch(`${API}/api/documents/${id}`);
    const body = await response.json();
    if (!response.ok) { setNotice(body.detail ?? "Unable to load document"); return; }
    setSelected(body as Doc);
    setEditMetadata((body as Doc).metadata);
    const reportResponse = await fetch(`${API}/api/turnitin-reports?document_id=${encodeURIComponent(id)}`);
    if (reportResponse.ok) setTurnitinReports(await reportResponse.json() as ImportedReport[]);
    const auditResponse = await fetch(`${API}/api/documents/${id}/audit`);
    if (auditResponse.ok) setAudit(await auditResponse.json() as {event_type:string;created_at:string}[]);
  };
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setNotice("");
    const form = event.currentTarget;
    const file = uploadFile;
    if (!file) { setNotice("Choose a document first."); setBusy(false); return; }
    const declared = Object.fromEntries(new FormData(form).entries());
    for (const key of ["domain", "genre", "source", "license", "consent", "generator_model", "generator_version", "prompt_reference", "editing_history"]) if (!declared[key]) delete declared[key];
    const body = new FormData(); body.append("file", file); body.append("metadata", JSON.stringify(declared));
    try {
      const response = await fetch(`${API}/api/documents`, { method: "POST", body });
      const result = await response.json();
      if (!response.ok) { if (response.status === 409 && result.detail?.existing_document_id) setDuplicateTarget({ id: result.detail.existing_document_id, filename: result.detail.existing_filename }); throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message ?? JSON.stringify(result.detail)); }
      setNotice(`Saved ${result.filename} · ${result.word_count} words`); form.reset(); setUploadMetadata(blank); setUploadFile(null); await refresh(); await loadDocument(result.id);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Upload failed"); }
    finally { setBusy(false); }
  };
  const saveMetadata = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!selected) return; setBusy(true);
    const fields = new FormData(event.currentTarget); const value = Object.fromEntries(fields.entries()) as Metadata;
    for (const key of ["domain", "genre", "source", "license", "consent", "generator_model", "generator_version", "prompt_reference", "editing_history"] as const) if (!value[key]) delete value[key];
    try {
      const response = await fetch(`${API}/api/documents/${selected.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
      const result = await response.json(); if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
      setNotice("Metadata saved and audit event recorded."); await refresh(); await loadDocument(selected.id);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Metadata update failed"); }
    finally { setBusy(false); }
  };
  const remove = async () => { if (!selected) return; const response = await fetch(`${API}/api/documents/${selected.id}`, { method: "DELETE" }); if (response.ok) { setNotice("Document archived; original file retained."); setSelected(null); await refresh(); } else setNotice("Archive failed."); };
  const exportManifest = () => { window.location.href = `${API}/api/documents/manifest.csv`; };
  const importManifest = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const file = manifestFile; if (!file) { setNotice("Choose a manifest first."); return; } const data = new FormData(); data.append("file", file); const response = await fetch(`${API}/api/documents/manifest.csv`, { method: "POST", body: data }); const result = await response.json(); setNotice(response.ok ? `Imported ${result.imported} manifest rows.` : result.detail ?? "Manifest import failed."); await refresh(); };
  const visible = docs.filter((doc) => `${doc.filename} ${doc.metadata.provenance} ${doc.metadata.language}`.toLowerCase().includes(filter.toLowerCase()));
  const field = (name: keyof Metadata, label: string, metadata: Metadata, onChange: (key: keyof Metadata, value: string) => void, required = false) => <TextInput htmlName={name} label={label} value={metadata[name] ?? ""} isRequired={required} onChange={(value) => onChange(name, value)} />;

  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={8}><Stack hAlign="center"><Stack as="main" width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / DOCUMENTS</Text><Heading level={1} type="display-1">Document library</Heading><Text as="p" color="secondary">Declared provenance and extraction notes stay attached to each original.</Text></Stack>
    {notice && <Text as="p" aria-live="polite">{notice}</Text>}
    {duplicateTarget && <Button type="button" label={`Open existing document: ${duplicateTarget.filename}`} variant="secondary" onClick={() => { void loadDocument(duplicateTarget.id); setDuplicateTarget(null); }} />}
    <Section variant="section" padding={5}><Stack gap={4}><Heading level={2}>Add a document</Heading>
      <form onSubmit={upload}><Stack gap={3}>
        <FileInput label="Document (PDF, DOC/DOCX, ODT, RTF, HTML, XML, Markdown, CSV, JSON, or text; max 20 MB)" value={uploadFile} onChange={(value) => setUploadFile(value instanceof File ? value : null)} accept=".pdf,.doc,.docx,.odt,.rtf,.txt,.text,.md,.markdown,.rst,.csv,.tsv,.json,.html,.htm,.xml,.yaml,.yml,.toml,.log,.tex,.ini,.conf" maxSize={20 * 1024 * 1024} isRequired />
        <Selector label="Provenance" htmlName="provenance" value={uploadMetadata.provenance} onChange={(value) => setUploadField("provenance", value)} isRequired options={["HUMAN", "AI_GENERATED", "AI_ASSISTED"]} />
        {field("language", "Language", uploadMetadata, setUploadField, true)}
        <Selector label="Author language background" htmlName="author_language_background" value={uploadMetadata.author_language_background} onChange={(value) => setUploadField("author_language_background", value)} isRequired options={["UNKNOWN", "NATIVE", "NON_NATIVE"]} />
        {field("domain", "Academic domain", uploadMetadata, setUploadField)}{field("genre", "Genre", uploadMetadata, setUploadField)}
        {uploadMetadata.provenance === "HUMAN" && <>{field("source", "Source", uploadMetadata, setUploadField, true)}{field("license", "License (or provide consent below)", uploadMetadata, setUploadField)}{field("consent", "Consent record", uploadMetadata, setUploadField)}</>}
        {uploadMetadata.provenance !== "HUMAN" && <>{field("generator_model", "Generator model", uploadMetadata, setUploadField, true)}{field("generator_version", "Generator version", uploadMetadata, setUploadField, true)}{uploadMetadata.provenance === "AI_GENERATED" ? field("prompt_reference", "Prompt reference", uploadMetadata, setUploadField, true) : field("editing_history", "Editing history", uploadMetadata, setUploadField, true)}</>}
        <Button type="submit" label={busy ? "Working…" : "Upload and extract"} variant="primary" isDisabled={busy} />
      </Stack></form>
    </Stack></Section>
    <Stack gap={3}><Heading level={2}>Documents · {visible.length}</Heading><Button type="button" label="Export CSV manifest" variant="secondary" onClick={exportManifest} /><form onSubmit={importManifest}><Stack gap={2}><FileInput label="CSV document manifest" value={manifestFile} onChange={(value) => setManifestFile(value instanceof File ? value : null)} accept=".csv,text/csv" isRequired /><Button type="submit" label="Import manifest" variant="secondary" /></Stack></form><TextInput label="Filter filename, provenance, or language" value={filter} onChange={(value) => setFilter(value)} placeholder="Search documents" />
      {visible.length === 0 ? <Text as="p" color="secondary">No documents yet. Upload a document above to begin.</Text> : <List header="Stored documents" density="compact" hasDividers>{visible.map((doc) => <ListItem key={doc.id} itemKey={doc.id} label={`${doc.filename} · ${doc.metadata.provenance} · ${doc.word_count} words`} onClick={() => void loadDocument(doc.id)} />)}</List>}
    </Stack>
    {selected && <Section variant="section" padding={5}><Stack gap={4}><Heading level={2}>{selected.filename}</Heading><Text as="p" type="supporting">SHA-256 · {selected.sha256}</Text>
      {selected.quality_flags.map((flag) => <Text key={flag.code} as="p" color="accent">Warning: {flag.message}</Text>)}
      {selected.duplicate_flags.map((flag) => <Text key={flag.document_id} as="p" color="accent">Near duplicate of {flag.filename} · Jaccard {flag.jaccard}</Text>)}
      <Heading level={3}>Manually imported Turnitin results</Heading>
      {turnitinReports.length === 0 ? <Text as="p" color="secondary">No Turnitin reports are attached to this document.</Text> : <Table<ImportedReportRow> idKey="id" density="compact" dividers="rows" data={turnitinReports.map((report) => ({
        id: report.id, submission: report.submission_reference, timestamp: report.report_timestamp,
        similarity: report.similarity.state === "value" ? `${report.similarity.raw} (${report.similarity.value}%)` : `${report.similarity.raw ?? ""} · ${report.similarity.state.replaceAll("_", " ")}`,
        aiWriting: report.ai_writing.state === "value" ? `${report.ai_writing.raw} (${report.ai_writing.value}%)` : `${report.ai_writing.raw} · ${report.ai_writing.state.replaceAll("_", " ")}`,
        eligibleWords: report.eligible_word_count, reportHash: report.report_file_sha256,
      }))} columns={[{ key: "submission", header: "Submission" }, { key: "timestamp", header: "Report timestamp" }, { key: "similarity", header: "Similarity · percentage" }, { key: "aiWriting", header: "AI writing · percentage" }, { key: "eligibleWords", header: "Eligible words" }, { key: "reportHash", header: "Original report SHA-256" }]} />}
      <Heading level={3}>Edit declared metadata</Heading>
      <form onSubmit={saveMetadata}><Stack gap={3}>
        <Selector label="Provenance" htmlName="provenance" value={editMetadata.provenance} onChange={(value) => setEditField("provenance", value)} options={["HUMAN", "AI_GENERATED", "AI_ASSISTED"]} />
        {field("language", "Language", editMetadata, setEditField, true)}
        <Selector label="Author language background" htmlName="author_language_background" value={editMetadata.author_language_background} onChange={(value) => setEditField("author_language_background", value)} options={["UNKNOWN", "NATIVE", "NON_NATIVE"]} />
        {(["domain", "genre", "source", "license", "consent", "generator_model", "generator_version", "prompt_reference", "editing_history"] as const).map((key) => <TextInput key={key} htmlName={key} label={key.replaceAll("_", " ")} value={editMetadata[key] ?? ""} onChange={(value) => setEditField(key, value)} />)}
        <Button type="submit" label="Save metadata" variant="primary" isDisabled={busy} /><Button type="button" label="Archive document" variant="secondary" onClick={() => void remove()} />
      </Stack></form>
      <Heading level={3}>Audit history</Heading>{audit.map((event, index) => <Text key={`${event.event_type}-${index}`} as="p">{event.event_type} · {new Date(event.created_at).toLocaleString()}</Text>)}
      <Heading level={3}>Extracted text by page</Heading>{selected.pages?.map((page, index) => <Section key={`${page.page}-${index}`} variant="section" padding={3}><Stack gap={2}><Text type="label">{page.page ? `Page ${page.page}` : "Document text"}</Text><pre>{page.text}</pre></Stack></Section>)}
    </Stack></Section>}
  </Stack></Stack></Section>;
}
