"""
Pulls the most recent items from each feed in config/rss_feeds.json and writes
data/rss_data.json for the dashboard's rotating headline carousel.

Standard library only (handles both RSS 2.0 <item> and Atom <entry> formats,
since e.g. Blogger-hosted feeds like Calculated Risk serve Atom).

NOTE: built without live internet access in my working environment -- feed
URLs were checked against search-engine snippets showing real content, but
if a feed's exact field layout changed, this script degrades gracefully
(skips that feed, logs a warning) rather than crashing the whole run.
"""
import os, json, re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "rss_feeds.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ITEMS_PER_FEED = 4
MAX_TOTAL_ITEMS = 24


def strip_html(s):
    return re.sub(r"<[^<]+?>", "", s or "").strip()


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dashboard-rss-bot)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_date(raw):
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_feed(xml_bytes, source_name):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"[warn] could not parse XML for {source_name}: {e}")
        return items

    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item")[:ITEMS_PER_FEED]:
            title = strip_html(item.findtext("title"))
            link = (item.findtext("link") or "").strip()
            pub = parse_date(item.findtext("pubDate"))
            summary = strip_html(item.findtext("description"))[:200]
            items.append({
                "title": title, "link": link, "source": source_name,
                "published": pub.isoformat() if pub else None,
                "summary": summary,
            })
        return items

    # Atom fallback
    entries = root.findall("atom:entry", ATOM_NS)
    for entry in entries[:ITEMS_PER_FEED]:
        title = strip_html(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        link_el = entry.find("atom:link", ATOM_NS)
        link = link_el.get("href") if link_el is not None else ""
        pub_raw = (entry.findtext("atom:published", default="", namespaces=ATOM_NS)
                   or entry.findtext("atom:updated", default="", namespaces=ATOM_NS))
        pub = parse_date(pub_raw)
        summary = strip_html(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))[:200]
        items.append({
            "title": title, "link": link, "source": source_name,
            "published": pub.isoformat() if pub else None,
            "summary": summary,
        })
    return items


def main():
    with open(CONFIG_PATH) as f:
        feeds = json.load(f)

    all_items = []
    for feed in feeds:
        try:
            raw = fetch_bytes(feed["url"])
            items = parse_feed(raw, feed["name"])
            all_items.extend(items)
            print(f"[ok] {feed['name']}: {len(items)} items")
        except urllib.error.HTTPError as e:
            print(f"[warn] {feed['name']} HTTP {e.code}: {e.reason}")
        except Exception as e:
            print(f"[warn] {feed['name']} failed: {e}")

    # Sort newest-first where we have a parseable date; undated items sink to the bottom.
    def sort_key(it):
        return it["published"] or "0000-00-00"
    all_items.sort(key=sort_key, reverse=True)
    all_items = all_items[:MAX_TOTAL_ITEMS]

    out = {"updated": datetime.now(timezone.utc).isoformat(), "items": all_items}
    with open(os.path.join(DATA_DIR, "rss_data.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"Done -> data/rss_data.json ({len(all_items)} items)")


if __name__ == "__main__":
    main()
