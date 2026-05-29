# SafeEarth Intelligence — Project Summary

> A web app that predicts natural disasters, estimates human/economic impact, and generates AI-powered safety recommendations.

---

## 1. What the App Does (Big Picture)

A user picks any location on Earth → the system predicts the most likely disaster (Flood, Earthquake, Storm, etc.), estimates how many people could be affected, and instantly generates 6 personalized safety recommendations — all powered by real historical disaster data and machine learning.

**Tech stack in one line:**
`Next.js 14` (frontend) + `FastAPI / Python` (backend) + `PostgreSQL` (database) + `XGBoost + CatBoost` (ML) + `ChromaDB + Groq` (RAG)

---

## 2. The Dataset

- **Source:** EM-DAT (Emergency Events Database) — the world's most authoritative disaster database, maintained by the UN.
- **Training set:** 16,126 disaster events from **1900 to 2021**.
- **Test (holdout) set:** Events from 1970–2021, never touched during training.
- **Disaster types covered:** Flood, Storm, Earthquake, Drought, Landslide, Wildfire, Extreme Temperature, Volcanic Activity.

Each event has: location (latitude/longitude), date, disaster magnitude, deaths, injuries, affected people, economic damage, insured damage.

---

## 3. Data Pipeline (Phase 2)

Before any ML can run, we pre-process the raw CSV into **8 clean JSON files** using a single script (`scripts/generate_emdat_stats.py`). These files are loaded into memory when the server starts — never re-read at runtime.

| File | What it contains |
|------|-----------------|
| `emdat_stats.json` | Median deaths/injuries/damage per disaster type, broken down globally → by continent → by country |
| `timeseries.json` | Event counts per year and per decade (1900–2021) |
| `trends.json` | Decade-by-decade growth trends (1950–2020) |
| `seasonal_peaks.json` | Which months each disaster type peaks |
| `secondary_disasters.json` | Which disasters commonly co-occur (e.g. Earthquake → Tsunami) |
| `insurance_ratios.json` | What fraction of damage is typically insured, per disaster type |
| `continent_stats.json` | Aggregated stats per continent |
| `risk_map.json` | 334 pre-sampled lat/lon points for the heatmap |

**Important rule we always follow: use median, never mean.**
Disaster data is heavily skewed — one catastrophic event can have millions of deaths. The mean is misleading. Example: Flood mean deaths = 1,735 but median = 16.

---

## 4. Machine Learning — Disaster Classification (Phase 3)

### 4.1 What the model predicts

Given a location + date + disaster type, the model answers:
> "What is the probability that a **[disaster type]** hits here?"

The user picks the disaster type (Flood, Earthquake, etc.) and the model returns the probability for that specific type, along with a severity label.

**Severity thresholds:**
| Probability | Severity |
|-------------|----------|
| 0.00 – 0.30 | Low |
| 0.31 – 0.55 | Medium |
| 0.56 – 0.75 | High |
| 0.76 – 1.00 | Critical |

---

### 4.2 Feature Engineering (16 features)

| Feature | Description |
|---------|-------------|
| `latitude` / `longitude` | Geographic location |
| `abs_latitude` | Distance from equator (climate zone proxy) |
| `continent_enc` | Continent encoded as integer |
| `region_enc` | Sub-region encoded as integer |
| `month_sin` / `month_cos` | Month encoded cyclically (January and December are "close") |
| `dis_mag_value` | Disaster magnitude (Richter scale / wind speed / area) |
| `has_magnitude` | Boolean — does this event have a magnitude reading? |
| `historical_freq` | How often this disaster type historically hits this region |
| `log_hist_freq` | Log-transformed version of the above |
| `decade` | Which decade the event falls in |
| `day_offset` | For forecasting — how many days ahead (0–29) |

Why cyclical encoding for month? If we use raw month numbers, the model thinks December (12) and January (1) are 11 steps apart — but they are actually adjacent seasons. `sin/cos` encoding fixes this.

---

### 4.3 Model Evolution — How We Got to v4.2

