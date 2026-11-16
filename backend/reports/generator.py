# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Render reproducible Markdown and raw-result CSV from persisted MIA outputs."""

import csv
import io
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone


def _display(value):
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_display(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


def git_revision(root):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return result.stdout.strip()


def render_report(experiment, analysis, commit_sha):
    protocol = experiment.protocol or {}
    documents = protocol.get("document_snapshot", [])
    provenance_counts = Counter(item.get("provenance") or "unknown" for item in documents)
    detector_versions = protocol.get("detector_snapshot", [])
    metrics_by_detector = {item["detector"]: item for item in analysis.get("detectors", [])}

    lines = [
        f"# {experiment.name}",
        "",
        "## Research question and protocol",
        "",
        f"- Research question: {protocol.get('research_question', 'not recorded')}",
        f"- Hypothesis: {_display(protocol.get('hypothesis', 'not recorded'))}",
        f"- Status: {experiment.status}",
        f"- Classification rule: {_display(analysis.get('classification_rule'))}",
        f"- Requested metrics: {', '.join(analysis.get('metrics_requested', [])) or 'none'}",
        f"- Protocol version: {analysis.get('protocol_version', 'not recorded')}",
        f"- Conditions: {_display(protocol.get('conditions', {}))}",
        "",
        "## Dataset snapshot",
        "",
        f"Documents in frozen snapshot: **{len(documents)}**.",
        "",
        _table(["Declared provenance", "Documents"], sorted(provenance_counts.items())),
        "",
        _table(
            ["Document ID", "Filename", "SHA-256", "Words", "Provenance"],
            [[item.get("id"), item.get("filename"), item.get("sha256"), item.get("word_count"), item.get("provenance")] for item in documents],
        ),
        "",
        "## Detector versions",
        "",
        _table(["Detector", "Model", "Revision", "Score semantics"], [[item.get("key"), item.get("model_id"), item.get("revision"), item.get("score_semantics")] for item in detector_versions]),
        "",
        "## Results",
        "",
    ]

    if not metrics_by_detector:
        lines.append("No numeric detector estimates are available for this experiment.")
        lines.append("")
    else:
        for key, result in metrics_by_detector.items():
            lines.extend([f"### {key}", "", f"n = {result.get('n', 0)}; positive n = {result.get('positive_n', 0)}; negative n = {result.get('negative_n', 0)}.", ""])
            metric_rows = []
            for name, value in (result.get("metrics") or {}).items():
                ci = (result.get("confidence_intervals") or {}).get(name)
                interval = f"[{ci['lower']}, {ci['upper']}]" if ci else "—"
                metric_rows.append([name, value, interval])
            lines.append(_table(["Metric", "Estimate", "95% bootstrap CI"], metric_rows) if metric_rows else "No requested metric could be estimated.")
            lines.append("")
            if result.get("excluded"):
                lines.append(f"Excluded outputs: {_display(result['excluded'])} (counted separately, not converted to zero).")
                lines.append("")
            for dimension, cells in (result.get("subgroups") or {}).items():
                lines.extend([f"#### Subgroup: {dimension}", ""])
                rows = []
                for cell in cells:
                    for name, value in (cell.get("metrics") or {}).items():
                        ci = (cell.get("confidence_intervals") or {}).get(name)
                        rows.append([cell.get("value"), cell.get("n"), "yes" if cell.get("unreliable") else "no", name, value,
                        f"[{ci['lower']}, {ci['upper']}]" if ci else "—"])
                lines.append(_table(["Group", "n", "n below floor", "Metric", "Estimate", "95% CI"], rows) if rows else "No subgroup estimates available.")
                lines.append("")

    limitations = []
    if any(item.get("n", 0) < 30 for item in metrics_by_detector.values()):
        limitations.append("At least one detector estimate has fewer than 30 observations; treat it as unreliable and descriptive.")
    semantics = {item.get("key"): item.get("score_semantics") for item in detector_versions}
    if any(value != "probability" for value in semantics.values()):
        limitations.append("Scores whose detector semantics are not probability are not probabilities of authorship.")
    if any((item.get("excluded") or {}).get("censored", 0) for item in metrics_by_detector.values()):
        limitations.append("Censored observations are reported separately in raw exports and excluded from numeric estimates.")
    limitations.append("Declared provenance is metadata, not independently verified authorship.")
    limitations.append("Detector outputs describe model behavior and are not proof of who wrote a document.")
    lines.extend(["## Limitations", "", *[f"- {item}" for item in limitations], ""])

    lines.extend([
        "## Reproducibility",
        "",
        f"- Experiment ID: {experiment.id}",
        f"- Seed: {protocol.get('seed', 'not recorded')}",
        f"- Analysis bootstrap replicates: {analysis.get('bootstrap_replicates', 'not recorded')}",
        f"- Git commit: {commit_sha}",
        f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}",
        "- Document and extracted-text hashes are listed in the dataset snapshot table.",
        "",
        "Generated from persisted experiment outputs by MIA. Bootstrap calculations use the frozen seed and analysis settings shown above.",
        "",
    ])
    return "\n".join(lines)


