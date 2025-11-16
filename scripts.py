import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import time
import random
import textwrap
from sentence_transformers import SentenceTransformer, util
import numpy as np
import pandas as pd
import os
from supabase import create_client, Client
from dotenv import load_dotenv

import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

#MODELS / CONSTANTS 

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
fraud_keywords = "fraud, scam, phishing, data breach, identity theft"
fraud_embedding = embedding_model.encode(fraud_keywords, convert_to_tensor=True)

BASE_URL = "https://www.bleepingcomputer.com"
TAG_URL = "https://www.bleepingcomputer.com/tag/data-breach/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)

FRAUD_LEXICON = [
    "ransomware", "phishing", "data leak", "exposed",
    "credential", "extortion", "identity theft",
    "malware", "breach", "exfiltration"
]

#Helpers to clean data

def clean_text(txt: str) -> str:
    """Collapse whitespace and trim."""
    return re.sub(r"\s+", " ", txt).strip()


def _tag_page_url(page: int) -> str:
    """Build URL for a given tag page."""
    base = TAG_URL.rstrip("/")
    return base + ("/" if page == 1 else f"/page/{page}/")


# scraping scripts 

def get_article_links_from_tag(max_links: int = 300, max_pages: int = 30):
    """
    Crawl multiple tag pages:
      /tag/data-breach/
      /tag/data-breach/page/2/
      /tag/data-breach/page/3/
    …until we collect max_links or hit max_pages or a page yields no new links.

    Return [{title, url}, ...]
    """
    articles = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        # be nice to the site: sleep a bit longer between pages to avoid 429s
        wait = random.uniform(5, 9)
        print(f"[info] Sleeping {wait:.1f}s before fetching tag page {page}")
        time.sleep(wait)

        url = _tag_page_url(page)
        print(f"[info] Fetching tag page {page}: {url}")
        r = session.get(url, timeout=10)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        new_links = 0
        for a in soup.select("a[href]"):
            href = a["href"].strip()
            full_url = urljoin(BASE_URL, href)

            # must stay on same domain
            if not full_url.startswith(BASE_URL):
                continue

            # skip comment links
            if "#comments" in full_url:
                continue

            path = full_url.lower()

            # must look like an article
            if "/news/security/" not in path:
                continue

            # skip garbage promo
            if "webinar" in path:
                continue

            # anchor text as candidate title
            title = a.get_text(strip=True)
            if not title:
                continue  # skip blank anchors

            # dedupe
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                articles.append({
                    "title": title,
                    "url": full_url,
                })
                new_links += 1

                if len(articles) >= max_links:
                    return articles

        # if this page produced nothing new, assume pagination is done
        if new_links == 0:
            print(f"[info] No new links on page {page}, stopping pagination.")
            break

    return articles