We iterated through several versions, each improving on the last:

| Version | Change | Macro F1 |
|---------|--------|----------|
| v1 | Single XGBoost, 10 features | 0.7020 |
| v2 | Added cyclical month + country encoding (12 features) | 0.6811 |
| v3 | Added LightGBM to ensemble, Optuna tuning, 16 features | 0.7106 |
| v4.1 | Added CatBoost to ensemble (XGB + LGB + CatBoost), Landslide class weight ×3 | 0.6929 |
| **v4.2 (final)** | **Dropped LightGBM (it was hurting macro F1), XGB=60% + CatBoost=40%** | **0.7052** |

**v5 experiment (SRTM elevation) — failed and reverted:**
We tried adding elevation data from NASA satellites. The API timed out on 1,383 rows, leaving them with elevation=0 — identical to sea-level events. This poisoned the feature and dropped Macro F1 to 0.6650. Reverted.

**Key lesson from v4 experiment:**
We tried adding "what fraction of events in this region are Floods?" as a feature. XGBoost learned to shortcut through it ("high flood fraction → predict Flood always"), ignoring more generalizable signals like magnitude and season. This is a form of label leakage. Removed.

---

### 4.4 Final Model: v4.2

**Architecture:** Soft ensemble of two models

```
Final prediction probability = 0.60 × XGBoost + 0.40 × CatBoost
```

**Why two models?**
Each model has different biases. XGBoost is faster and handles sparse features well. CatBoost handles ordered boosting and is more robust on small classes. Combining them improves minority class detection.

**Per-class F1 on holdout test set (13,070 events):**

| Disaster Type | F1 Score | Why hard/easy |
|---------------|----------|---------------|
| Earthquake | 97.6% | Distinct magnitude signal (Richter scale) |
| Flood | 77.8% | Common, many training examples |
| Storm | 77.1% | Similar to Flood, distinguishable by season |
| Extreme Temperature | 74.9% | Seasonal signal is strong |
| Volcanic Activity | 66.8% | Rare, geographically concentrated |
| Wildfire | 62.8% | Seasonal but overlaps with Drought |
| Drought | 58.9% | Very gradual onset, no clear magnitude |
| Landslide | 48.2% | Rarest class, small training set |

**Overall: Macro F1 = 0.7052 | Weighted F1 = 0.7587 | Accuracy = 74.67%**

---

### 4.5 SHAP — Why Did the Model Predict That?

Every prediction includes a SHAP explanation: the top 3 features that most influenced the result, shown as percentage bars.

**What is SHAP?**
SHAP (SHapley Additive exPlanations) is a method from game theory that assigns each feature a "contribution score" — how much did this feature push the prediction up or down?

**Implementation detail:**
The SHAP TreeExplainer is computed **once at server startup** and cached. Re-computing it per request would add ~200ms latency. The cached explainer is reused for every prediction.

```python
# Loaded once at startup:
shap_explainer = shap.TreeExplainer(xgboost_model)

# Used per request:
shap_values = shap_explainer.shap_values(input_features)
top_3 = sort by |contribution| → return as [{feature, contribution_pct}]
```

---

### 4.6 Impact Estimation (Regression)

Beyond classifying the disaster type, the system estimates:
- Estimated deaths
- Estimated injuries
- Estimated people affected
- Estimated economic damage (USD)
- Uninsured loss (damage × (1 − insurance ratio))

**How it works:**
Four separate regression models are bundled together:

| Target | Model | Why |
|--------|-------|-----|
| Deaths | XGBoost Regressor | Handles extreme outliers well |
| Damage (USD) | XGBoost Regressor | Same reason |
| Injuries | Random Forest Regressor | More stable on sparse data |
| Affected people | Random Forest Regressor | Same reason |

All targets were trained on `log(1 + value)` to handle the extreme skew in disaster data. At inference time, `exp(output) - 1` reverses this transformation.

**The accuracy problem we fixed:**
The regressors share the same 16 geographic/temporal features as the classifier — disaster type is NOT in their feature vector. This meant a Flood and an Earthquake at the same coordinates on the same date produced identical impact numbers. That is wrong.

