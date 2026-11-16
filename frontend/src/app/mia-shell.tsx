// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { AppShell } from "@astryxdesign/core/AppShell";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TopNav } from "@astryxdesign/core/TopNav";
import NextLink from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Detector" },
  { href: "/detectors", label: "Method" },
  { href: "/documents", label: "History" },
  { href: "/reports", label: "Reports" },
  { href: "/experiments", label: "Research lab" },
];

export function MiaShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const topNav = <TopNav
    label="MIA navigation"
    heading={<Stack direction="horizontal" gap={1} vAlign="center"><Heading level={4}>MIA</Heading><Text type="label" color="accent">.</Text></Stack>}
    startContent={<Stack direction="horizontal" gap={4} wrap="wrap" aria-label="Primary navigation">
      {links.map((item) => <Link key={item.href} as={NextLink} href={item.href} isStandalone>{item.label}{pathname === item.href ? " ·" : ""}</Link>)}
    </Stack>}
    endContent={<Text type="supporting" color="secondary">Local analysis</Text>}
  />;
  return <AppShell height="auto" variant="section" contentPadding={0} topNav={topNav}>{children}</AppShell>;
}
