"""
Calls the Claude API (with the web_search tool) to regenerate the four
narrative "Insights" cards on a monthly cadence, so that section stops being
frozen text and instead reflects roughly-current research.

Requires ANTHROPIC_API_KEY (your own key from console.anthropic.com --
this one is NOT free; usage-based, but at this volume -- one call a month,
a couple thousand tokens plus a handful of searches -- expect cents to low
single-digit dollars per month, not a real budget concern).

Standard library only.
"""
import os, json, urllib.request, urllib.error
from datetime import datetime, timezone

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

PROMPT = """You are a research assistant for a buy-and-hold real estate investor
based in New Jersey who is expanding into out-of-state markets.

Search the web for current information (this month) on these four topics and
write one paragraph (80-120 words) per topic, in plain factual prose, no
markdown formatting, no headers inside the paragraph:

1. Which U.S. metro markets currently offer the best cash-flow potential for
   buy-and-hold rental investors, and why.
2. The current state of creative financing (seller financing, DSCR loans,
   subject-to, lease options) for real estate investors.
3. Current best practices for managing rental property remotely / out of state.
4. How landlord-tenant law friendliness varies by state right now, and why it
   matters for investors choosing a market.

Respond with ONLY a JSON object -- no markdown code fences, no commentary
before or after -- in exactly this shape:
{
  "cards": [
    {"title": "short title", "body": "the paragraph", "sources": ["Publisher A", "Publisher B"]},
    {"title": "...", "body": "...", "sources": ["..."]},
    {"title": "...", "body": "...", "sources": ["..."]},
    {"title": "...", "body": "...", "sources": ["..."]}
  ]
}
"""


def call_claude():
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def extract_text(data):
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts).strip()


def clean_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def main():
    if not API_KEY:
        print("[warn] No ANTHROPIC_API_KEY set -- skipping insight generation. "
              "The dashboard will keep showing its bundled default cards.")
        return
    try:
        raw = call_claude()
        text = extract_text(raw)
        parsed = json.loads(clean_json_text(text))
        cards = parsed.get("cards", [])
        if not cards:
            raise ValueError("no cards in response")
    except Exception as e:
        print(f"[warn] insight generation failed: {e}")
        return

    out = {"updated": datetime.now(timezone.utc).isoformat(), "cards": cards}
    with open(os.path.join(DATA_DIR, "insights_data.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"Done -> data/insights_data.json ({len(cards)} cards)")


if __name__ == "__main__":
    main()
