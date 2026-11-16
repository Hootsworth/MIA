// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { Theme } from "@astryxdesign/core/theme";
import { defaultThemeSlug, themes } from "../astryx-themes";
import { MiaShell } from "./mia-shell";

export const metadata = { title: "MIA · AI Writing Analysis", description: "Careful, locally run AI writing analysis with an open detector." };
export const viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" as const };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Theme theme={themes[defaultThemeSlug]} mode="system"><MiaShell>{children}</MiaShell></Theme></body></html>;
}
