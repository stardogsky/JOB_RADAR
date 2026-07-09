"""Discovery helper: mine public Telegram channel previews (t.me/s/<channel>)
for company ATS boards and emit ready-to-paste entries for
sources.ats.companies.

NOT part of the daily cron. Run on demand (locally or a manual workflow):
    python -m tools.mine_telegram                 # channels from config.telegram_mine.channels
    python -m tools.mine_telegram geekjobs ...     # explicit channels

No third-party deps beyond PyYAML (already used). Network required.
"""
import re
import sys
import urllib.request

try:
    import yaml
except ImportError:
    yaml = None

UA = "Mozilla/5.0 (compatible; jobradar-miner/1.0)"

# Hosted ATS domains where the slug lives IN the URL -> reliable {ats, slug}.
PATTERNS = {
    "greenhouse": re.compile(r"(?:job-boards|boards)\.greenhouse\.io/([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)"),
    "recruitee": re.compile(r"https?://([A-Za-z0-9_-]+)\.recruitee\.com"),
    "smartrecruiters": re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_.-]+)"),
    "breezy": re.compile(r"https?://([A-Za-z0-9_-]+)\.breezy\.hr"),
    "workable": re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
}
# ATS we do NOT collect yet -> report the gap so the list can grow later.
UNSUPPORTED = {
    "workday": re.compile(r"([A-Za-z0-9_-]+)\.\w+\.myworkdayjobs\.com"),
    "teamtailor": re.compile(r"https?://([A-Za-z0-9_-]+)\.teamtailor\.com"),
}
HREF = re.compile(r'href="([^"]+)"')
_SKIP = {"jobs", "job", "careers", "api", "v1", "v0", "posting-api"}


def fetch(channel: str) -> str:
    url = "https://t.me/s/" + channel
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def extract(html_or_urls):
    if isinstance(html_or_urls, list):
        urls = html_or_urls
    else:
        urls = HREF.findall(html_or_urls)
    hosted, unsupported, custom = {}, {}, set()
    for u in urls:
        hit = False
        for ats, pat in PATTERNS.items():
            m = pat.search(u)
            if m and m.group(1).lower() not in _SKIP:
                hosted.setdefault((ats, m.group(1)), u)
                hit = True
                break
        if hit:
            continue
        for ats, pat in UNSUPPORTED.items():
            m = pat.search(u)
            if m:
                unsupported.setdefault((ats, m.group(1)), u)
                hit = True
                break
        if not hit and any(k in u for k in ("gh_jid=", "gh_src=", "ashby_jid=")):
            custom.add(u.split("?")[0])
    return hosted, unsupported, custom


def load_existing(cfg_path="config.yaml"):
    if not yaml:
        return set()
    try:
        cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
        return {(c["ats"], c["slug"]) for c in cfg["sources"]["ats"]["companies"]}
    except Exception:
        return set()


def main(argv):
    channels = argv[1:]
    if not channels and yaml:
        cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
        channels = cfg.get("telegram_mine", {}).get("channels", [])
    if not channels:
        print("no channels (pass as args or set telegram_mine.channels in config.yaml)")
        return 1
    existing = load_existing()
    hosted, unsup, custom = {}, {}, set()
    for ch in channels:
        try:
            h, u, c = extract(fetch(ch))
        except Exception as e:  # noqa: BLE001
            print("# %s: fetch failed: %s" % (ch, e))
            continue
        hosted.update(h); unsup.update(u); custom |= c
        print("# %s: %d hosted, %d unsupported, %d custom-domain" % (ch, len(h), len(u), len(c)))
    new = sorted((a, s) for (a, s) in hosted if (a, s) not in existing)
    print("\n# --- NEW: paste into sources.ats.companies (review names) ---")
    for ats, slug in new:
        name = slug.replace("-", " ").replace("_", " ").title()
        print('      - { ats: %s, slug: %s, name: "%s" }' % (ats, slug, name))
    if unsup:
        print("\n# --- unsupported ATS (not collected yet; consider adding) ---")
        for ats, slug in sorted(unsup):
            print("#   %s: %s" % (ats, slug))
    if custom:
        print("\n# --- custom-domain boards (slug not in URL; add manually) ---")
        for u in sorted(custom):
            print("#   " + u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
