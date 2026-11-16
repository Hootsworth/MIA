"use client";

import { useEffect, useState } from "react";

type Health = { status: string; service: string };

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${base}/api/health`).then((response) => {
      if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
      return response.json() as Promise<Health>;
    }).then(setHealth).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Request failed"));
  }, []);

  return <main className="mx-auto min-h-screen max-w-4xl px-8 py-20">
    <p className="text-sm uppercase tracking-[0.2em] text-emerald-800">TurnOut · Research lab</p>
    <h1 className="mt-5 text-5xl font-semibold tracking-tight">Open detector evaluation</h1>
    <p className="mt-4 max-w-xl text-lg text-neutral-600">A transparent workspace for measuring what text detectors can and cannot tell us.</p>
    <section className="mt-12 rounded-xl border border-neutral-200 bg-white p-6" aria-live="polite">
      <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">Backend status</h2>
      <p className="mt-3 text-lg">{health ? `Connected · ${health.service}` : error ? `Unavailable · ${error}` : "Checking backend…"}</p>
    </section>
  </main>;
}
