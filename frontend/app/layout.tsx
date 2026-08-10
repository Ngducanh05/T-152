import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "ParkSmart AI — Trợ lý đỗ xe thông minh",
  description: "Demo end-to-end cho hệ thống trợ lý đỗ xe ParkSmart AI.",
  openGraph: {
    title: "ParkSmart AI",
    description: "Tìm đúng chỗ. Đỗ xe nhẹ nhàng.",
    locale: "vi_VN",
    type: "website",
    images: [{ url: "/og.png", width: 1731, height: 909, alt: "ParkSmart AI — Tìm đúng chỗ. Đỗ xe nhẹ nhàng." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ParkSmart AI",
    description: "Tìm đúng chỗ. Đỗ xe nhẹ nhàng.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
