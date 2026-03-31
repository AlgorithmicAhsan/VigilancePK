import type { Metadata } from "next";
import { Inter, Noto_Nastaliq_Urdu } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const urdu = Noto_Nastaliq_Urdu({ subsets: ["arabic"], weight: ["400", "700"], variable: "--font-urdu" });

export const metadata: Metadata = {
  title: "Vigilance-PK | Elite Human Rights Intel",
  description: "Advanced RAG Dashboard for Multilingual News Triage",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${urdu.variable}`}>
        {children}
      </body>
    </html>
  );
}
