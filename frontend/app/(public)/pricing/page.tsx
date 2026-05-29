// Public pricing page — /pricing (CLAUDE.md Feature 8).
// Server Component. Plan numbers come from the pre-seeded `premium_plans`
// rows in alembic/versions/a3f1d2e4b5c6_initial_schema.py — there is no
// public /premium/plans endpoint yet (Phase 7 will add the real checkout
// flow). If the seed numbers change, update the i18n keys below to match.

import Link from "next/link"
import { Nav } from "@/components/Nav"
import { CheckoutButton } from "@/components/CheckoutButton"
import { S } from "@/lib/strings"

const MONTHLY_FEATURES = [
  S("pricing.monthly.feature1"),
  S("pricing.monthly.feature2"),
  S("pricing.monthly.feature3"),
]

const YEARLY_FEATURES = [
  S("pricing.yearly.feature1"),
  S("pricing.yearly.feature2"),
  S("pricing.yearly.feature3"),
]

export default function PricingPage() {
  return (
    <>
      <Nav />
      <main className="max-w-5xl mx-auto px-4 py-12">
        <h1 className="text-3xl font-bold text-slate-800">{S("pricing.title")}</h1>
        <p className="mt-2 text-sm text-slate-500 max-w-2xl">{S("pricing.subtitle")}</p>

        <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-6">
          <PlanCard
            name={S("pricing.monthly.name")}
            price={S("pricing.monthly.price")}
            cadence={S("pricing.monthly.cadence")}
            features={MONTHLY_FEATURES}
            cta={S("pricing.monthly.cta")}
            planName="monthly"
          />
          <PlanCard
            name={S("pricing.yearly.name")}
            price={S("pricing.yearly.price")}
            cadence={S("pricing.yearly.cadence")}
            equivalent={S("pricing.yearly.equivalent")}
            badge={S("pricing.yearly.save")}
            features={YEARLY_FEATURES}
            cta={S("pricing.yearly.cta")}
            planName="yearly"
            highlight
          />
        </div>

        <section className="mt-12 rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="font-semibold text-slate-800">{S("pricing.free.title")}</h2>
          <p className="mt-1 text-sm text-slate-600">{S("pricing.free.body")}</p>
          <Link
            href="/register"
            className="mt-4 inline-flex items-center rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {S("nav.register")}
          </Link>
        </section>

        <p className="mt-6 text-xs text-slate-400">{S("pricing.note")}</p>
      </main>
    </>
  )
}

function PlanCard(props: {
  name:        string
  price:       string
  cadence:     string
  equivalent?: string
  badge?:      string
  features:    string[]
  cta:         string
  planName:    "monthly" | "yearly"
  highlight?:  boolean
}) {
  return (
    <div
      className={`relative rounded-2xl border p-6 ${
        props.highlight
          ? "border-slate-800 bg-white shadow-md"
          : "border-slate-200 bg-white"
      }`}
    >
      {props.badge && (
        <span className="absolute -top-3 right-4 inline-flex items-center rounded-full bg-emerald-500 px-3 py-1 text-xs font-semibold text-white shadow">
          {props.badge}
        </span>
      )}

      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {props.name}
      </h3>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-4xl font-bold text-slate-900">{props.price}</span>
        <span className="text-sm text-slate-500">{props.cadence}</span>
      </div>
      {props.equivalent && (
        <p className="mt-1 text-xs text-emerald-700 font-medium">{props.equivalent}</p>
      )}

      <ul className="mt-6 space-y-2 text-sm text-slate-700">
        {props.features.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <span
              aria-hidden
              className="mt-1.5 h-1.5 w-1.5 rounded-full bg-slate-500 shrink-0"
            />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <CheckoutButton
        planName={props.planName}
        label={props.cta}
        highlight={props.highlight}
      />
    </div>
  )
}
