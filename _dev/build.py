#!/usr/bin/env python3
"""
build.py — build Fug's blog from sources.

Reads:
  _meta/nav.txt             nav items: "<slug>  <label>" per line
  _meta/page.html           page template w/ {{TITLE}} {{DESCRIPTION}} {{NAV}} {{CONTENT}}
  <cat>/<slug>/_post.html   individual post sources
  _static/*.html            static pages (about, etc.)

Writes:
  <cat>/<slug>/index.html   wrapped post page (URL: /<cat>/<slug>/)
  <cat>/index.html          category listing
  index.html                homepage — N most recent posts across categories
  <name>.html               static pages (about.html, etc.)
  feed.xml                  RSS feed

Run from repo root:  python3 _dev/build.py
Uses only the Python stdlib. No dependencies.
"""

import html
import math
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# config

ROOT       = Path(__file__).parent.parent.resolve()
META_DIR   = ROOT / "_meta"
STATIC_DIR = ROOT / "_static"
NAV_FILE   = META_DIR / "nav.txt"
TEMPLATE   = META_DIR / "page.html"

SITE_URL   = "https://xn--qckwd.com"
SITE_TITLE = "Fug"
SITE_DESC  = "Personal blog of Fug."

HOME_POST_LIMIT = 10
RSS_LIMIT       = 20
SPECIAL_SLUGS   = {"home", "about", "rss"}

META_RE  = re.compile(r'<meta\s+name=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']', re.I)
TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.I)
BODY_RE  = re.compile(r"<body[^>]*>(.*)</body>", re.I | re.S)

# ---------------------------------------------------------------------------
# parsing

def parse_source(path):
    """Parse a post or static page source. Returns dict of metadata + body."""
    text = path.read_text(encoding="utf-8")
    meta = {m.group(1).lower(): m.group(2) for m in META_RE.finditer(text)}
    t = TITLE_RE.search(text)
    if t:
        meta["title"] = t.group(1).strip()
    b = BODY_RE.search(text)
    body = b.group(1).strip() if b else text
    return {
        "title":       meta.get("title", "(untitled)"),
        "date":        meta.get("date", ""),
        "excerpt":     meta.get("excerpt", ""),
        "cover":       meta.get("cover", ""),
        "description": meta.get("description", SITE_DESC),
        "body":        body,
    }


def read_time(body_html):
    text = re.sub(r"<[^>]+>", " ", body_html)
    return max(1, math.ceil(len(text.split()) / 200))


# ---------------------------------------------------------------------------
# nav + template

def read_nav():
    nav = []
    for line in NAV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2:
            nav.append((parts[0], parts[1]))
    return nav


def slug_to_url(slug):
    return {"home": "/", "about": "/about.html", "rss": "/feed.xml"}.get(slug, f"/{slug}/")


def render_nav(nav):
    return "\n        ".join(
        f'<li><a href="{slug_to_url(s)}">{html.escape(l)}</a></li>'
        for s, l in nav
    )


def render_page(template, title, description, nav_html, content):
    return (template
            .replace("{{TITLE}}",       html.escape(title))
            .replace("{{DESCRIPTION}}", html.escape(description))
            .replace("{{NAV}}",         nav_html)
            .replace("{{CONTENT}}",     content))


# ---------------------------------------------------------------------------
# rendering

def render_post_article(post):
    rt = read_time(post["body"])
    date = html.escape(post["date"])
    meta_line = f"{date} — {rt} min read" if post["date"] else f"{rt} min read"
    return (
        '<article class="post-content">\n'
        f'      <h1 class="post-content-title">{html.escape(post["title"])}</h1>\n'
        f'      <div class="post-content-meta">{meta_line}</div>\n'
        '      <div class="post-content-body">\n'
        f'{post["body"]}\n'
        '      </div>\n'
        '    </article>'
    )


def render_entry(post, cat_slug, post_slug):
    url = f"/{cat_slug}/{post_slug}/"
    title = html.escape(post["title"])
    date = html.escape(post["date"])
    excerpt = html.escape(post["excerpt"])

    cover_html = ""
    if post["cover"]:
        covers = [c.strip() for c in post["cover"].split(",") if c.strip()]
        if len(covers) == 1:
            cover_html = (
                '\n          <span class="post-entry-cover post-entry-cover--single">'
                f'<img src="{url}{html.escape(covers[0])}" alt=""></span>'
            )
        elif len(covers) >= 2:
            imgs = "".join(f'<img src="{url}{html.escape(c)}" alt="">' for c in covers[:3])
            cover_html = (
                '\n          <span class="post-entry-cover post-entry-cover--grid">'
                f'{imgs}</span>'
            )

    return (
        '      <li class="post-entry">\n'
        f'        <a class="post-entry-link" href="{url}">\n'
        f'          {title}\n'
        f'          <span class="post-entry-date">{date}</span>{cover_html}\n'
        '        </a>\n'
        f'        <p class="post-entry-excerpt">{excerpt}</p>\n'
        '      </li>'
    )


