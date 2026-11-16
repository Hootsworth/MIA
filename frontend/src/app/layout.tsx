import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { Theme } from "@astryxdesign/core/theme";
import { miaEditorialTheme } from "../mia-theme";

export const metadata = { title: "MIA Lab", description: "Open detector evaluation lab" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-theme="dark"><body><Theme theme={miaEditorialTheme} mode="dark">{children}</Theme></body></html>;
}
