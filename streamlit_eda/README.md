# SafeEarth — Training Data EDA (Streamlit)

A deep exploratory data analysis of the EM-DAT training dataset (1900–2021,
16,126 events) that powers SafeEarth's disaster-prediction models. It quantifies
**data quality** (missingness, skew, dirty coordinates, class imbalance) and then
shows **how that data quality explains the model's per-class accuracy**.

## Run locally

```bash
pip install -r streamlit_eda/requirements.txt
streamlit run streamlit_eda/streamlit_app.py
```

Opens at http://localhost:8501.

## Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub.**
3. Repository: `mohaitham22/SafeEarth_Intelligence`
4. Branch: the branch this app lives on.
5. **Main file path:** `streamlit_eda/streamlit_app.py`
6. Click **Deploy**.

The app reads the training CSV (`data/train/…`) and model metrics (`metrics/…`)
straight from the repo — no extra configuration or secrets are required.

## What's inside

| Tab | Contents |
|-----|----------|
| 📋 Overview | Dataset shape, the 8-of-15 modeled-types decision, full column dictionary |
| 🔍 Data Quality | Missingness per field, the 81%-missing-coordinates problem, dirty lat/lon strings, extreme right-skew (mean vs median) |
| ⚖️ Class Balance | 21× imbalance, per-class counts, why macro-F1 is the honest metric |
| 📈 Features | Magnitude availability, events over time, seasonality |
| 🎯 Quality → Accuracy | Magnitude-vs-F1 and volume-vs-F1 correlations; why resampling regressed |
| ✅ Takeaways | Findings + a concrete data roadmap to improve accuracy |