def render_entries_list(entries):
    return (
        '    <ul class="post-entries">\n'
        + "\n".join(entries) + "\n"
        '    </ul>'
    )


# ---------------------------------------------------------------------------
# RSS

def rfc822(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except ValueError:
        return ""


def write_feed(posts):
    feed_url = f"{SITE_URL}/feed.xml"
    build_date = format_datetime(datetime.now(timezone.utc))

    items = []
    for post, cat_slug, post_slug in posts:
        url = f"{SITE_URL}/{cat_slug}/{post_slug}/"
        items.append(
            '    <item>\n'
            f'      <title>{html.escape(post["title"])}</title>\n'
            f'      <link>{url}</link>\n'
            f'      <guid isPermaLink="true">{url}</guid>\n'
            f'      <pubDate>{rfc822(post["date"])}</pubDate>\n'
            f'      <description>{html.escape(post["excerpt"])}</description>\n'
            '    </item>'
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '  <channel>\n'
        f'    <title>{SITE_TITLE}</title>\n'
        f'    <link>{SITE_URL}/</link>\n'
        f'    <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>\n'
        f'    <description>{SITE_DESC}</description>\n'
        '    <language>en-us</language>\n'
        f'    <lastBuildDate>{build_date}</lastBuildDate>\n'
        + ("\n".join(items) + "\n" if items else "")
        + '  </channel>\n'
        '</rss>\n'
    )
    (ROOT / "feed.xml").write_text(rss, encoding="utf-8")


# ---------------------------------------------------------------------------
# build

def collect_posts(cat_slugs):
    posts = []
    for cat_slug in cat_slugs:
        cat_dir = ROOT / cat_slug
        if not cat_dir.is_dir():
            continue
        for post_dir in sorted(cat_dir.iterdir()):
            if not post_dir.is_dir():
                continue
            src = post_dir / "_post.html"
            if not src.exists():
                continue
            post = parse_source(src)
            posts.append((post, cat_slug, post_dir.name))
    posts.sort(key=lambda x: x[0]["date"], reverse=True)   # ISO dates sort lex = chrono
    return posts


def build():
    nav = read_nav()
    cat_slugs  = [s for s, _ in nav if s not in SPECIAL_SLUGS]
    cat_labels = dict(nav)
    template   = TEMPLATE.read_text(encoding="utf-8")
    nav_html   = render_nav(nav)

    posts = collect_posts(cat_slugs)

    # individual post pages
    for post, cat_slug, post_slug in posts:
        article = render_post_article(post)
        page = render_page(
            template,
            f'{post["title"]} — {SITE_TITLE}',
            post["excerpt"] or SITE_DESC,
            nav_html,
            article,
        )
        (ROOT / cat_slug / post_slug / "index.html").write_text(page, encoding="utf-8")

    # category index pages
    for cat_slug in cat_slugs:
        cat_posts = [p for p in posts if p[1] == cat_slug]
        entries = [render_entry(p, cs, ps) for p, cs, ps in cat_posts]
        heading = f'    <h1 class="post-content-title">{html.escape(cat_labels[cat_slug])}</h1>\n'
        if entries:
            body = heading + render_entries_list(entries)
        else:
            body = heading + '    <p class="post-entry-excerpt">No posts yet.</p>'
        page = render_page(
            template,
            f'{cat_labels[cat_slug]} — {SITE_TITLE}',
            SITE_DESC,
            nav_html,
            body,
        )
        (ROOT / cat_slug / "index.html").write_text(page, encoding="utf-8")

    # homepage
    recent = posts[:HOME_POST_LIMIT]
    entries = [render_entry(p, cs, ps) for p, cs, ps in recent]
    if entries:
        body = render_entries_list(entries)
    else:
        body = '    <p class="post-entry-excerpt">No posts yet.</p>'
    page = render_page(template, SITE_TITLE, SITE_DESC, nav_html, body)
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    # static pages
    if STATIC_DIR.is_dir():
        for src in sorted(STATIC_DIR.glob("*.html")):
            static = parse_source(src)
            page = render_page(
                template,
                f'{static["title"]} — {SITE_TITLE}',
                static["description"],
                nav_html,
                static["body"],
            )
            (ROOT / src.name).write_text(page, encoding="utf-8")

    # RSS
    write_feed(posts[:RSS_LIMIT])

    plural = "y" if len(cat_slugs) == 1 else "ies"
    print(f"built {len(posts)} post(s), {len(cat_slugs)} categor{plural}")


if __name__ == "__main__":
    build()