def summarize_article(url: str) -> dict:
    """
    Visit an article URL and pull:
      - title from <h1>
      - author from <a rel="author"> ... <span itemprop="name">
      - published date from <li class="cz-news-date">
      - summary from paragraphs
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(url, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Title
    title_tag = soup.select_one("h1")
    title = clean_text(title_tag.get_text()) if title_tag else None

    # Published date
    date_tag = soup.select_one(".cz-news-date")
    published = clean_text(date_tag.get_text()) if date_tag else "unknown"

    # Author
    author_tag = soup.select_one('a[rel="author"] span[itemprop="name"]')
    if author_tag:
        author = clean_text(author_tag.get_text())
    else:
        fallback_tag = soup.select_one('[itemprop="name"]')
        author = clean_text(fallback_tag.get_text()) if fallback_tag else "unknown"

    # body/summary
    paras = []

    # main container
    for p in soup.select("div#bc_article_content p"):
        txt = clean_text(p.get_text(" ", strip=True))
        # filter garbage like "Related:"
        if len(txt.split()) < 4:
            continue
        if txt.lower().startswith("related:"):
            continue
        paras.append(txt)

    # fallback containers
    if not paras:
        for p in soup.select(
            "div[id^='bc_article_content'] p, "
            "div.cz-article-body p, "
            "div.cz_article_body p, "
            "article p"
        ):
            txt = clean_text(p.get_text(" ", strip=True))
            if len(txt.split()) < 4:
                continue
            if txt.lower().startswith("related:"):
                continue
            paras.append(txt)

    body_text = " ".join(paras)

    if body_text:
        summary = body_text.strip()
    else:
        summary = None

    if body_text:
        article_embedding = embedding_model.encode(body_text, convert_to_tensor=True)
        similarity = util.pytorch_cos_sim(fraud_embedding, article_embedding).item()
    else:
        similarity = 0.0

    if author == "unknown" and published == "unknown" and not paras:
        with open("debug_article.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"[debug] wrote debug_article.html for {url} (layout looked different than expected)")

    return {
        "title": title,
        "url": url,
        "author": author,
        "published": published,
        "summary": summary,
        "similarity": similarity,
    }


# storing the articles

def write_outputs(results, json_path="breaches.json", txt_path="report.txt"):
    """
    Save output to both JSON (structured) and TXT (readable).
    """
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    with open(txt_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write("----\n")
            f.write(f"Title: {r.get('title')}\n")
            f.write(f"URL: {r.get('url')}\n")
            f.write(f"Author: {r.get('author')}\n")
            f.write(f"Published: {r.get('published')}\n")
            f.write("Summary:\n")
            summary_text = r.get("summary") or "None"
            wrapped = textwrap.fill(summary_text, width=100)
            f.write(wrapped + "\n\n")


def insert_df_into_supabase(df: pd.DataFrame, table_name: str = "articles"):
    """
    Upsert into Supabase on url.
    Requires a UNIQUE constraint on articles.url (which you now have).
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase env vars missing, skipping Supabase insert.")
        return

    if df.empty:
        print("DataFrame empty, skipping Supabase insert.")
        return

    # de-dupe locally by url just to avoid noise
    df = df.drop_duplicates(subset=["title"])

    cols_to_keep = ["title", "url", "author", "published", "summary", "similarity"]
    df_to_insert = df[cols_to_keep].copy()
    df_to_insert = df_to_insert.where(pd.notnull(df_to_insert), None)
    records = df_to_insert.to_dict(orient="records")

    if not records:
        print("No records to insert into Supabase.")
        return

    try:
        # requires UNIQUE(url) on the table → which you have as articles_url_key
        supabase.table(table_name).upsert(records, on_conflict="url").execute()
        print(f"Upserted {len(records)} rows into '{table_name}'")
    except Exception as e:
        print(f"Error inserting into Supabase: {e}")



# ------------ ANALYSIS / VISUALS ------------

def normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["published_dt"] = pd.to_datetime(df["published"], errors="coerce")
    return df


def plot_articles_over_time(df: pd.DataFrame, outfile: str = "articles_per_week.png"):
    df = normalize_dates(df)
    df = df.dropna(subset=["published_dt"]).set_index("published_dt")

    if df.empty:
        print("[info] No valid dates for articles_per_week plot.")
        return

    weekly = df.resample("W")["url"].count()

    plt.figure(figsize=(10, 5))
    weekly.plot()
    plt.title("Articles per Week")
    plt.xlabel("Week")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()
    print(f"[info] Saved {outfile}")


