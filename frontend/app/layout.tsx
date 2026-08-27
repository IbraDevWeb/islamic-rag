import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Athar — Recherche islamique sourcée",
    template: "%s — Athar",
  },
  description:
    "Athar est une interface de recherche documentaire islamique qui relie chaque synthèse aux passages originaux, à leur provenance et à leurs citations.",
  applicationName: "Athar",
  keywords: [
    "Athar",
    "recherche islamique",
    "bibliothèque islamique",
    "fiqh",
    "Ibn Rushd",
    "OpenITI",
    "RAG",
  ],
};

export const viewport: Viewport = {
  themeColor: "#0a2119",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
