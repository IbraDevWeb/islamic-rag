import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Athar — Recherche islamique sourcée",
  description:
    "Interface de recherche documentaire pour le corpus Islamic RAG, avec preuves et citations traçables.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
