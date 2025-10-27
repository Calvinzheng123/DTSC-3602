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

    # ---- Title ----
    title_tag = soup.select_one("h1")
    title = clean_text(title_tag.get_text()) if title_tag else None

    # ---- Published date ----
    date_tag = soup.select_one(".cz-news-date")
    published = clean_text(date_tag.get_text()) if date_tag else "unknown"

    author_tag = soup.select_one('a[rel="author"] span[itemprop="name"]')
    if author_tag:
        author = clean_text(author_tag.get_text())
    else:
        fallback_tag = soup.select_one('[itemprop="name"]')
        author = clean_text(fallback_tag.get_text()) if fallback_tag else "unknown"

    # ---- Body / Summary ----
    paras = []

    # main container (older layout)
    for p in soup.select("div#bc_article_content p"):
        txt = clean_text(p.get_text(" ", strip=True))
        # filter garbage like "Related:"
        if len(txt.split()) < 4:
            continue
        if txt.lower().startswith("related:"):
            continue
        paras.append(txt)

    # fallback: newer container guesses
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

    # Debug if we totally failed to parse useful content
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
    }


def write_outputs(results, json_path="breaches.json", txt_path="report.txt"):
    """
    Save output to both JSON (structured) and TXT (readable).
    """
    # structured / machine-friendly
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # human readable
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
    # Pull links from tag page
    links = get_article_links_from_tag(max_links=max_articles)

    # Scrape each article and summarize it
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

    # Save to breaches.json and report.txt
    write_outputs(results)

    # Print quick preview to console so you can sanity check
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
