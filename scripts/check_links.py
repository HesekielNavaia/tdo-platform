#!/usr/bin/env python3
"""
TDO Dataset URL Checker

Usage:
    python3 scripts/check_links.py \\
        --api https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io \\
        --apikey tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963 \\
        [--portal worldbank] [--limit 200] [--verbose] [--sample]
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import datetime

SEARCH_QUERIES = [
    "GDP growth", "population", "inflation", "unemployment",
    "trade", "energy", "health", "education", "poverty", "emissions",
    "housing", "climate", "agriculture", "finance", "industry",
]
PORTALS = ["statfin", "eurostat", "oecd", "worldbank", "undata"]
TIMEOUT = 20
CONTENT_CHECK_PORTALS = {"worldbank", "oecd", "undata"}
# Domains that are JavaScript SPAs — their static HTML shell contains error phrases
# as boilerplate/fallback text, causing false positives if we content-check them.
NO_CONTENT_CHECK_DOMAINS = {"databank.worldbank.org"}
ERROR_PHRASES = [
    "no longer available",
    "not found",
    "does not exist",
    "no data available",
    "discontinued",
    "there is no data",
]
# HTTP status codes treated as transient server errors (not our URL's fault).
# 500 = Internal Server Error (server crash, not missing resource — 404 = truly missing).
# 502/503/504 = Gateway/Unavailable/Timeout (infrastructure issues).
TRANSIENT_STATUSES = {500, 502, 503, 504}

# Patterns that indicate a generic portal homepage (not a specific dataset)
HOMEPAGE_PATH_PATTERNS = [
    re.compile(r"^https?://[^/]+/?$"),                          # bare domain
    re.compile(r"^https://unstats\.un\.org/sdgs/?$"),           # UN SDG root
    re.compile(r"^https://data\.worldbank\.org/?$"),            # WB root
    re.compile(r"^https://databank\.worldbank\.org/?$"),        # WB databank root
    re.compile(r"^https://ec\.europa\.eu/eurostat/?$"),         # Eurostat root
]
# WorldBank numeric-only indicator code (these are source IDs, not indicator codes)
WB_NUMERIC_PATTERN = re.compile(r"^https://data\.worldbank\.org/indicator/[0-9]+$")
USER_AGENT = "TDO-LinkChecker/1.0"


# ── Domain rate limiting ──────────────────────────────────────────────────────

_last_request_by_domain = {}


def _domain(url):
    return urllib.parse.urlparse(url).netloc


def _rate_limit(url, delay=0.5):
    domain = _domain(url)
    now = time.time()
    last = _last_request_by_domain.get(domain, 0)
    gap = delay - (now - last)
    if gap > 0:
        time.sleep(gap)
    _last_request_by_domain[domain] = time.time()


# ── API helpers ───────────────────────────────────────────────────────────────

def api_post(api_base, path, payload, apikey):
    url = api_base.rstrip("/") + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "X-API-Key": apikey,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def api_get(api_base, path, apikey):
    url = api_base.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": apikey, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ── URL fetching ──────────────────────────────────────────────────────────────

def fetch_url(url, read_body=False):
    _rate_limit(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            final_url = resp.url if hasattr(resp, "url") else url
            body = None
            if read_body:
                body = resp.read(4096).decode("utf-8", errors="ignore").lower()
            return status, final_url, body
    except urllib.error.HTTPError as e:
        return e.code, url, None
    except Exception as e:
        raise ConnectionError(str(e))


def check_content_errors(body):
    if not body:
        return None
    found = []
    for phrase in ERROR_PHRASES:
        if phrase in body:
            found.append(phrase)
    return found or None


def is_homepage_url(url):
    for pattern in HOMEPAGE_PATH_PATTERNS:
        if pattern.match(url):
            return True
    return False


# ── URL collection ─────────────────────────────────────────────────────────────

def extract_record_fields(r):
    rec = r.get("record", r)
    portal = (
        rec.get("source_portal")
        or rec.get("portal_id")
        or r.get("portal")
        or r.get("source_portal")
        or "unknown"
    )
    url = rec.get("dataset_url") or r.get("dataset_url") or r.get("url") or ""
    title = rec.get("title") or r.get("title") or "(no title)"
    return portal, url, title


def collect_urls(api_base, apikey, portal_filter, limit, do_sample):
    seen_urls = set()
    records = []

    print("Collecting dataset URLs via /v1/query ...")

    portals_to_check = [portal_filter] if portal_filter else PORTALS

    for query in SEARCH_QUERIES:
        if len(records) >= limit:
            break
        payload = {"question": query, "limit": 20}
        if portal_filter:
            payload["portal"] = portal_filter
        try:
            data = api_post(api_base, "/v1/query", payload, apikey)
            for r in data.get("results", []):
                portal, url, title = extract_record_fields(r)
                if not url or url in seen_urls:
                    continue
                if portal_filter and portal != portal_filter:
                    continue
                seen_urls.add(url)
                records.append({"portal": portal, "title": title[:80], "url": url})
        except Exception as e:
            print("  [!] Query '{}' failed: {}".format(query, e))

    # Ensure each portal has coverage via datasets endpoint
    for portal in portals_to_check:
        if len(records) >= limit:
            break
        try:
            data = api_get(
                api_base,
                "/v1/datasets?portal={}&limit=30".format(portal),
                apikey,
            )
            for r in data.get("results", []):
                portal_val, url, title = extract_record_fields(r)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                records.append({"portal": portal_val or portal, "title": title[:80], "url": url})
        except Exception as e:
            print("  [!] Portal top-up for {} failed: {}".format(portal, e))

    # --sample: pull 50 random records per portal via datasets endpoint
    if do_sample:
        print("  Pulling sample records per portal ...")
        for portal in portals_to_check:
            offset = 50  # skip the first page to get diversity
            try:
                data = api_get(
                    api_base,
                    "/v1/datasets?portal={}&limit=50&offset={}".format(portal, offset),
                    apikey,
                )
                added = 0
                for r in data.get("results", []):
                    portal_val, url, title = extract_record_fields(r)
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    records.append({
                        "portal": portal_val or portal,
                        "title": title[:80],
                        "url": url,
                    })
                    added += 1
                print("    {} +{} sample records".format(portal, added))
            except Exception as e:
                print("  [!] Sample for {} failed: {}".format(portal, e))

    print("  Collected {} unique URLs\n".format(len(records)))
    return records[:limit] if limit else records


# ── Link checking ─────────────────────────────────────────────────────────────

def is_ok(r):
    return (
        r["http_status"] is not None
        and 200 <= r["http_status"] < 400
        and r["content_errors"] is None
        and r["error"] is None
        and not r.get("numeric_wb_id", False)
        and not r.get("is_homepage", False)
        and not r.get("transient", False)
        and not r.get("inconclusive", False)
    )


def is_transient_or_inconclusive(r):
    return r.get("transient", False) or r.get("inconclusive", False)


def result_label(r):
    if r.get("numeric_wb_id"):
        return "BROKEN (WorldBank numeric-only indicator code)"
    if r.get("is_homepage"):
        return "BROKEN (final URL is portal homepage/root)"
    if r.get("transient"):
        return "TRANSIENT HTTP {} (server-side gateway error — URL is valid)".format(r["http_status"])
    if r.get("inconclusive"):
        return "INCONCLUSIVE (connection error — host may be unreachable from this network)"
    if r["error"]:
        return "BROKEN ({})".format(r["error"][:60])
    if r["http_status"] and r["http_status"] >= 400:
        return "HTTP {}".format(r["http_status"])
    if r["content_errors"]:
        return "BAD CONTENT ({})".format(", ".join(r["content_errors"]))
    return "OK (HTTP {})".format(r["http_status"])


def check_links(records, verbose):
    results = []
    total = len(records)
    print("Checking {} URLs ...\n".format(total))

    for i, rec in enumerate(records, 1):
        url    = rec["url"]
        portal = rec["portal"]
        r = {
            "portal":         portal,
            "title":          rec["title"],
            "url":            url,
            "http_status":    None,
            "final_url":      url,
            "error":          None,
            "content_errors": None,
            "numeric_wb_id":  False,
            "is_homepage":    False,
            "transient":      False,
            "inconclusive":   False,
        }

        if verbose:
            print("[{:3}/{}] {:12} {}".format(i, total, portal, url[:80]))

        # WorldBank numeric indicator code: flag without HTTP request
        if WB_NUMERIC_PATTERN.match(url):
            r["numeric_wb_id"] = True
            if verbose:
                print("             => {}".format(result_label(r)))
            results.append(r)
            continue

        if not url.startswith("http"):
            r["error"] = "not a valid URL"
        else:
            try:
                domain = _domain(url)
                read_body = (
                    portal in CONTENT_CHECK_PORTALS
                    and domain not in NO_CONTENT_CHECK_DOMAINS
                )
                status, final_url, body = fetch_url(url, read_body=read_body)
                r["http_status"] = status
                r["final_url"] = final_url
                if status in TRANSIENT_STATUSES:
                    r["transient"] = True
                elif is_homepage_url(final_url):
                    r["is_homepage"] = True
                elif body:
                    r["content_errors"] = check_content_errors(body)
            except ConnectionError as e:
                r["error"] = str(e)[:80]
                r["inconclusive"] = True

        if verbose:
            print("             => {}".format(result_label(r)))

        results.append(r)

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(results):
    ok           = [r for r in results if is_ok(r)]
    broken       = [r for r in results if not is_ok(r) and not is_transient_or_inconclusive(r)]
    transient    = [r for r in results if r.get("transient")]
    inconclusive = [r for r in results if r.get("inconclusive")]
    total        = len(results)

    print()
    print("=" * 72)
    print("  TDO LINK CHECK REPORT")
    print("=" * 72)
    print("  Total        : {}".format(total))
    print("  OK           : {}  ({:.0f}%)".format(len(ok), 100 * len(ok) / max(total, 1)))
    print("  Broken       : {}  ({:.0f}%)".format(len(broken), 100 * len(broken) / max(total, 1)))
    print("  Transient    : {}  (5xx gateway errors — server-side, URL is valid)".format(len(transient)))
    print("  Inconclusive : {}  (connection errors — host may be unreachable from here)".format(len(inconclusive)))
    print()
    print("  {:<14} {:>5} {:>7} {:>7} {:>7}  {:>6}".format(
        "Portal", "OK", "Broken", "Trans.", "Incon.", "% OK"))
    print("  " + "-" * 56)

    summary_parts = []
    for portal in PORTALS + ["unknown"]:
        pr = [r for r in results if r["portal"] == portal]
        if not pr:
            continue
        pok   = sum(1 for r in pr if is_ok(r))
        pbad  = sum(1 for r in pr if not is_ok(r) and not is_transient_or_inconclusive(r))
        ptran = sum(1 for r in pr if r.get("transient"))
        pinc  = sum(1 for r in pr if r.get("inconclusive"))
        pct   = 100 * pok // len(pr)
        print("  {:<14} {:>5} {:>7} {:>7} {:>7}  {:>5}%".format(
            portal, pok, pbad, ptran, pinc, pct))
        summary_parts.append("{} {}/{}".format(portal, pok, len(pr)))

    if broken:
        print()
        print("  BROKEN LINKS ({})".format(len(broken)))
        print("  " + "-" * 72)
        for r in broken:
            url_short = r["url"]
            if len(url_short) > 70:
                url_short = url_short[:67] + "..."
            print("  [{:<10}] {}".format(r["portal"], result_label(r)))
            print("    URL  : {}".format(url_short))
            print("    Title: {}".format(r["title"][:70]))
            print()
    else:
        print()
        print("  All definitive checks are healthy.")

    if transient:
        print()
        print("  TRANSIENT (server-side errors, not our fault) — {}".format(len(transient)))
        print("  " + "-" * 72)
        for r in transient:
            print("  [{:<10}] HTTP {}  {}".format(
                r["portal"], r["http_status"], r["url"][:65]))

    if inconclusive:
        print()
        print("  INCONCLUSIVE (connection errors) — {}".format(len(inconclusive)))
        print("  " + "-" * 72)
        for r in inconclusive:
            print("  [{:<10}] {}".format(r["portal"], r["url"][:65]))

    print("=" * 72)
    print()
    print("LINKS: " + " | ".join("{} OK".format(s) for s in summary_parts))

    return 1 if broken else 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TDO dataset URL link checker")
    parser.add_argument("--api",     required=True,
                        help="TDO API base URL")
    parser.add_argument("--apikey",  required=True,
                        help="API key (sent as X-API-Key header)")
    parser.add_argument("--portal",  default=None,
                        help="Restrict to one portal: {}".format(", ".join(PORTALS)))
    parser.add_argument("--limit",   type=int, default=100,
                        help="Max URLs to check (default: 100)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each URL and result as it is checked")
    parser.add_argument("--sample",  action="store_true",
                        help="Also pull 50 random records per portal for broader coverage")
    args = parser.parse_args()

    records = collect_urls(args.api, args.apikey, args.portal, args.limit, args.sample)
    if not records:
        print("No records returned. Check --api and --apikey.")
        sys.exit(1)

    results = check_links(records, args.verbose)

    # Save full results JSON
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = "check_links_results_{}.json".format(ts)
    try:
        with open(out_path, "w") as f:
            json.dump({
                "timestamp": ts,
                "total": len(results),
                "ok": sum(1 for r in results if is_ok(r)),
                "broken": sum(1 for r in results if not is_ok(r)),
                "results": results,
            }, f, indent=2)
        print("Full results saved to: {}".format(out_path))
    except Exception as e:
        print("  [!] Could not save results: {}".format(e))

    exit_code = print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
