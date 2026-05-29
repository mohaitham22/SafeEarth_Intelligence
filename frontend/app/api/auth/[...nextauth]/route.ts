// NextAuth v5 route handler — re-exports the GET and POST handlers exported
// from frontend/auth.ts. Do not add logic here.

import { handlers } from "@/auth"

export const { GET, POST } = handlers
export const dynamic = "force-dynamic"
