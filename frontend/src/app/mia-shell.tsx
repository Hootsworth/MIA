// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
"use client";

import { AppShell } from "@astryxdesign/core/AppShell";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { SideNav, SideNavHeading, SideNavItem, SideNavSection } from "@astryxdesign/core/SideNav";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TopNav } from "@astryxdesign/core/TopNav";
import { usePathname } from "next/navigation";
import NextLink from "next/link";

const navigation = [
  { title: "Workspace", items: [{ href: "/", label: "Analyze" }, { href: "/documents", label: "Documents" }] },
  { title: "Evaluation", items: [{ href: "/detectors", label: "Detectors" }, { href: "/experiments", label: "Experiments" }, { href: "/analysis", label: "Analysis" }] },
  { title: "Reports", items: [{ href: "/turnitin-reports", label: "Turnitin imports" }, { href: "/reports", label: "Research reports" }] },
];

const pageNames: Record<string, string> = {
  "/": "Analyze",
  "/documents": "Documents",
  "/detectors": "Detectors",
  "/experiments": "Experiments",
  "/analysis": "Analysis",
  "/turnitin-reports": "Turnitin imports",
  "/reports": "Research reports",
};

export function MiaShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const pageName = pageNames[pathname] ?? "MIA workspace";

  const sideNav = <SideNav
    aria-label="MIA primary navigation"
    header={<SideNavHeading heading="MIA" superheading="OPEN DETECTOR LAB" subheading="Research workspace" headingHref="/" />}
    footer={<Stack gap={1}><Text type="label" color="secondary">RESEARCH NOTE</Text><Text type="supporting" color="secondary">Detector output describes model behavior; it does not establish authorship.</Text></Stack>}
    collapsible={{ defaultIsCollapsed: false, buttonLabel: "Collapse primary navigation" }}>
    {navigation.map((group) => <SideNavSection key={group.title} title={group.title}>
      {group.items.map((item) => <SideNavItem
        key={item.href}
        as={NextLink}
        href={item.href}
        label={item.label}
        isSelected={pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`))}
      />)}
    </SideNavSection>)}
  </SideNav>;

  const topNav = <TopNav
    label="MIA workspace toolbar"
    heading={<Stack direction="horizontal" gap={3} vAlign="center">
      <Heading level={4}>{pageName}</Heading>
    </Stack>}
    endContent={<Link href="/" isStandalone>New analysis</Link>}
  />;

  return <AppShell height="auto" variant="section" contentPadding={0} sideNav={sideNav} topNav={topNav}>{children}</AppShell>;
}
