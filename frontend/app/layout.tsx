import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "refer — 논문 인용·레퍼런스 검토",
  description:
    "DOCX/HWP/HWPX 논문의 인용↔참고문헌 정합성, APA 7판 변환, DOI 실재 검증을 자동화하는 멀티 에이전트 도구.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
