#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Steam Deck Refurbished (US) - ANY in-stock monitor (single URL)
- Only monitors: https://store.steampowered.com/sale/steamdeckrefurbished/
- To reduce false positives:
  * Only scans <a> / <button> text and common accessibility attrs
  * Only counts strong phrases: "Add to Cart", "Buy Now", "In Stock"
  * Requires local context to include "Steam Deck" and "Refurbished"
- Single-run script — perfect for GitHub Actions cron.

Env:
  DISCORD_WEBHOOK  (required)
"""

import os, re, time, json, hashlib, logging, requests
from bs4 import BeautifulSoup

URL = "https://store.steampowered.com/sale/steamdeckrefurbished/"

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
STATE_FILE = os.path.join(os.path.dirname(__file__), ".any_instock_state.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Strong, low-noise signals ONLY
POSITIVE_STRICT = [
    r"\badd\s*to\s*cart\b",
    r"\bbuy\s*now\b",
    r"\bin\s*stock\b",
]

NEGATIVE_HINTS = [
    r"\bout\s*of\s*stock\b",
    r"\bunavailable\b",
    r"\bsold\s*out\b",
    r"\bnotify\s*me\b",
]

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()

def context_looks_like_refurb(text: str) -> bool:
    t = norm(text)
    return ("steam deck" in t) and ("refurb" in t or "certified refurbished" in t or "refurbished" in t)

def has_positive_in_context(node) -> bool:
    """
    Check whether this anchor/button node is a 'buy' signal with a nearby context
    that looks like a Steam Deck refurb card.
    """
    texts = [norm(node.get_text(" ", strip=True))]
    for key in ("aria-label", "title"):
        v = node.get(key)
        if v:
            texts.append(norm(v))
    combined = " ".join(texts)

    # require a positive phrase
    if not any(re.search(p, combined, flags=re.I) for p in POSITIVE_STRICT):
        return False
    # and NOT a negative phrase
    if any(re.search(p, combined, flags=re.I) for p in NEGATIVE_HINTS):
        return False

    # now look at local context (walk up a few parents and grab text)
    ctx_chunks = []
    parent = node
    steps = 0
    while parent is not None and steps < 4:  # climb up to a few levels
        try:
            ctx_chunks.append(parent.get_text(" ", strip=True))
        except Exception:
            pass
        parent = getattr(parent, "parent", None)
        steps += 1
    ctx = " ".join(ctx_chunks)

    return context_looks_like_refurb(ctx)

def detect_in_stock(soup: BeautifulSoup) -> bool:
    # Scan buttons and links only
    for n in soup.select("a, button"):
        if has_positive_in_context(n):
            return True
    return False

def post_discord(msg: str):
    try:
        r = requests.post(WEBHOOK, json={"content": msg}, timeout=15)
        if r.status_code >= 300:
            logging.error("Discord webhook error %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logging.error("Failed to post to Discord: %s", e)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("Failed to write state: %s", e)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    if not WEBHOOK:
        logging.error("Missing DISCORD_WEBHOOK environment variable.")
        return

    state = load_state()
    last_hash = state.get("last_hash")

    # Fetch single URL
    r = requests.get(URL, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    if detect_in_stock(soup):
        page_hash = hashlib.sha256(norm(soup.get_text(" ", strip=True)).encode("utf-8")).hexdigest()[:16]
        if page_hash != last_hash:
            ts = int(time.time())
            post_discord(f"🎉 **Steam Deck 官翻（美区）页面出现可购买/有货信号！**\n🔗 {URL}\n⏱️ <t:{ts}:F>")
            state["last_hash"] = page_hash
            save_state(state)
        else:
            logging.info("Positive signal detected but page hash unchanged; skip duplicate alert.")
    else:
        logging.info("No positive buy signal on monitored URL.")

if __name__ == "__main__":
    main()