def render_raw_csv(experiment, document_rows, detector_versions):
    docs = {row.get("id"): row for row in (experiment.protocol or {}).get("document_snapshot", [])}
    version_keys = {row.get("version_id"): row.get("key") for row in detector_versions}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["result_id", "document_id", "filename", "provenance", "detector", "score", "score_semantics", "score_state", "raw_display", "label", "raw_output_json", "created_at", "error"])
    for row in document_rows:
        doc = docs.get(row.get("document_id"), {})
        result = row.get("output") or {}
        writer.writerow([row.get("id"), row.get("document_id"), doc.get("filename"), doc.get("provenance"),
                         row.get("detector") or version_keys.get(row.get("detector_version_id"), "unknown"), result.get("score"),
                         result.get("score_semantics"), result.get("score_state", "missing" if result.get("error") else "value"),
                         result.get("raw_display"), result.get("label"),
                         json.dumps(result.get("raw_output"), sort_keys=True, ensure_ascii=False), row.get("created_at"), row.get("error")])
    return output.getvalue()


def render_document_report(document, result, commit_sha):
    metadata = document.metadata_json or {}
    declared = metadata.get("declared", {})
    detection = metadata.get("language_detection", {})
    output = result.output or {}
    score = output.get("score")
    lines = [
        f"# MIA analysis: {document.filename}", "",
        "## Document", "",
        f"- Filename: {document.filename}", f"- SHA-256: {document.sha256}",
        f"- Extracted word count: {metadata.get('word_count', 0)}",
        f"- Language: {detection.get('name', declared.get('language', 'unknown'))} ({detection.get('status', 'unknown')})",
        f"- Language detector confidence: {_display(detection.get('confidence'))}",
        f"- Provenance: {declared.get('provenance', 'UNKNOWN')} (declared metadata; not inferred)", "",
        *( [f"Uploader context: {declared.get('context')}", ""] if declared.get("context") else [] ),
        "## Detector output", "",
        f"- Detector: {output.get('model_id', 'RoBERTa OpenAI Detector')}",
        f"- Revision: {output.get('revision', 'unknown')}",
        f"- Label: {_display(output.get('label'))}",
        f"- Raw score: {_display(score)}", f"- Score semantics: {output.get('score_semantics', 'unknown')}",
        f"- Device: {_display(output.get('device'))}", f"- Duration (ms): {_display(output.get('duration_ms'))}",
        f"- Raw output: {_display(output.get('raw_output', {}))}", "",
        "## Limitations", "",
        "This is a single detector result, not a calibrated probability or proof of authorship. The model was trained to distinguish GPT-2 outputs from WebText and may perform differently on modern generators, domains, or language varieties. Do not use this output as the sole basis for a consequential decision.",
        "",
        "## Reproducibility", "",
        f"- Document ID: {document.id}", f"- Result ID: {result.id}",
        f"- Experiment ID: {result.experiment_id}", f"- Git commit: {commit_sha}",
        f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}",
        "- This report was generated from the persisted MIA result; it does not add or infer evidence.", "",
    ]
    return "\n".join(lines)


def render_document_csv(document, result):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    row = result.output or {}
    writer.writerow(["document_id", "filename", "sha256", "word_count", "language", "provenance", "detector", "revision", "label", "raw_score", "score_semantics", "device", "duration_ms", "result_id", "experiment_id"])
    writer.writerow([document.id, document.filename, document.sha256, (document.metadata_json or {}).get("word_count"),
                     ((document.metadata_json or {}).get("language_detection") or {}).get("name"),
                     ((document.metadata_json or {}).get("declared") or {}).get("provenance", "UNKNOWN"),
                     row.get("model_id"), row.get("revision"), row.get("label"), row.get("score"),
                     row.get("score_semantics"), row.get("device"), row.get("duration_ms"), result.id, result.experiment_id])
    return output.getvalue()
