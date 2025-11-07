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
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()  

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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


def clean_text(txt: str) -> str:
    """Collapse whitespace and trim."""
    return re.sub(r"\s+", " ", txt).strip()


def get_article_links_from_tag(max_links: int = 20):
    """
    Fetch ONLY https://www.bleepingcomputer.com/tag/data-breach/
    Extract article links from that page.

    Keep:
      - internal links
      - URLs containing '/news/security/' (breach writeups live here)
      - anchor text with 3+ words (to avoid junk links)

    Return [{title, url}, ...] up to max_links.
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(TAG_URL, timeout=10)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    articles = []
    seen_urls = set()

    for a in soup.select("a[href]"):
        href = a["href"].strip()
        full_url = urljoin(BASE_URL, href)

        # must stay on same domain
        if not full_url.startswith(BASE_URL):
            continue

        # must look like an article, not nav/etc.
        if "/news/security/" not in full_url.lower():
            continue

        # skip garbage promo
        if "webinar" in full_url.lower():
            continue

        # anchor text as candidate title
        title = a.get_text(strip=True)
        if not title or len(title.split()) < 3:
            continue

        # dedupe
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            articles.append({
                "title": title,
                "url": full_url,
            })

        if len(articles) >= max_links:
            break

    return articles


def summarize_article(url: str) -> dict:
    """
    Visit an article URL and pull:
      - title from <h1>
      - author from <a rel="author"> ... <span itemprop="name">
      - published date from <li class="cz-news-date">
      - summary from first ~6 paragraphs

    Assumes:
      - .cz-news-date exists (your observation)
      - rel="author" exists wrapping the byline (your observation)
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(url, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    #Title 
    title_tag = soup.select_one("h1")
    title = clean_text(title_tag.get_text()) if title_tag else None

    #Published date 
    date_tag = soup.select_one(".cz-news-date")
    published = clean_text(date_tag.get_text()) if date_tag else "unknown"

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

    # in case the article has diff elements for whatever reason
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
    #Insert DataFrame rows into a Supabase table.
    cols_to_keep = ["title", "url", "author", "published", "summary", "similarity"]
    df_to_insert = df[cols_to_keep].copy()

    # Replace NaN with None so it doesnt break supabase insert
    df_to_insert = df_to_insert.where(pd.notnull(df_to_insert), None)

    records = df_to_insert.to_dict(orient="records")

    if not records:
        print("No records to insert into Supabase.")
        return

    try:
        resp = supabase.table(table_name).insert(records).execute()
        print(f"Inserted {len(records)} rows into '{table_name}'")
    except Exception as e:
        print(f"Error inserting into Supabase: {e}")


def main(max_articles=20, similarity_threshold=0.45):
    links = get_article_links_from_tag(max_links=max_articles)

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
    # turns results into a df
    df = pd.DataFrame(all_results)
    df = df.sort_values("similarity", ascending=False, ignore_index=True)

    print("\n All articles with similarity ")
    print(df[["similarity", "title", "url"]])

    # writes results into the txt and json formats
    write_outputs(filtered_results)

    # insert everything into supabase
    insert_df_into_supabase(df, table_name="articles")

    return df, filtered_results


if __name__ == "__main__":
    main(20)

