import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { Heading } from "@astryxdesign/core/Heading";
import { Link } from "@astryxdesign/core/Link";
import { Section } from "@astryxdesign/core/Section";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { Theme } from "@astryxdesign/core/theme";
import { miaEditorialTheme } from "../mia-theme";

export const metadata = { title: "MIA · AI Writing Analysis", description: "Careful, locally run AI writing analysis with an open detector." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-theme="dark"><body><Theme theme={miaEditorialTheme} mode="dark">
    <Section width="100%" paddingInline={6} paddingBlock={3}>
      <Stack hAlign="center">
        <Stack as="header" direction="horizontal" width="100%" maxWidth="76rem" hAlign="between" vAlign="center" gap={4} wrap="wrap">
          <Link href="/" isStandalone><Stack gap={0.5}><Heading level={3}>MIA</Heading><Text type="label" color="secondary">OPEN TEXT ANALYSIS</Text></Stack></Link>
          <Stack as="nav" direction="horizontal" gap={4} wrap="wrap" aria-label="Main navigation">
            <Link href="/" isStandalone>Analyze</Link>
            <Link href="/documents" isStandalone>Documents</Link>
            <Link href="/detectors" isStandalone>Detectors</Link>
            <Link href="/experiments" isStandalone>Experiments</Link>
            <Link href="/turnitin-reports" isStandalone>Reports</Link>
          </Stack>
        </Stack>
      </Stack>
    </Section>
    {children}
  </Theme></body></html>;
}
