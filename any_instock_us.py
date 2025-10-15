#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Steam Deck Refurbished - ANY in-stock monitor (US-only)
- Triggers a Discord alert if ANY product on the US certified refurbished page
  looks purchasable (broader phrase coverage to minimize misses).
- Designed for single-run execution (cron / GitHub Actions).

Env vars:
- DISCORD_WEBHOOK (required): your Discord webhook URL

Notes:
- This script parses both the whole-page text and button/link text to improve recall.
- If Valve changes the page significantly, you can add new phrases in POSITIVE_PHRASES.
"""

import os, re, time, json, hashlib, logging, requests
from bs4 import BeautifulSoup

URL = "https://store.steampowered.com/steamdeckrefurbished"  # US official refurb page
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Expanded positive phrases (case-insensitive; allow flexible spacing)
POSITIVE_PHRASES = [
    r"in\s*stock",
    r"available\s*now",
    r"availability:\s*in\s*stock",
    r"add\s*to\s*cart",
    r"add\s*to\s*basket",
    r"add\s*to\s*bag",
    r"buy\s*now",
    r"purchase",
    r"checkout",
    r"pre[-\s]*order",    # pre-order / preorder (in case Valve uses this)
    r"reserve",           # sometimes used on Valve pages
]

STATE_FILE = os.path.join(os.path.dirname(__file__), ".any_instock_state.json")

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def has_positive_signal(soup: BeautifulSoup) -> bool:
    # 1) Whole-page text search
    page_text = normalize_space(soup.get_text(" ", strip=True))
    for pat in POSITIVE_PHRASES:
        if re.search(pat, page_text, flags=re.I):
            return True

    # 2) Buttons / links text search (covers aria/alt content that may not be in main text)
    candidate_nodes = soup.select("a, button")
    combined = " ".join(normalize_space(n.get_text(" ", strip=True)) for n in candidate_nodes)
    for pat in POSITIVE_PHRASES:
        if re.search(pat, combined, flags=re.I):
            return True

    # 3) Attributes like aria-label / title (less common but cheap to scan)
    attrs_text = []
    for n in candidate_nodes:
        for key in ("aria-label", "title"):
            v = n.get(key)
            if v:
                attrs_text.append(normalize_space(v))
    combined_attrs = " ".join(attrs_text)
    for pat in POSITIVE_PHRASES:
        if re.search(pat, combined_attrs, flags=re.I):
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

    # Fetch
    r = requests.get(URL, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Detect
    if has_positive_signal(soup):
        # Hash only the visible text to avoid spamming the same page state
        page_hash = hashlib.sha256(normalize_space(soup.get_text(" ", strip=True)).encode("utf-8")).hexdigest()[:16]
        if page_hash != last_hash:
            ts = int(time.time())
            post_discord(f"🎉 **Steam Deck 官翻（美区）页面出现可购买/有货信号！**\n🔗 {URL}\n⏱️ <t:{ts}:F>\n\n（提示：信号来自“可购买”相关文案或按钮文本）")
            state["last_hash"] = page_hash
            save_state(state)
        else:
            logging.info("Positive signal detected but page hash unchanged; skipping duplicate alert.")
    else:
        logging.info("No positive buy signal found on page.")

if __name__ == "__main__":
    main()
