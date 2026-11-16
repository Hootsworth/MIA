# MIA design direction

`Demo.html` is the current visual reference for MIA. It supersedes the earlier Ollama theme direction. Keep the design quiet, editorial, and document-first.

## Visual system

- Warm parchment page: `#f7f5f1`; near-black text: `#1b1b19`; muted text: `#8a877f`; fine borders: `#e2dfd8`; white-warm surfaces: `#fffefb`.
- Burnt orange accent: `#c2410c` in light mode and a readable warm orange in dark mode.
- Fraunces for display headings and Inter for interface text. Load fonts from the local `@fontsource` packages; do not fetch them from Google Fonts at runtime.
- Use generous whitespace, a centered reading column around 760px, thin separators, simple surfaces, and rounded upload areas. Primary actions are pill-shaped.
- Navigation belongs across the top. Keep the first-use flow focused on adding a document, recording the minimum required permission confirmation, and generating a report.
- Support system light and dark appearance.

## Product and research boundaries

- MIA processes uploaded documents through its local backend and local storage. Do not repeat the demo's browser-only processing claim.
- Never infer provenance or author language background. One-off analysis may keep provenance `UNKNOWN`; language identification is a separate best-effort document-level detection.
- Present the persisted detector output using its actual score semantics. Never turn a raw score into a probability or describe it as proof of authorship.
- Do not invent document maps, highlighted signals, explanations, or confidence summaries unless the detector actually produces those data and the UI labels them accurately.
- Keep the non-authorship limitation visible, especially in generated reports.

## Implementation

- Use the installed Astryx components and the generated `mia-editorial` theme. Extend the imported theme with `defineTheme` when changing tokens; do not hand-edit generated files.
- Keep forms concise. Advanced research metadata belongs on the research workflows, not in the ordinary one-document analysis path.
- Empty states are preferable to sample or mock data.
