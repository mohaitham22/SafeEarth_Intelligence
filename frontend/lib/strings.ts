// i18n string-keys module.
// No UI string in this project may be hardcoded. All user-visible text MUST
// be looked up here by key. v1 ships English only; v2 will swap this map
// for locale-aware loading without touching call sites.
//
// Usage: import { S } from "@/lib/strings"  →  S("page.home.title")
//        import { Sf } from "@/lib/strings" →  Sf("page.home.events", {n: "1,234"})
// Unknown key returns "[missing: <key>]" so it's obvious in the UI.

const STRINGS_EN: Record<string, string> = {
  // App
  "app.title": "SafeEarth Intelligence",
  "app.description":
    "Predict natural disasters, estimate impact, and get AI-powered safety recommendations.",

  // Nav
  "nav.brand":          "SafeEarth",
  "nav.map":            "Risk Map",
  "nav.analytics":      "Analytics",
  "nav.pricing":        "Pricing",
  "nav.login":          "Log In",
  "nav.register":       "Sign Up",
  "nav.dashboard":      "Dashboard",
  "nav.admin":          "Admin",
  "nav.logout":         "Log out",
  "nav.role.guest":     "Guest",
  "nav.role.subscriber":"Subscriber",
  "nav.role.premium":   "Premium",
  "nav.role.admin":     "Admin",

  // Page placeholders (kept until each page is built)
  "page.home.title": "Home",
  "page.map.title": "Risk Map",
  "page.analytics.title": "Global Analytics",
  "page.pricing.title": "Pricing",
  "page.login.title": "Log In",
  "page.register.title": "Create Account",
  "page.dashboard.title": "Dashboard",
  "page.forecast.title": "30-Day Forecast",
  "page.admin.title": "Admin",
  "common.placeholder": "Placeholder — implementation pending",

  // Home — hero
  "home.hero.eyebrow":  "Open natural-disaster intelligence",
  "home.hero.title":    "Know what's coming. Prepare before it hits.",
  "home.hero.subtitle":
    "ML-powered disaster predictions, impact estimates, 30-day forecasts, and a live global risk map — for any region on Earth, backed by official EM-DAT data.",
  "home.hero.ctaPrimary":   "Create free account",
  "home.hero.ctaSecondary": "Explore risk map",

  // Home — summary stat cards
  // Sources: totalEvents from /regions/continent-stats (sum of total_events, full 1900-2021 range)
  //          totalDeaths from /regions/timeseries (sum of by_year deaths, non-null)
  //          coverage from /regions/timeseries (by_decade first decade → by_year last year)
  //          topType from /regions/trends (argmax of per-type decade sums)
  //          typeCount from /regions/trends (count of disaster-type keys)
  "home.summary.title":       "By the numbers",
  "home.summary.totalEvents": "Disaster events recorded",
  "home.summary.totalDeaths": "Deaths tracked in EM-DAT",
  "home.summary.coverage":    "Historical coverage",
  "home.summary.topType":     "Most common disaster",
  "home.summary.typeCount":   "Disaster types modelled",
  "home.summary.note":        "Computed from /regions/continent-stats, /regions/timeseries, and /regions/trends — cached hourly.",
  // Legacy keys kept for any stale references
  "home.summary.events":      "Disaster events tracked (1950-2020)",
  "home.summary.types":       "Disaster types modelled",
  "home.summary.regions":     "Continents covered",

  // Home — trends insight (CLAUDE.md Feature 2 headline)
  "home.trends.title":     "Floods are accelerating",
  "home.trends.insight":   "Recorded floods grew 3.3x in 20 years — from 524 events in the 1980s to 1,725 in the 2000s.",
  "home.trends.cta":       "See global analytics",

  // Home — insurance insight (CLAUDE.md Feature 2 headline)
  "home.insurance.title":   "The insurance gap is real",
  "home.insurance.insight": "Only 17% of earthquake damage and 26% of flood damage is insured globally. Most losses fall on households.",
  "home.insurance.cta":     "See insurance gap",

  // Home — forecast teaser (Feature 10)
  "home.forecast.title":     "30-Day Forecast",
  "home.forecast.body":
    "Day-by-day disaster risk for any region. Predicts severity, peak risk windows, and the most likely disaster type for the next 30 days.",
  "home.forecast.locked":    "Sign up to unlock",
  "home.forecast.cta":       "Create free account",
  "home.forecast.disclaimer":
    "Forecast based on historical patterns and seasonal trends — not live weather data.",

  // Home — features grid (links out to pages already scaffolded)
  "home.features.title":           "Explore the platform",
  "home.features.map.title":       "Global Risk Map",
  "home.features.map.body":        "Click any point on the map to see the dominant disaster type and risk score for that location.",
  "home.features.analytics.title": "Global Analytics",
  "home.features.analytics.body":  "Trends per decade, continent comparison, insurance gap, and time-series — all from EM-DAT.",
  "home.features.pricing.title":   "Premium",
  "home.features.pricing.body":    "$5/month or $48/year. Rich-HTML email alerts on Critical-severity risk for up to 10 regions.",

  // Home — footer
  "home.footer.tagline": "Free, open, and built on official EM-DAT history.",

  // Auth — shared
  "auth.email.label":           "Email",
  "auth.email.placeholder":     "you@example.com",
  "auth.password.label":        "Password",
  "auth.password.placeholder":  "At least 8 characters",
  "auth.fullName.label":        "Full name",
  "auth.fullName.placeholder":  "Jane Doe (optional)",
  "auth.confirm.label":         "Confirm password",

  // Auth — login
  "auth.login.title":      "Welcome back",
  "auth.login.subtitle":   "Log in to manage subscriptions, predictions, and the 30-day forecast.",
  "auth.login.submit":     "Log in",
  "auth.login.busy":       "Logging in...",
  "auth.login.noAccount":  "Don't have an account?",
  "auth.login.signupLink": "Create one",
  "auth.error.invalid":    "Wrong email or password.",
  "auth.error.unverified": "Please verify your email — check your inbox for the verification link.",
  "auth.error.generic":    "Something went wrong. Try again in a moment.",
  "auth.error.network":    "Could not reach the server. Check your connection and retry.",

  // Auth — register
  "auth.register.title":      "Create your free account",
  "auth.register.subtitle":   "Get predictions, in-app alerts, and a 30-day risk forecast.",
  "auth.register.submit":     "Create account",
  "auth.register.busy":       "Creating account...",
  "auth.register.haveAccount":"Already have an account?",
  "auth.register.loginLink":  "Log in",
  "auth.register.successTitle":   "Check your inbox",
  "auth.register.successBody":
    "We sent a verification link to {email}. Click it to activate your account, then come back to log in.",
  "auth.register.successDev":
    "Dev mode: the verification token is printed to the backend console. Paste it on the verify page to activate the account.",
  "auth.register.successGoVerify": "Open verify-email page",
  "auth.register.error.shortPassword": "Password must be at least 8 characters.",
  "auth.register.error.passwordMismatch": "Passwords do not match.",
  "auth.register.error.invalidEmail": "Enter a valid email address.",
  "auth.register.error.taken": "That email is already registered.",
  "auth.register.error.generic": "Could not create the account. Try again.",

  // Auth — verify email
  "auth.verify.title":         "Verify your email",
  "auth.verify.subtitle":      "Paste the token from your verification email to activate the account.",
  "auth.verify.tokenLabel":    "Verification token",
  "auth.verify.submit":        "Verify",
  "auth.verify.busy":          "Verifying...",
  "auth.verify.successTitle":  "Email verified",
  "auth.verify.successBody":   "Your account is active. You can now log in.",
  "auth.verify.successCta":    "Continue to log in",
  "auth.verify.error.invalid": "Invalid or expired verification token.",

  // Analytics page
  "analytics.title":              "Global disaster analytics",
  "analytics.subtitle":           "Historical trends from 14,476 events (1900-2021). All charts served from precomputed JSON — zero runtime DB queries, revalidated daily.",
  "analytics.tab.trends":         "Trends",
  "analytics.tab.continents":     "Continents",
  "analytics.tab.insurance":      "Insurance gap",
  "analytics.tab.timeseries":     "Time series",

  // Analytics — trends
  "analytics.trends.title":       "Disaster frequency by decade (1950-2020)",
  "analytics.trends.help":        "One line per disaster type. Earthquake / Flood / Storm dominate; Drought and Volcanic activity stay low.",
  "analytics.trends.insightTitle":"Floods are accelerating",
  "analytics.trends.insightBody": "Recorded floods grew {multiple}x from {n80} events in the 1980s to {n00} in the 2000s.",
  "analytics.trends.legend.decade":"Decade",

  // Analytics — continents
  "analytics.continents.title":   "Total events per continent (1900-2021)",
  "analytics.continents.help":    "Asia accounts for ~40% of recorded events. Each bar is annotated with that continent's most-common disaster type.",
  "analytics.continents.yLabel":  "Total events",

  // Analytics — insurance gap
  "analytics.insurance.title":    "Insurance coverage ratio per disaster type",
  "analytics.insurance.help":     "Median insured / total damage. Low coverage means most losses fall on households.",
  "analytics.insurance.insightTitle":"The insurance gap is real",
  "analytics.insurance.insightBody": "Only {eq}% of earthquake damage and {fl}% of flood damage is insured globally. The rest is paid by households and governments.",
  "analytics.insurance.yLabel":   "Coverage ratio",

  // Analytics — time series
  "analytics.timeseries.title":   "Time series — decadal trend per disaster type",
  "analytics.timeseries.help":    "Bars show event counts; the line is a least-squares linear trend across all 13 decades. Decades with fewer than 10 recorded events are greyed out — sample size too small to read.",
  "analytics.timeseries.typeLabel":"Disaster type",
  "analytics.timeseries.eventsAxis":"Events",
  "analytics.timeseries.trendLabel":"Linear trend",
  "analytics.timeseries.eventsLabel":"Events",
  "analytics.timeseries.greyNote":"Greyed bars = decade with fewer than 10 events.",
  "analytics.timeseries.slope.increasing": "Increasing",
  "analytics.timeseries.slope.decreasing": "Decreasing",
  "analytics.timeseries.slope.stable":     "Stable",
  "analytics.timeseries.slope.full":       "Slope: {slope} events / decade",

  // Pricing page (Feature 8) — keep numbers in sync with backend
  // alembic/versions/a3f1d2e4b5c6_initial_schema.py premium_plans seed.
  "pricing.title":            "Choose your plan",
  "pricing.subtitle":         "Free Subscribers always get in-app alerts. Premium unlocks rich-HTML email alerts, up to 10 subscribed regions, and PDF reports.",
  "pricing.monthly.name":     "Monthly",
  "pricing.monthly.price":    "$5",
  "pricing.monthly.cadence":  "per month",
  "pricing.monthly.feature1": "Email alerts on Critical risk",
  "pricing.monthly.feature2": "Up to 10 subscribed regions",
  "pricing.monthly.feature3": "PDF reports for predictions and 30-day forecasts",
  "pricing.monthly.cta":      "Upgrade to Monthly",
  "pricing.yearly.name":      "Yearly",
  "pricing.yearly.price":     "$48",
  "pricing.yearly.cadence":   "per year",
  "pricing.yearly.equivalent":"= $4 / month",
  "pricing.yearly.save":      "Save 20%",
  "pricing.yearly.feature1":  "Everything in Monthly",
  "pricing.yearly.feature2":  "Two months free vs paying monthly",
  "pricing.yearly.feature3":  "Priority email delivery via Resend",
  "pricing.yearly.cta":       "Upgrade to Yearly",
  "pricing.checkout.busy":    "Starting checkout...",
  "pricing.checkout.loginRequired": "Log in to upgrade",
  "pricing.checkout.error":   "Could not start checkout. Please log in and try again.",
  "pricing.free.title":       "Already on Free?",
  "pricing.free.body":        "Subscriber accounts always include in-app alerts and unlimited predictions. You only need Premium for email alerts and PDF reports.",
  "pricing.note":             "Payments are processed via a secure mock checkout. No real money is charged.",
  "pricing.currentPlan":      "Current plan",

  // Unsubscribe page (/unsubscribe?token=...)
  "unsubscribe.loading":      "Processing your request...",
  "unsubscribe.success.title":"Unsubscribed",
  "unsubscribe.success.body": "You have been unsubscribed. You will no longer receive alerts for this region.",
  "unsubscribe.error.title":  "Invalid link",
  "unsubscribe.error.body":   "This unsubscribe link is invalid or has already been used.",
  "unsubscribe.home":         "Go to home",
  "unsubscribe.noToken":      "No unsubscribe token was found in this link.",

  // Forecast page (Feature 10) — Subscriber+ only
  "forecast.title":            "30-day forecast",
  "forecast.subtitle":         "Day-by-day disaster risk for any region over the next 30 days.",
  "forecast.form.title":       "Forecast parameters",
  "forecast.form.help":        "Each forecast counts against your 5-per-hour rate limit. The backend caches identical requests for 24 hours.",
  "forecast.submit":           "Run 30-day forecast",
  "forecast.busy":             "Running forecast...",
  "forecast.error.unauth":     "Your session has expired. Please log in again.",
  "forecast.error.rateLimit":  "Rate limit reached (5 forecasts per hour). Try again later.",
  "forecast.error.generic":    "Could not run the forecast. Try again in a moment.",
  "forecast.disclaimer":       "Forecast based on historical patterns and seasonal trends — not live weather data.",
  "forecast.summary.title":    "Risk summary",
  "forecast.summary.highest":  "Highest risk day",
  "forecast.summary.likely":   "Most likely disaster",
  "forecast.summary.peakWindow":"Peak risk window (>= High)",
  "forecast.summary.peakNone": "No High / Critical days in the next 30",
  "forecast.calendar.title":   "30-day calendar",
  "forecast.empty":            "Run a forecast to see the 5x6 calendar, line chart, and risk summary.",
  "forecast.calendar.help":    "Click any day to expand the full prediction card. Bar colour follows the standard severity scale.",
  "forecast.calendar.day":     "Day {n}",
  "forecast.summary.dayShort": "Day {n}",
  "forecast.summary.dayRange": "Day {from}-{to}",
  "forecast.cardSuffix":       "Day {n} ({date})",
  "forecast.linechart.title":  "Probability trend",
  "forecast.linechart.help":   "Day 1-30 vs probability score for the selected disaster type. (Multi-line view requires a backend extension — see code comment.)",
  "forecast.guestTitle":       "30-day forecast is for Subscribers",
  "forecast.guestBody":        "Sign up to run a 30-day forecast for any region on Earth.",
  "forecast.guestCta":         "Create free account",

  // Risk map page
  "map.title":             "Global risk map",
  "map.subtitle":          "Heat overlay shows ~330 historical disaster events with composite risk score 0-100. Click any point to predict risk there.",
  "map.loading":           "Loading map tiles...",
  "map.dataLoading":       "Loading heat data...",
  "map.dataError":         "Could not load risk points. The base map still works.",
  "map.legend.title":      "Risk score",
  "map.legend.low":        "Low",
  "map.legend.medium":     "Medium",
  "map.legend.high":       "High",
  "map.legend.critical":   "Critical",
  "map.popup.lat":         "Lat",
  "map.popup.lon":         "Lon",
  "map.popup.risk":        "Risk",
  "map.popup.disaster":    "Type",
  "map.popup.guestCta":    "Sign up to predict risk here",
  "map.popup.subscriberCta":"Run prediction at this point",
  "map.attribution":       'Map &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',

  // Severity badge
  "severity.Low":      "Low",
  "severity.Medium":   "Medium",
  "severity.High":     "High",
  "severity.Critical": "Critical",

  // Recommendation categories
  "rec.category.evacuation": "Evacuation",
  "rec.category.kit":        "Emergency kit",
  "rec.category.shelter":    "Shelter",
  "rec.category.medical":    "Medical",
  "rec.category.contact":    "Contacts",
  "rec.title":               "Safety recommendations",
  "rec.empty":               "No recommendations available for this combination yet.",
  "rec.personalisation":     "Personalised for your subscription history.",

  // Dashboard shell
  "dashboard.title":           "Dashboard",
  "dashboard.greeting":        "Hello, {email}",
  "dashboard.tab.overview":      "Overview",
  "dashboard.tab.predictions":   "Predictions",
  "dashboard.tab.alerts":        "Alerts",
  "dashboard.tab.subscriptions": "Subscriptions",
  "dashboard.tab.admin":         "Admin",

  // Dashboard — overview / three task cards
  "dashboard.overview.signOut":  "Sign out",

  // Card 1 — Disaster Type Predictor
  "card1.title":        "Disaster Type Predictor",
  "card1.subtitle":     "Which disaster is most likely at these coordinates?",
  "card1.badge":        "XGB + CatBoost Classifier",
  "card1.year.label":   "Target year",
  "card1.year.placeholder": "e.g. 2025",
  "card1.continent.label": "Continent",
  "card1.continent.placeholder": "e.g. Africa",
  "card1.season.label": "Month / season (optional)",
  "card1.season.placeholder": "e.g. 7 or summer",
  "card1.submit":       "Classify",
  "card1.busy":         "Classifying...",
  "card1.result.top":   "Most likely disaster",
  "card1.result.ranked":"Ranked probabilities",
  "card1.error.generic":"Classification failed. Try again.",

  // Card 2 — Disaster Impact Prediction
  "card2.title":        "Disaster Impact Prediction",
  "card2.subtitle":     "Estimate deaths, damage, and affected population.",
  "card2.badge":        "XGB + RF Regressors",
  "card2.year.label":   "Prediction year",
  "card2.year.placeholder": "e.g. 2025",
  "card2.continent.label": "Continent",
  "card2.continent.placeholder": "e.g. Asia",
  "card2.country.label": "Country (optional)",
  "card2.country.placeholder": "e.g. Bangladesh",
  "card2.season.label": "Month / season (optional)",
  "card2.season.placeholder": "e.g. 6 or monsoon",
  "card2.submit":       "Predict impact",
  "card2.busy":         "Predicting...",
  "card2.result.type":  "Most likely disaster",
  "card2.result.events":"Expected events",
  "card2.result.deaths":"Est. deaths",
  "card2.result.injuries": "Est. injuries",
  "card2.result.affected": "Est. affected",
  "card2.result.damage":   "Est. damage (×1000 USD)",
  "card2.result.uninsured":"Uninsured loss (×1000 USD)",
  "card2.error.generic":"Impact prediction failed. Try again.",

  // Card 3 — Risk Level Classifier
  "card3.title":        "Risk Level Classifier",
  "card3.subtitle":     "Get severity, SHAP explanation, and safety recommendations.",
  "card3.badge":        "XGB Severity Classifier",
  "dashboard.overview.title":   "Run a prediction",
  "dashboard.overview.subtitle": "Estimate disaster risk and impact for any region. Predictions are saved to your history.",

  // Coming soon placeholders
  "dashboard.coming.admin":         "Admin tools arrive in Phase 8.",

  // Predictions history tab
  "history.title":         "Prediction History",
  "history.empty":         "No predictions yet. Run one from the Overview tab.",
  "history.loading":       "Loading history...",
  "history.error":         "Failed to load history.",
  "history.col.type":      "Disaster",
  "history.col.severity":  "Severity",
  "history.col.prob":      "Probability",
  "history.col.risk":      "Risk",
  "history.col.location":  "Location",
  "history.col.date":      "Date",
  "history.prev":          "Previous",
  "history.next":          "Next",
  "history.page":          "Page {page} of {total}",

  // Subscriptions tab
  "subs.title":            "Region Subscriptions",
  "subs.subtitle":         "Subscribe to regions to receive alerts when disaster risk is detected.",
  "subs.limit.free":       "Free accounts: up to 3 active subscriptions.",
  "subs.limit.premium":    "Premium accounts: up to 10 active subscriptions.",
  "subs.add.title":        "Add subscription",
  "subs.add.region":       "Region name",
  "subs.add.region.ph":    "e.g. Cairo, Egypt",
  "subs.add.lat":          "Latitude",
  "subs.add.lon":          "Longitude",
  "subs.add.freq":         "Alert frequency",
  "subs.add.freq.weekly":  "Weekly digest",
  "subs.add.freq.immediate": "Immediate (Critical only)",
  "subs.add.submit":       "Subscribe",
  "subs.add.busy":         "Subscribing...",
  "subs.add.error":        "Failed to subscribe.",
  "subs.empty":            "No active subscriptions.",
  "subs.loading":          "Loading subscriptions...",
  "subs.remove":           "Unsubscribe",
  "subs.removing":         "Removing...",
  "subs.col.region":       "Region",
  "subs.col.coords":       "Coordinates",
  "subs.col.freq":         "Frequency",
  "subs.col.since":        "Since",
  "subs.col.action":       "Action",

  // Alerts tab
  "alerts.title":          "Alert History",
  "alerts.subtitle":       "Alerts dispatched to your subscribed regions.",
  "alerts.empty":          "No alerts yet. Subscribe to regions to start receiving alerts.",
  "alerts.loading":        "Loading alerts...",
  "alerts.error":          "Failed to load alerts.",
  "alerts.col.type":       "Type",
  "alerts.col.disaster":   "Disaster",
  "alerts.col.severity":   "Severity",
  "alerts.col.message":    "Message",
  "alerts.col.sent":       "Sent",
  "alerts.col.status":     "Status",
  "alerts.type.weekly":    "Weekly digest",
  "alerts.type.immediate": "Immediate",
  "alerts.status.sent":    "Sent",
  "alerts.status.failed":  "Failed",
  "alerts.status.pending": "Pending",

  // Prediction form
  "form.lat.label":          "Latitude",
  "form.lat.placeholder":    "e.g. 30.05",
  "form.lat.error":          "Latitude must be between -90 and 90.",
  "form.lon.label":          "Longitude",
  "form.lon.placeholder":    "e.g. 31.24",
  "form.lon.error":          "Longitude must be between -180 and 180.",
  "form.country.label":      "Country",
  "form.country.placeholder": "e.g. Egypt",
  "form.continent.label":    "Continent",
  "form.continent.placeholder": "e.g. Africa",
  "form.disasterType.label": "Disaster type",
  "form.season.label":       "Season or month (optional)",
  "form.season.placeholder": "Leave blank for current month",
  "form.season.help":        'Name ("spring", "summer", "autumn", "winter") or month number 1-12.',
  "form.magnitude.label":    "Magnitude (optional)",
  "form.magnitude.placeholder": "Richter / kph / km² / °C",
  "form.submit":             "Run prediction",
  "form.busy":               "Running prediction...",
  "form.required":           "All fields above are required.",

  // Filter bar (shared across all charts)
  "filter.label.disasterType":  "Disaster Type",
  "filter.label.metric":        "Metric",
  "filter.label.sort":          "Sort",
  "filter.label.riskLevel":     "Risk Level",
  "filter.label.fromDecade":    "From",
  "filter.label.toDecade":      "To",
  "filter.label.minSeverity":   "Min Severity",
  "filter.all.types":           "All Types",
  "filter.all.levels":          "All Levels",
  "filter.all.severities":      "All Severities",
  "filter.metric.events":       "Events",
  "filter.metric.deaths":       "Deaths",
  "filter.metric.affected":     "Affected",
  "filter.metric.damage":       "Damage (USD)",
  "filter.sort.lowHigh":        "Low → High",
  "filter.sort.highLow":        "High → Low",
  "filter.riskLevel.low":       "Low (0–30)",
  "filter.riskLevel.medium":    "Medium (31–55)",
  "filter.riskLevel.high":      "High (56–75)",
  "filter.riskLevel.critical":  "Critical (76–100)",
  "filter.severity.mediumPlus": "Medium +",
  "filter.severity.highPlus":   "High +",
  "filter.severity.criticalOnly": "Critical only",

  // Prediction errors
  "predict.error.unauth":    "Your session has expired. Please log in again.",
  "predict.error.forbidden": "Predictions require a Subscriber account. Verify your email and log in.",
  "predict.error.generic":   "Could not run the prediction. Try again in a moment.",

  // Prediction result card
  "result.title":             "Prediction result",
  "result.probability.label": "Probability",
  "result.riskScore.label":   "Risk score",
  "result.disasterType.label":"Disaster type",
  "result.deaths":            "Estimated deaths",
  "result.injuries":          "Estimated injured",
  "result.affected":          "Estimated affected",
  "result.damage":            "Estimated damage",
  "result.uninsured":         "Uninsured loss",
  "result.coverage.injuries": "Estimate based on ~26% of recorded events — injuries data is often missing.",
  "result.coverage.damage":   "Estimate based on ~33% of recorded events — damage data is often missing.",
  "result.dataSource.country": "Based on historical events in {country}.",
  "result.dataSource.region":  "Based on regional historical average ({n} events).",
  "result.dataSource.global":  "Based on the global historical average ({n} events).",
  "result.dataQuality.limited":"Limited data — treat numbers with caution.",
  "result.shap.title":        "Top 3 drivers of this prediction",
  "result.secondary.title":   "Secondary disaster warning",
  "result.seasonal.title":    "Seasonal peak months",
  "result.modelVersion":      "Model {version}",
  "result.miniChart.title":   "Historical frequency — {type}",

  // Mock checkout page (Phase 7 — MockPaymentService redirect target)
  "checkout.mock.title":          "Confirm Mock Payment",
  "checkout.mock.subtitle":       "This is a simulated payment page. No real money will be charged.",
  "checkout.mock.plan":           "Plan",
  "checkout.mock.amount":         "Amount",
  "checkout.mock.session":        "Session ID",
  "checkout.mock.cta":            "Confirm Mock Payment",
  "checkout.mock.busy":           "Processing...",
  "checkout.mock.success.title":  "You are now Premium!",
  "checkout.mock.success.body":   "Your account has been upgraded to Premium. Log out and log back in to see your Premium badge in the nav.",
  "checkout.mock.success.cta":    "Go to Dashboard",
  "checkout.mock.error.title":    "Payment confirmation failed",
  "checkout.mock.error.body":     "Could not confirm the mock payment. Try again or start a new checkout from the Pricing page.",
  "checkout.mock.error.retry":    "Try again",
  "checkout.mock.noSession":      "No session ID found. Please start checkout from the Pricing page.",
  "checkout.mock.backToPricing":  "Back to Pricing",

  // Time Series page (/analytics/timeseries) — Feature 9 standalone page
  "timeseries.page.title":    "Historical Disaster Trends",
  "timeseries.page.subtitle":
    "Decadal event counts with linear regression trend lines. Pick any disaster type and metric — 1900–2020, served from precomputed EM-DAT data.",
  "timeseries.insight.title": "Floods are accelerating",
  "timeseries.insight.body":
    "Recorded floods grew {multiple}× from {n80} events in the 1980s to {n00} in the 2000s.",

  // Nav — timeseries + forecast links
  "nav.timeseries": "Time Series",
  "nav.forecast":   "Forecast",

  // /forecast public landing page
  "forecast.landing.hero.title":    "30-Day Disaster Risk Forecast",
  "forecast.landing.hero.subtitle": "Day-by-day risk outlook for any region on Earth — severity levels, peak windows, and the most likely disaster type. Powered by XGBoost trained on 16,126 historical events.",
  "forecast.landing.feature1.title": "5×6 Risk Calendar",
  "forecast.landing.feature1.body":  "30 colour-coded tiles show risk severity for each day. Click any cell to expand the full prediction with SHAP explanation and safety recommendations.",
  "forecast.landing.feature2.title": "Day-by-Day Probability",
  "forecast.landing.feature2.body":  "Recharts line chart plots probability over 30 days so you can spot the peak risk window at a glance.",
  "forecast.landing.feature3.title": "Premium PDF Export",
  "forecast.landing.feature3.body":  "Premium subscribers can download a full 30-day forecast as a formatted PDF report including impact estimates and AI safety recommendations.",
  "forecast.landing.cta.signup":     "Sign up free",
  "forecast.landing.cta.learn":      "See pricing",
  "forecast.landing.redirect":       "Taking you to your forecast…",

  // Error states
  "error.publicData.title": "Live data unavailable",
  "error.publicData.body":
    "The public stats service did not respond. Charts and headline numbers will return once it is reachable. All other navigation works.",
}

export type StringKey = keyof typeof STRINGS_EN

export function S(key: string): string {
  if (key in STRINGS_EN) return STRINGS_EN[key]
  return `[missing: ${key}]`
}

/** Substitute `{name}` tokens in a localised string with provided values. */
export function Sf(key: string, vars: Record<string, string | number>): string {
  return S(key).replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  )
}
