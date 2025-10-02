import type { ReactNode } from "react";
import { Inter } from "next/font/google";

export const metadata = {
  title: "Claimscope",
  description: "Reproducing AI-lab claims with pinned, open harnesses.",
};

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className} style={{ background: "#0B0F14", color: "#E6EDF3", margin: 0 }}>
        {children}
      </body>
    </html>
  );
}
