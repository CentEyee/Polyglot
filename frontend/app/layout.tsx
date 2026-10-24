import "./globals.css";

export const metadata = {
  title: "PolyGlot Refactor AI",
  description: "Autonomous C → Rust migrations that arrive as reviewable pull requests",
};

export const viewport = { themeColor: "#050505" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
