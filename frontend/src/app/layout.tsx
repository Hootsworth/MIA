import "./globals.css";

export const metadata = { title: "TurnOut Lab", description: "Open detector evaluation lab" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
