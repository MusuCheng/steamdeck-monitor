#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Steam Deck Refurbished - ANY in-stock monitor (US-only)
- Triggers a Discord alert if ANY product on the certified refurbished SALE page(s)
  looks purchasable (broader phrase coverage). Supports multiple URLs.
"""

import os, re, time, json, hashlib, logging, requests
from bs4 import BeautifulSoup

URLS = [
    "https://store.steampowered.com/sale/steamdeckrefurbished/",   # correct sale path (primary)
    "https://store.steampowered.com/steamdeckrefurbished",         # legacy path (fallback)
]

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

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
    r"pre[-\s]*order",
    r"reserve",
]

STATE_FILE = os.path.join(os.path.dirname(__file__), ".any_instock_state.json")

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def has_positive_signal(soup: BeautifulSoup) -> bool:
    page_text = normalize_space(soup.get_text(" ", strip=True))
    for pat in POSITIVE_PHRASES:
        if re.search(pat, page_text, flags=re.I):
            return True

    nodes = soup.select("a, button")
    combined = " ".join(normalize_space(n.get_text(' ', strip=True)) for n in nodes)
    for pat in POSITIVE_PHRASES:
        if re.search(pat, combined, flags=re.I):
            return True

    attrs_text = []
    for n in nodes:
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

    triggered_url = None
    combined_text = ""

    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            if has_positive_signal(soup):
                triggered_url = url
            combined_text += " " + soup.get_text(" ", strip=True)
        except Exception as e:
            logging.warning("Fetch failed for %s: %s", url, e)

    if triggered_url:
        page_hash = hashlib.sha256(normalize_space(combined_text).encode("utf-8")).hexdigest()[:16]
        if page_hash != last_hash:
            ts = int(time.time())
            post_discord(f"🎉 **Steam Deck 官翻（美区）页面出现可购买/有货信号！**\n🔗 {triggered_url}\n⏱️ <t:{ts}:F>\n\n（提示：监控已使用 /sale/steamdeckrefurbished 路径，含旧地址兜底）")
            state["last_hash"] = page_hash
            save_state(state)
        else:
            logging.info("Positive signal but same page state; skip duplicate.")
    else:
        logging.info("No positive buy signal on monitored URLs.")

if __name__ == "__main__":
    main()
