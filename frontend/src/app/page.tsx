"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { Section } from "@astryxdesign/core/Section";
import { Stack } from "@astryxdesign/core/Stack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
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

  const statusLabel = health ? "Backend connected" : error ? "Backend unavailable" : "Checking backend";
  const statusVariant = health ? "success" : error ? "error" : "warning";

  return <Section width="100%" minHeight="100vh" paddingInline={6} paddingBlock={10}>
    <Stack hAlign="center">
      <Stack as="main" width="100%" maxWidth="68rem" gap={8}>
        <Stack as="header" gap={3}>
          <Text type="label" color="accent">MIA · RESEARCH LAB / 01</Text>
          <Heading level={1} type="display-1" textWrap="balance">Open detector evaluation</Heading>
          <Text as="p" type="large" color="secondary" maxLines={3}>
            A careful, evidence-led workspace for measuring what AI-writing detectors can and cannot tell us.
          </Text>
        </Stack>

        <section aria-live="polite">
          <Section variant="section" padding={5}>
            <Stack gap={3}>
              <Text type="label" color="secondary">SYSTEM STATUS</Text>
              <Stack direction="horizontal" gap={2} align="center" wrap="wrap">
                <StatusDot variant={statusVariant} label={statusLabel} isPulsing={!health && !error} />
                <Heading level={2}>{health ? "Backend connected" : error ? "Backend unavailable" : "Checking connection"}</Heading>
              </Stack>
              <Text as="p" color="secondary">
                {health ? `Live health check · ${health.service}` : error ? error : "Waiting for the API health check to respond."}
              </Text>
            </Stack>
          </Section>
        </section>

        <Text as="p" type="supporting" color="secondary">
          Research infrastructure for transparency, reproducibility, and honest limitations.
        </Text>
        <Stack direction="horizontal" gap={4} wrap="wrap">
          <Link href="/documents" isStandalone>Open document library</Link>
          <Link href="/detectors" isStandalone>Inspect detector registry</Link>
          <Link href="/experiments" isStandalone>Plan an experiment</Link>
        </Stack>
      </Stack>
    </Stack>
  </Section>;
}
