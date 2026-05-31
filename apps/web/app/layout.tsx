import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shinkai",
  description: "Long-running investment research agent"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
