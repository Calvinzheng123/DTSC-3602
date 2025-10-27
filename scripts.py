import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import time
import random
import textwrap

BASE = "https://www.bleepingcomputer.com"
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


def get_article_links_from_tag(tag_url: str, max_links: int = 20):
    """
    Hit the data-breach tag page once and pull all article URLs.
    Grab every <a>, keep /news/security/ links with headline-like text.
    Return [{title, url}, ...] in order (up to max_links).
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(tag_url, timeout=10)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    articles = []
    seen_urls = set()

    for a in soup.select("a[href]"):
        href = a["href"].strip()
        full_url = urljoin(BASE, href)

        # Must look like a real security news article
        if "/news/security/" not in full_url.lower():
            continue
        if "webinar" in full_url.lower():
            continue

        # Anchor text as possible title
        title = a.get_text(strip=True)
        if not title or len(title.split()) < 3:
            continue  # skip junk like "Read more"

        if full_url not in seen_urls:
            seen_urls.add(full_url)
            articles.append({
                "title": title,
                "url": full_url
            })

        if len(articles) >= max_links:
            break

    return articles


def summarize_article(url: str) -> dict:
    """
    Visit an article URL and pull title, author, published date,
    and build a short summary from the first paragraphs.
    Tries multiple layouts for author/date because BC isn't consistent.
    """
    time.sleep(random.uniform(0.8, 1.6))

    r = session.get(url, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # ----- title -----
    title_tag = soup.select_one("h1")
    title = clean_text(title_tag.get_text()) if title_tag else None

    # ---------- AUTHOR ----------
    author = None

    # 1. normal layout
    block_author = soup.select_one(".bc_article_author")
    if block_author:
        author = clean_text(block_author.get_text())

    # 2. author might be in something like span.author or div.author
    if author is None:
        alt_author = soup.select_one("span.author, div.author, .article_author, .post_author")
        if alt_author:
            author = clean_text(alt_author.get_text())

    # 3. try to extract "By <name>" patterns from the top area
    if author is None:
        # grab any text near the top of the article header
        header_block = soup.select_one(".bc_article_top, .bc_article_header, header, .article_header")
        if header_block:
            header_text = clean_text(header_block.get_text())
            # look for "By Someone"
            m = re.search(r"\b[Bb]y\s+([A-Z][A-Za-z .'-]+)", header_text)
            if m:
                author = m.group(1).strip()

    # final cleanup
    if author:
        if author.lower().startswith("by "):
            author = author[3:].strip()
    else:
        author = "unknown"

    # ---------- PUBLISHED DATE ----------
    published = None

    # 1. normal layout
    block_date = soup.select_one(".bc_article_date")
    if block_date:
        published = clean_text(block_date.get_text())

    # 2. in some versions, date is just in a <time> tag
    if published is None:
        t = soup.select_one("time")
        if t:
            published = clean_text(t.get_text())

    # 3. try common classes like .date or .post_date
    if published is None:
        alt_date = soup.select_one(".date, .post_date, span.date, div.date")
        if alt_date:
            published = clean_text(alt_date.get_text())

    if not published:
        published = "unknown"

    # ---------- BODY / SUMMARY ----------
    paras = []

    # main pattern they use
    for p in soup.select("div#bc_article_content p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt.split()) < 4:
            continue
        if txt.lower().startswith("related:"):
            continue
        paras.append(txt)

    # fallback pattern
    if not paras:
        for p in soup.select("div[id^='bc_article_content'] p, article p"):
            txt = clean_text(p.get_text(" ", strip=True))
            if len(txt.split()) < 4:
                continue
            if txt.lower().startswith("related:"):
                continue
            paras.append(txt)

    body_text = " ".join(paras[:6])

    summary = None
    if body_text:
        sentences = re.split(r"(?<=[.?!])\s+", body_text)
        summary = " ".join(sentences[:3]).strip()

    if (not summary or summary == "") and body_text:
        summary = body_text[:400].rstrip() + "..."

    # dump debug html if we really couldn't parse structure
    if author == "unknown" and published == "unknown" and not paras:
        with open("debug_article.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"[debug] wrote debug_article.html for {url} (layout was unexpected)")

    return {
        "title": title,
        "url": url,
        "author": author,
        "published": published,
        "summary": summary
    }


def main(max_articles=20, json_path="breaches.json", txt_path="report.txt"):
    # 1. get links from the tag page
    links = get_article_links_from_tag(TAG_URL, max_links=max_articles)

    # 2. scrape each article
    results = []
    for art in links:
        try:
            data = summarize_article(art["url"])
        except Exception as e:
            data = {
                "title": art["title"],
                "url": art["url"],
                "author": None,
                "published": None,
                "summary": None,
                "error": str(e),
            }
        results.append(data)

    # 3. save machine-friendly JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # 4. save human-readable TXT (wrapped lines, clean)
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

    # 5. still print to console, but this part is now just for a quick glance
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
