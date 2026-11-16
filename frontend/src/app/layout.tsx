// Copyright 2026 MIA contributors
// SPDX-License-Identifier: Apache-2.0
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { Theme } from "@astryxdesign/core/theme";
import { miaEditorialTheme } from "../mia-theme";
import { MiaShell } from "./mia-shell";

export const metadata = { title: "MIA · AI Writing Analysis", description: "Careful, locally run AI writing analysis with an open detector." };
export const viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" as const };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-theme="dark"><body><Theme theme={miaEditorialTheme} mode="dark"><MiaShell>{children}</MiaShell></Theme></body></html>;
}
