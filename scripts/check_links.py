#!/usr/bin/env python3
"""
TDO Dataset URL Checker

Usage:
    python3 scripts/check_links.py \\
        --api https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io \\
        --apikey tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963 \\
        [--portal worldbank] [--limit 100] [--verbose]
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

SEARCH_QUERIES = [
    "GDP growth", "population", "inflation", "unemployment",
    "trade", "energy", "health", "education", "poverty", "emissions",
]
PORTALS = ["statfin", "eurostat", "oecd", "worldbank", "undata"]
TIMEOUT = 15
CONTENT_CHECK_PORTALS = {"worldbank", "oecd", "undata"}
ERROR_PHRASES = [
    "no longer available",
    "not found",
    "does not exist",
    "discontinued",
]
USER_AGENT = "TDO-LinkChecker/1.0"


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
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_get(api_base, path, apikey):
    url = api_base.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": apikey, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── URL fetching ──────────────────────────────────────────────────────────────

def fetch_url(url, read_body=False):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            body = None
            if read_body:
                body = resp.read(8192).decode("utf-8", errors="ignore").lower()
            return status, body
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        raise ConnectionError(str(e))


def check_content_errors(body):
    found = []
    for phrase in ERROR_PHRASES:
        if phrase in body:
            found.append(phrase)
    return found or None


# ── URL collection ─────────────────────────────────────────────────────────────

def collect_urls(api_base, apikey, portal_filter, limit):
    seen_urls = set()
    records = []

    print("Collecting dataset URLs via /v1/query ...")

    for query in SEARCH_QUERIES:
        if len(records) >= limit:
            break
        payload = {"question": query, "limit": 10}
        if portal_filter:
            payload["portal"] = portal_filter
        try:
            data = api_post(api_base, "/v1/query", payload, apikey)
            for r in data.get("results", []):
                url = r.get("dataset_url") or r.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                records.append({
                    "portal": r.get("portal") or r.get("source_portal", "unknown"),
                    "title":  r.get("title", "(no title)")[:80],
                    "url":    url,
                })
        except Exception as e:
            print("  [!] Query '{}' failed: {}".format(query, e))

    # Top-up: one request per portal to ensure coverage
    for portal in (PORTALS if not portal_filter else [portal_filter]):
        if len(records) >= limit:
            break
        try:
            data = api_post(
                api_base, "/v1/query",
                {"question": "statistics data", "portal": portal, "limit": 10},
                apikey,
            )
            for r in data.get("results", []):
                url = r.get("dataset_url") or r.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                records.append({
                    "portal": r.get("portal") or r.get("source_portal", portal),
                    "title":  r.get("title", "(no title)")[:80],
                    "url":    url,
                })
        except Exception:
            pass

    print("  Collected {} unique URLs\n".format(len(records)))
    return records[:limit]


# ── Link checking ─────────────────────────────────────────────────────────────

def is_ok(r):
    return (
        r["http_status"] is not None
        and 200 <= r["http_status"] < 400
        and r["content_errors"] is None
        and r["error"] is None
    )


def result_label(r):
    if r["error"]:
        return "ERROR ({})".format(r["error"][:50])
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
            "error":          None,
            "content_errors": None,
        }

        if verbose:
            print("[{:3}/{}] {:12} {}".format(i, total, portal, url[:80]))

        if not url.startswith("http"):
            r["error"] = "not a valid URL"
        else:
            try:
                read_body = portal in CONTENT_CHECK_PORTALS
                status, body = fetch_url(url, read_body=read_body)
                r["http_status"] = status
                if body:
                    r["content_errors"] = check_content_errors(body)
            except ConnectionError as e:
                r["error"] = str(e)[:80]

        if verbose:
            print("             => {}".format(result_label(r)))

        results.append(r)
        time.sleep(0.25)

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(results):
    ok     = [r for r in results if is_ok(r)]
    broken = [r for r in results if not is_ok(r)]
    total  = len(results)

    print()
    print("=" * 72)
    print("  TDO LINK CHECK REPORT")
    print("=" * 72)
    print("  Total  : {}".format(total))
    print("  OK     : {}  ({:.0f}%)".format(len(ok),     100 * len(ok)     / max(total, 1)))
    print("  Broken : {}  ({:.0f}%)".format(len(broken), 100 * len(broken) / max(total, 1)))
    print()
    print("  {:<14} {:>6} {:>8} {:>7}".format("Portal", "OK", "Broken", "Total"))
    print("  " + "-" * 40)
    for portal in PORTALS + ["unknown"]:
        pr = [r for r in results if r["portal"] == portal]
        if not pr:
            continue
        pok = sum(1 for r in pr if is_ok(r))
        print("  {:<14} {:>6} {:>8} {:>7}".format(
            portal, pok, len(pr) - pok, len(pr)))

    if broken:
        print()
        print("  BROKEN LINKS ({})".format(len(broken)))
        print("  " + "-" * 72)
        for r in broken:
            url_short = r["url"]
            if len(url_short) > 68:
                url_short = url_short[:65] + "..."
            print("  [{:<10}] {}".format(r["portal"], result_label(r)))
            print("    URL  : {}".format(url_short))
            print("    Title: {}".format(r["title"]))
            print()
    else:
        print()
        print("  All links are healthy.")

    print("=" * 72)
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
    args = parser.parse_args()

    records = collect_urls(args.api, args.apikey, args.portal, args.limit)
    if not records:
        print("No records returned. Check --api and --apikey.")
        sys.exit(1)

    results   = check_links(records, args.verbose)
    exit_code = print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
