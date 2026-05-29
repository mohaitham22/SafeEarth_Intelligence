import type { Metadata, Viewport } from "next"
import "./globals.css"
import { S } from "@/lib/strings"
import { AuthBoot } from "@/components/AuthBoot"

export const metadata: Metadata = {
  title: S("app.title"),
  description: S("app.description"),
  manifest: "/manifest.json",
}

export const viewport: Viewport = {
  themeColor: "#0f172a",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthBoot>{children}</AuthBoot>
      </body>
    </html>
  )
}
