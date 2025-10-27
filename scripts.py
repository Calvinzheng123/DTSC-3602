import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import time
import random
import textwrap

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
    We keep:
      - URLs under /news/security/
      - Anchor text that looks like a real headline (>=3 words)
    Return [{title, url}, ...] up to max_links, in order.
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

        # Only keep internal security news links (breach stories live here)
        if not full_url.startswith(BASE_URL):
            continue
        if "/news/security/" not in full_url.lower():
            continue
        if "webinar" in full_url.lower():
            continue  # skip promo stuff

        # Use the anchor text as headline candidate
        title = a.get_text(strip=True)
        if not title or len(title.split()) < 3:
            continue  # kill junk like "Read more"

        # Deduplicate
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
      - author from <span itemprop="name">
      - published date from <li class="cz-news-date">
      - summary from first few paragraphs in article body
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(url, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # ---- Title ----
    title_tag = soup.select_one("h1")
    title = clean_text(title_tag.get_text()) if title_tag else None

    # ---- Author ----
    author_tag = soup.select_one('[itemprop="name"]')
    author = clean_text(author_tag.get_text()) if author_tag else "unknown"

    # ---- Published Date ----
    date_tag = soup.select_one(".cz-news-date")
    published = clean_text(date_tag.get_text()) if date_tag else "unknown"

    # ---- Body / Summary ----
    paras = []

    # Try legacy container first
    for p in soup.select("div#bc_article_content p"):
        txt = clean_text(p.get_text(" ", strip=True))
        # filter garbage
        if len(txt.split()) < 4:
            continue
        if txt.lower().startswith("related:"):
            continue
        paras.append(txt)

    # Fallback: newer content container(s)
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

    body_text = " ".join(paras[:6])

    if body_text:
        sentences = re.split(r"(?<=[.?!])\s+", body_text)
        summary = " ".join(sentences[:3]).strip()
        if not summary:
            summary = body_text[:400].rstrip() + "..."
    else:
        summary = None

    # Debug dump if somehow we got literally nothing meaningful
    if author == "unknown" and published == "unknown" and not paras:
        with open("debug_article.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"[debug] wrote debug_article.html for {url} because scraping failed on layout")

    return {
        "title": title,
        "url": url,
        "author": author,
        "published": published,
        "summary": summary,
    }


def write_outputs(results, json_path="breaches.json", txt_path="report.txt"):
    """
    Save machine-readable (JSON) and human-readable (TXT).
    """
    # JSON for feeding into code / dashboard
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # TXT for eyeballing / email / paste into Slack
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


def main(max_articles=20):
    # 1. pull the list of breach stories from the tag page
    links = get_article_links_from_tag(max_links=max_articles)

    # 2. fetch and summarize each story
    results = []
    for art in links:
        try:
            data = summarize_article(art["url"])
        except Exception as e:
            data = {
                "title": art["title"],
                "url": art["url"],
                "author": "error",
                "published": "error",
                "summary": f"ERROR: {e}",
            }
        results.append(data)

    # 3. save outputs
    write_outputs(results)

    # 4. optional: print a preview to console
    for r in results:
        print("----")
        print(f"Title: {r.get('title')}")
        print(f"URL: {r.get('url')}")
        print(f"Author: {r.get('author')}")
        print(f"Published: {r.get('published')}")
        print("Summary:")
        summary_text = r.get("summary") or "None"
        wrapped = textwrap.fill(summary_text, width=80)
        print(wrapped)
        print()

    return results


if __name__ == "__main__":
    main(20)