def plot_top_phrases(df: pd.DataFrame, outfile: str = "top_phrases.png"):
    texts = df["summary"].fillna("").tolist()
    if not any(texts):
        print("[info] No summaries for top_phrases plot.")
        return

    vec = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(2, 3),
        min_df=3,
        max_features=5000
    )
    X = vec.fit_transform(texts)
    scores = np.asarray(X.mean(axis=0)).ravel()
    terms = np.array(vec.get_feature_names_out())

    if len(terms) == 0:
        print("[info] No n-grams produced for top_phrases.")
        return

    top_k = min(10, len(terms))
    top_idx = scores.argsort()[::-1][:top_k]
    top_terms = terms[top_idx]
    top_vals = scores[top_idx]

    plt.figure(figsize=(10, 6))
    y = np.arange(len(top_terms))[::-1]
    plt.barh(y, top_vals)
    plt.yticks(y, top_terms)
    plt.title("Top Fraud-Related Phrases (TF-IDF, 2–3-grams)")
    plt.xlabel("Mean TF-IDF")
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()
    print(f"[info] Saved {outfile}")


def plot_keyword_trends(df: pd.DataFrame, outfile: str = "keyword_trends.png", top_k: int = 5):
    df = normalize_dates(df)
    df = df.dropna(subset=["published_dt"]).copy()
    if df.empty:
        print("[info] No valid dates for keyword_trends plot.")
        return

    df["week"] = df["published_dt"].dt.to_period("W").dt.start_time
    df["lc"] = df["summary"].fillna("").str.lower()

    rows = []
    for week, grp in df.groupby("week"):
        text = " ".join(grp["lc"].tolist())
        counts = {kw: text.count(kw) for kw in FRAUD_LEXICON}
        counts["week"] = week
        rows.append(counts)

    trend_df = pd.DataFrame(rows).sort_values("week")
    if trend_df.empty:
        print("[info] No data for keyword trends.")
        return

    totals = trend_df.drop(columns=["week"]).sum().sort_values(ascending=False)
    keep = totals.head(top_k).index.tolist()

    plt.figure(figsize=(12, 6))
    for kw in keep:
        plt.plot(trend_df["week"], trend_df[kw], label=kw)
    plt.title("Fraud Keyword Mentions Over Time")
    plt.xlabel("Week")
    plt.ylabel("Mentions")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()
    print(f"[info] Saved {outfile}")


# ------------ MAIN PIPELINE ------------

def main(max_articles=300, similarity_threshold=0.45, max_pages=30):
    links = get_article_links_from_tag(max_links=max_articles, max_pages=max_pages)
    print(f"[info] collected {len(links)} article links")

    all_results = []
    filtered_results = []

    for art in links:
        try:
            data = summarize_article(art["url"])
            all_results.append(data)

            if data["similarity"] >= similarity_threshold:
                filtered_results.append(data)
        except Exception as e:
            print(f"Error processing article {art['url']}: {e}")

    df = pd.DataFrame(all_results)

    if df.empty:
        print("[info] No articles scraped. Exiting.")
        return df, pd.DataFrame()

    df = df.sort_values("similarity", ascending=False, ignore_index=True)
    df = df.drop_duplicates(subset=["title"])

    print("\nAll articles with similarity (top 20)")
    print(df[["similarity", "title", "url"]].head(20))
    print(f"[info] total articles in df: {len(df)}")

    # save snapshots
    df.to_csv("articles_all.csv", index=False)
    print("[info] Saved articles_all.csv")

    fraud_df = df[df["similarity"] >= similarity_threshold].copy()
    fraud_df.to_csv("fraud_articles.csv", index=False)
    print(f"[info] Saved fraud_articles.csv with {len(fraud_df)} rows")

    # write human-readable outputs for filtered (fraud-like) ones
    write_outputs(fraud_df.to_dict(orient="records"))

    # visuals for the filtered set
    if not fraud_df.empty:
        plot_articles_over_time(fraud_df)
        plot_top_phrases(fraud_df)
        plot_keyword_trends(fraud_df)
    else:
        print("[info] No articles above similarity threshold; skipping plots.")

    # insert everything into supabase
    insert_df_into_supabase(df, table_name="articles")

    return df, fraud_df


if __name__ == "__main__":
    main(max_articles=2000, similarity_threshold=0.45, max_pages=75)
