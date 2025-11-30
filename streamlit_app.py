import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

#loading data from csv we already have
@st.cache_data
def load_data():
    all_df = pd.read_csv("articles_all.csv")
    fraud_df = pd.read_csv("fraud_articles.csv")
    all_df["published_dt"] = pd.to_datetime(all_df["published"], errors="coerce")
    fraud_df["published_dt"] = pd.to_datetime(fraud_df["published"], errors="coerce")
    return all_df, fraud_df

all_df, fraud_df = load_data()

fraud_df["summary_lc"] = fraud_df["summary"].fillna("").str.lower()

FRAUD_LEXICON = [
    "breach",
    "exposed",
    "credential",
    "ransomware",
    "phishing",
    "data leak",
    "identity theft",
    "extortion",
    "malware",
    "exfiltration",
]

st.title("Fraud & Data Breach News Explorer")

# sidebar filters
st.sidebar.header("Filters")

threshold = st.sidebar.slider(
    "Similarity threshold",
    min_value=0.0,
    max_value=1.0,
    value=0.55,
    step=0.05,
)

keywords_to_plot = st.sidebar.multiselect(
    "Keywords to plot",
    FRAUD_LEXICON,
    default=["breach", "ransomware", "credential"],
)

date_min = fraud_df["published_dt"].min()
date_max = fraud_df["published_dt"].max()
date_range = st.sidebar.date_input(
    "Date range",
    value=(date_min, date_max),
)

# applies the filters
start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

filtered = fraud_df[
    (fraud_df["similarity"] >= threshold)
    & (fraud_df["published_dt"].between(start_date, end_date))
].copy()

st.subheader("Overview")

col1, col2, col3 = st.columns(3)
col1.metric("Total articles scraped", len(all_df))
col2.metric("Fraud-like articles (filtered)", len(filtered))
pct = (len(filtered) / max(len(all_df), 1)) * 100
col3.metric("Fraud-like % of total", f"{pct:.1f}%")

st.write("")

# monthly trend chart
st.markdown("### Monthly Fraud Article Count")

if not filtered.empty:
    monthly_counts = (
        filtered
        .set_index("published_dt")
        .resample("M")["url"]
        .count()
    )

    fig1, ax1 = plt.subplots(figsize=(8, 4))
    monthly_counts.plot(kind="line", ax=ax1)
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Article count")
    ax1.set_title("Fraud-Related Articles per Month")
    st.pyplot(fig1)

else:
    st.info("No articles match the current filters.")

# monthly keyword trend chart
st.markdown("### Keyword Mentions Over Time")

if not filtered.empty and keywords_to_plot:
    df_kw = filtered.copy()
    df_kw["month"] = df_kw["published_dt"].dt.to_period("M").dt.start_time

    rows = []
    for month, grp in df_kw.groupby("month"):
        text = " ".join(grp["summary_lc"].tolist())
        counts = {kw: text.count(kw) for kw in FRAUD_LEXICON}
        counts["month"] = month
        rows.append(counts)

    trend_df = pd.DataFrame(rows).sort_values("month")

    fig2, ax2 = plt.subplots(figsize=(10, 5))
    for kw in keywords_to_plot:
        if kw in trend_df.columns:
            ax2.plot(trend_df["month"], trend_df[kw], label=kw)
    ax2.set_xlabel("Month")
    ax2.set_ylabel("Mentions")
    ax2.set_title("Keyword Mentions Over Time (Monthly)")
    ax2.legend()
    st.pyplot(fig2)
else:
    st.info("Not enough data to plot keyword trends with current filters.")

# article explorer
st.markdown("### Article Explorer")

st.dataframe(
    filtered[["published_dt", "similarity", "title", "url"]]
    .sort_values("published_dt", ascending=False)
    .reset_index(drop=True)
)

selected_title = st.selectbox(
    "Select an article to inspect:",
    options=filtered["title"].tolist() if not filtered.empty else [],
)

if selected_title:
    row = filtered[filtered["title"] == selected_title].iloc[0]
    st.markdown(f"**Title:** {row['title']}")
    st.markdown(f"**Published:** {row['published_dt'].date()}")
    st.markdown(f"**Similarity:** {row['similarity']:.3f}")
    st.markdown(f"[Open article]({row['url']})")
    st.markdown("**Summary:**")
    st.write(row["summary"])
