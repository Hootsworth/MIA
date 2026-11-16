// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { Section } from "@astryxdesign/core/Section";
import { Selector } from "@astryxdesign/core/Selector";
import { Stack } from "@astryxdesign/core/Stack";
import { Table } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Experiment = { id: string; name: string; status: string };
type Report = { id: string; experiment_id: string; created_at: string; markdown_sha256: string; csv_sha256: string; analysis: { experiment_name?: string; detectors?: { key: string; n: number; metrics: Record<string, number | null> }[] }; markdown_url: string; csv_url: string };
type ReportRow = { id: string; experiment: string; created: string; observations: string; estimates: string; files: string; integrity: string };

export default function ReportsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [notice, setNotice] = useState("Loading report archive…");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [experimentResponse, reportResponse] = await Promise.all([fetch(`${API}/api/experiments`), fetch(`${API}/api/reports`)]);
    if (!experimentResponse.ok || !reportResponse.ok) throw new Error("MIA could not load experiments and reports.");
    const experimentRows = await experimentResponse.json() as Experiment[];
    const reportRows = await reportResponse.json() as Report[];
    const completed = experimentRows.filter((row) => row.status === "COMPLETED");
    setExperiments(completed);
    setReports(reportRows);
    setSelectedId((current) => current || completed[0]?.id || "");
    setNotice(reportRows.length ? `${reportRows.length} generated report${reportRows.length === 1 ? "" : "s"} in this local archive.` : "No generated reports yet.");
  }, []);

  useEffect(() => { void refresh().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Could not load report archive.")); }, [refresh]);

  async function generate() {
    if (!selectedId) return;
    setBusy(true); setNotice("Generating Markdown and raw CSV from stored experiment results…");
    try {
      const response = await fetch(`${API}/api/experiments/${selectedId}/reports`, { method: "POST" });
      const body = await response.json() as Report & { detail?: string | { message?: string } };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? "Report generation failed.");
      await refresh();
      setNotice(`Report saved for ${body.analysis.experiment_name ?? "the selected experiment"}. Both files were generated from persisted outputs.`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Report generation failed."); }
    finally { setBusy(false); }
  }

  const rows: ReportRow[] = useMemo(() => reports.map((report) => ({
    id: report.id,
    experiment: report.analysis.experiment_name ?? report.experiment_id,
    created: new Date(report.created_at).toLocaleString(),
    observations: (report.analysis.detectors ?? []).map((row) => `${row.key}: n=${row.n}`).join(" · ") || "No numeric estimates",
    estimates: (report.analysis.detectors ?? []).map((row) => `${row.key} · ${Object.entries(row.metrics).map(([name, value]) => `${name} ${typeof value === "number" ? value.toFixed(3) : "—"}`).join(", ")}`).join("; ") || "—",
    files: report.id,
    integrity: `MD ${report.markdown_sha256?.slice(0, 12) ?? "—"} · CSV ${report.csv_sha256?.slice(0, 12) ?? "—"}`,
  })), [reports]);

  return <Section width="100%" paddingInline={5} paddingBlock={6}><Stack hAlign="center"><Stack width="100%" maxWidth="76rem" gap={6}>
    <Stack as="header" gap={2}><Text type="label" color="accent">MIA · RESEARCH LAB / REPORTS</Text><Heading level={1} type="display-1">Research reports</Heading><Text as="p" color="secondary">Generate and download reproducible Markdown summaries and CSV exports from completed experiment data.</Text></Stack>
    <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Create a report</Heading><Text as="p" color="secondary">MIA uses the frozen experiment protocol and stored result rows. It does not fabricate missing values or re-run detector inference.</Text>
      {experiments.length > 0 ? <><Selector label="Completed experiment" value={selectedId} onChange={setSelectedId} options={experiments.map((row) => ({ value: row.id, label: row.name }))} /><Button type="button" label={busy ? "Generating report…" : "Generate Markdown + CSV"} variant="primary" isDisabled={busy || !selectedId} onClick={() => void generate()} /></> : <Text as="p">No completed experiments are ready to report. Complete an experiment with an analyzable M6 protocol first.</Text>}
    </Stack></Section>
    <Text as="p" aria-live="polite" color="secondary">{notice}</Text>
    <Section variant="section" padding={5}><Stack gap={3}><Heading level={2}>Saved reports</Heading>
      {rows.length ? <Table<ReportRow> idKey="id" density="compact" dividers="rows" data={rows} columns={[
        { key: "experiment", header: "Experiment" }, { key: "created", header: "Generated" },
        { key: "observations", header: "Scored observations" }, { key: "estimates", header: "Stored estimates" },
        { key: "integrity", header: "SHA-256 · shortened" },
        { key: "files", header: "Downloads", renderCell: (row) => <Stack direction="horizontal" gap={3} wrap="wrap"><Link href={`${API}/api/reports/${row.id}/markdown`} isExternalLink isStandalone>Markdown</Link><Link href={`${API}/api/reports/${row.id}/csv`} isExternalLink isStandalone>CSV</Link></Stack> },
      ]} /> : <Text as="p">The archive is empty. Generated reports will appear here with file digests and downloads.</Text>}
    </Stack></Section>
    <Text as="p" color="secondary">Reports are stored locally under <code>storage/reports/generated/</code>. The CSV contains observed outputs, including failures and typed censored values; it does not contain original document files.</Text>
  </Stack></Stack></Section>;
}
