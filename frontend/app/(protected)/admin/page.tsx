// Admin panel — /admin (Admin role only)
// Sections: All Users (paginated, GET /admin/users), Role management (PATCH /admin/users/{id}),
//           ML model stats (GET /admin/model-stats), Manual alert trigger (POST /admin/alerts/trigger)
// Protected by Next.js middleware + server-side role check — non-admins get 403.

import { S } from "@/lib/strings"

export default function AdminPage() {
  return (
    <main className="max-w-6xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold text-slate-800">{S("page.admin.title")}</h1>
      <p className="mt-2 text-slate-500">{S("common.placeholder")}</p>
    </main>
  )
}
