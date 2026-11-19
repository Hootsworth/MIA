import "./styles.css";

export const metadata = {
  title: "MIA Detector · Local text analysis",
  description: "Compare outputs from locally run open-weight AI-text detectors.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
