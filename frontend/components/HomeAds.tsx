// Home-page ads shown to guests (the "guest + free" bucket — see HomeForecastSection).
// Content comes from the backend `ads` table (admin-managed via the Studio panel
// in Phase 10); the home page fetches it server-side and passes it in.
//
// If there are no active ads, falls back to the sign-up forecast teaser so the
// section is never empty and still carries a call to action.

import Link from "next/link"
import { S } from "@/lib/strings"
import { ForecastTeaser } from "@/components/ForecastTeaser"
import type { Ad } from "@/types"

export function HomeAds({ ads }: { ads: Ad[] }) {
  if (!ads || ads.length === 0) return <ForecastTeaser />

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        {S("home.ads.eyebrow")}
      </p>
      <h2 className="mt-1 text-lg font-semibold text-slate-800">
        {S("home.ads.title")}
      </h2>

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
        {ads.map((ad) => (
          <AdCard key={ad.id} ad={ad} />
        ))}
      </div>
    </section>
  )
}

function AdCard({ ad }: { ad: Ad }) {
  const isExternal = !!ad.link_url && /^https?:\/\//i.test(ad.link_url)

  const inner = (
    <>
      {ad.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={ad.image_url}
          alt=""
          className="mb-3 h-32 w-full rounded-lg object-cover"
        />
      )}
      <h3 className="font-semibold text-slate-800">{ad.title}</h3>
      {ad.body && <p className="mt-2 text-sm text-slate-600">{ad.body}</p>}
      {ad.link_url && (
        <span className="mt-4 inline-flex items-center text-sm font-medium text-slate-800">
          {ad.cta_label || S("home.ads.defaultCta")} →
        </span>
      )}
    </>
  )

  const cardCls =
    "block rounded-xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"

  if (!ad.link_url) {
    return <div className={cardCls}>{inner}</div>
  }
  if (isExternal) {
    return (
      <a href={ad.link_url} target="_blank" rel="noopener noreferrer" className={cardCls}>
        {inner}
      </a>
    )
  }
  return (
    <Link href={ad.link_url} className={cardCls}>
      {inner}
    </Link>
  )
}