**The fix (coverage-weighted blending):**
We blend the ML regressor output with EM-DAT historical medians for the specific disaster type:

| Field | EM-DAT data coverage | Blend formula |
|-------|---------------------|---------------|
| Deaths | ~73% | 70% EM-DAT median + 30% ML |
| Affected | ~73% | 70% EM-DAT median + 30% ML |
| Damage | ~33% | 35% EM-DAT median + 65% ML |
| Injuries | ~26% | 30% EM-DAT median + 70% ML |

Higher EM-DAT coverage → we trust the historical median more. Lower coverage → we lean on the ML regressor.

---

### 4.7 Risk Score (0–100 Composite)

```
risk_score = (normalized_deaths × 0.35)
           + (normalized_affected × 0.30)
           + (normalized_damage × 0.20)
           + (probability × 0.15)
```

Each metric is normalized against the 99th percentile for that disaster type in EM-DAT history, so the score is always on a 0–100 scale regardless of disaster type.

---

### 4.8 30-Day Forecast

The same ML models are run in a loop — 30 iterations, each with `day_offset` = 0 to 29. The `day_offset` feature lets the model account for how risk evolves over the next month.

- Results are cached in the database for 24 hours per (location, date).
- Rate-limited to 5 requests/hour per user (it's computationally expensive).
- RAG recommendations are deduplicated by severity — instead of 30 separate LLM calls, we make at most 4 (one per severity level: Low/Medium/High/Critical).

---

## 5. RAG Pipeline — AI Safety Recommendations (Phase 4)

### 5.1 What is RAG?

RAG = **Retrieval-Augmented Generation**.

Instead of asking an LLM to generate safety advice from scratch (which may hallucinate), we:
1. Store official disaster safety guidelines in a searchable database.
2. When a user needs advice, we retrieve the most relevant passages.
3. We feed those passages to the LLM as context.
4. The LLM generates answers grounded in real, authoritative content.

**Think of it like:** giving a student the textbook during the exam vs. asking them to recall everything from memory.

---

### 5.2 The Knowledge Base

**Source:** `Natural_Disaster_Safety_Guidelines.pdf` — an official 51-page document covering 15 disaster types.

Each chapter covers: Before / During / After / Medical care / Evacuation routes.

---

### 5.3 Chunking — Splitting the PDF into Searchable Pieces

A vector database cannot search a 51-page PDF directly — it needs small, semantically meaningful pieces called **chunks**.

We benchmarked **4 chunking strategies** on 30 test queries (2 per disaster type):

| Strategy | How it works | Score |
|----------|-------------|-------|
| Fixed-Size | Split every N words, regardless of content | 0.6278 |
| Recursive Character | Split on paragraphs, then sentences, then words | 0.5824 |
| Section-Aware | Detect "Before:", "During:", "After:" headers | 0.8042 |
| **Semantic (winner)** | **Detect topic changes using sentence similarity** | **0.8493** |

**How Semantic Chunking works:**
1. Split the text into individual sentences.
2. For each consecutive pair of sentences, compute their cosine similarity using a sentence embedding model.
3. If similarity drops below 0.45 (a threshold we tuned), start a new chunk — the topic has changed.
4. This produces chunks that begin and end at natural topic boundaries.

Scoring criteria:
- **Retrieval Relevance (50%):** Does the search return relevant chunks?
- **Chunk Coherence (30%):** Does each chunk make sense on its own?
- **LLM Output Quality (20%):** Are the generated recommendations specific and actionable?

**Result:** 167 chunks across 15 chapters, stored in ChromaDB.

---

### 5.4 Embedding — Turning Text into Numbers

To search by meaning (not just keywords), we convert every chunk into a **vector** — a list of 384 numbers that captures the semantic meaning.

**Model used:** `sentence-transformers/all-MiniLM-L6-v2`
- 80MB, runs on CPU, open-source.
- The same model is used at ingestion time (to embed the chunks) and at query time (to embed the user's question).

Why the same model for both? Because both vectors live in the same "meaning space" — similar meanings will have vectors that are close together.

---

### 5.5 Vector Database — ChromaDB

All 167 chunk embeddings are stored in **ChromaDB**, a local vector database.

When a user needs recommendations:
```
Query: "High severity Flood emergency safety recommendations Cairo"
↓
Embed the query using all-MiniLM-L6-v2
↓
Find the 5 most similar chunks in ChromaDB (cosine similarity)
↓
Return those 5 chunks as context
```

ChromaDB uses a **PersistentClient** — the data is stored on disk and loaded once at server startup. It is never re-loaded per request.

---

### 5.6 LLM — Generating the Final Recommendations

The 5 retrieved chunks are passed to **Groq** (a fast LLM inference API) running `llama-3.1-8b-instant`:

```
Prompt: "Given these disaster safety guidelines, generate exactly 6 safety 
         recommendations for a [severity] [disaster type] emergency in [region].
         Return JSON with: category, title, body."
```

- Temperature = 0.3 (low = more focused, less creative)
- Response forced to JSON format
- Always exactly 6 recommendations

Recommendations are sorted in a fixed order: **Evacuation → Emergency Kit → Shelter → Medical → Emergency Contacts**

---

### 5.7 Resilience — What Happens if Groq is Down?

The RAG pipeline can fail (network issues, API quota, etc.). We designed a **degrade-not-fail** system:

```
Try RAG pipeline
  ↓ (if Groq is unavailable or returns bad output)
Fall back to pre-written recommendations stored in PostgreSQL
  ↓ (if DB has no entries for this type/severity)
Return empty list (prediction still succeeds — never a 500 error)
```

The `/health` endpoint reports `rag_loaded: true/false` so the team can monitor the RAG status without crashing.

---

### 5.8 Personalisation

If a user has previously received an alert for the same disaster type + region, the system prepends a notice:
> "You were previously warned about flood risk in this region."

This check happens in the router via a database join before calling the RAG pipeline.

---

## 6. How ML and RAG Connect

```
User submits: latitude, longitude, disaster_type
                    ↓
          [ML Classifier — v4.2]
          XGBoost (60%) + CatBoost (40%)
                    ↓
          probability, severity, risk_score
                    ↓
     [Impact Regressors + EM-DAT Blend]
     deaths, injuries, affected, damage
                    ↓
          [SHAP Explainer]
          top 3 features that drove this prediction
                    ↓
          [RAG Pipeline]
    ChromaDB retrieval → Groq LLM → 6 recommendations
                    ↓
     Full response saved to PostgreSQL
     (All of the above returned in ONE API call)
```

---

## 7. Test Coverage

| Test File | Tests | What it covers |
|-----------|-------|---------------|
| `test_smoke.py` | 5 | App starts, DB connects, health check |
| `test_auth.py` | 11 | Register → verify email → login → logout → refresh |
| `test_data_pipeline.py` | 4 | JSON files load correctly at startup |
| `test_regions.py` | 11 | All 8 region endpoints |
| `test_predictions.py` | 16 | Prediction endpoint (ML models mocked — no pkl needed) |
| `test_recommendations.py` | 12 | RAG happy path, fallback path, personalisation |
| `test_generation.py` | 10 | JSON file generation regression tests |
| **Total** | **73/73** | **All passing** |

---

## 8. Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Done | FastAPI backend + PostgreSQL + Auth |
| Phase 2 | ✅ Done | EM-DAT data pipeline + 8 JSON files |
| Phase 3 | ✅ Done | ML models v4.2 + prediction endpoints |
| Phase 4 | ✅ Done | RAG pipeline + recommendations |
| Phase 5 | ✅ Done | Full Next.js 14 frontend (12 routes) |
| Phase 6 | 📋 Next | Email alerts + subscriptions + n8n automation |
| Phase 7 | 📋 Planned | Premium subscription + payments |
| Phase 8 | 📋 Planned | Deployment (Vercel + Render) + PWA |
