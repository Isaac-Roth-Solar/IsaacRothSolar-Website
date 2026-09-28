#!/usr/bin/env python3
"""Check Google Search Console index status for every URL in sitemap.xml.

Reads the sitemap, asks Search Console for the submitted sitemap's fetch status,
then runs each URL through the URL Inspection API and prints the verdict.

Usage:
    python3 tools/gsc-index-check.py --key ~/gsc-service-account.json
    GSC_SERVICE_ACCOUNT_KEY=~/gsc-service-account.json python3 tools/gsc-index-check.py

Exit codes:
    0  every sitemap URL is indexed
    1  at least one URL is not indexed
    2  configuration, auth, or API error

See tools/README.md for the one-time Google Cloud + Search Console setup.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SITEMAPS_API = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps/{feed}"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

DEFAULT_SITE = "https://isaacrothsolar.com/"

# Bound to the real exception classes by load_session(), once imports have succeeded.
AuthError = RequestError = ()


def die(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(2)


def load_session(key_path):
    """Build an authorized session from a service-account key file."""
    global AuthError, RequestError
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        from google.auth.exceptions import GoogleAuthError as AuthError
        from requests.exceptions import RequestException as RequestError
    except ImportError:
        die(
            "missing dependencies. Install them with:\n"
            "    pip install -r tools/requirements.txt"
        )
    except BaseException as exc:
        # A half-installed cryptography/cffi can fail loudly rather than as ImportError.
        die(
            "dependencies are installed but failed to load ({}: {}).\n"
            "    Try a clean virtualenv:\n"
            "        python3 -m venv .venv && .venv/bin/pip install -r "
            "tools/requirements.txt".format(type(exc).__name__, exc)
        )

    if not key_path:
        die(
            "no service-account key. Pass --key /path/to/key.json or set "
            "GSC_SERVICE_ACCOUNT_KEY."
        )
    key_path = os.path.expanduser(key_path)
    if not os.path.isfile(key_path):
        die("service-account key not found: " + key_path)

    try:
        creds = service_account.Credentials.from_service_account_file(
            key_path, scopes=[SCOPE]
        )
    except (ValueError, KeyError) as exc:
        die("could not read service-account key: " + str(exc))
    return AuthorizedSession(creds)


def read_sitemap(source):
    """Return the <loc> URLs from a sitemap, given a local path or an http(s) URL."""
    if source.startswith("http://") or source.startswith("https://"):
        try:
            with urllib.request.urlopen(source, timeout=30) as response:
                raw = response.read()
        except OSError as exc:
            die("could not fetch sitemap {}: {}".format(source, exc))
    else:
        if not os.path.isfile(source):
            die("sitemap not found: " + source)
        with open(source, "rb") as handle:
            raw = handle.read()

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        die("sitemap is not valid XML: " + str(exc))

    if root.tag.endswith("sitemapindex"):
        die(
            "{} is a sitemap index, not a sitemap. Point --sitemap at one of the "
            "child sitemaps.".format(source)
        )

    urls = [
        loc.text.strip()
        for loc in root.findall("sm:url/sm:loc", SITEMAP_NS)
        if loc.text and loc.text.strip()
    ]
    if not urls:
        die("no <loc> entries found in " + source)
    return urls


def call_api(session, method, url, payload=None, attempts=3):
    """Call the API, retrying transient failures with a widening backoff."""
    delay = 2
    for attempt in range(1, attempts + 1):
        try:
            if method == "GET":
                response = session.get(url, timeout=30)
            else:
                response = session.post(url, json=payload, timeout=30)
        except AuthError as exc:
            die(
                "could not authenticate with Google ({}).\n"
                "    Check the key file is current and belongs to a service account "
                "that still exists,\n"
                "    and that the Search Console API is enabled in its Cloud "
                "project.".format(exc)
            )
        except RequestError as exc:
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            return {"__error__": "network error: {}".format(exc)}

        if response.status_code < 400:
            return response.json()
        # 429 is the daily/per-minute quota; 5xx is Google's side. Both are worth a retry.
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
            time.sleep(delay)
            delay *= 2
            continue
        return {"__error__": describe_error(response)}
    return {"__error__": "request failed after {} attempts".format(attempts)}


def describe_error(response):
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:200].replace("\n", " ")
    hint = ""
    if response.status_code == 403:
        hint = (
            " — the service account is probably not a user on this property, or the "
            "Search Console API is not enabled in the Cloud project"
        )
    elif response.status_code == 404:
        hint = " — check --site matches the property exactly, trailing slash included"
    return "HTTP {}: {}{}".format(response.status_code, message, hint)


def check_sitemap_status(session, site, feed_url):
    url = SITEMAPS_API.format(
        site=urllib.parse.quote(site, safe=""),
        feed=urllib.parse.quote(feed_url, safe=""),
    )
    return call_api(session, "GET", url)


def inspect_url(session, site, page_url):
    payload = {"inspectionUrl": page_url, "siteUrl": site, "languageCode": "en-US"}
    result = call_api(session, "POST", INSPECT_API, payload)
    if "__error__" in result:
        return result
    return result.get("inspectionResult", {}).get("indexStatusResult", {})


def print_sitemap_status(status, feed_url):
    print("Sitemap: " + feed_url)
    if "__error__" in status:
        print("  status:    could not read — " + status["__error__"])
        print()
        return

    submitted = sum(int(c.get("submitted", 0)) for c in status.get("contents", []))
    print("  submitted:  " + status.get("lastSubmitted", "unknown"))
    print("  downloaded: " + status.get("lastDownloaded", "never — Google has not fetched it"))
    print("  URLs found: {}".format(submitted))
    print("  warnings:   {}    errors: {}".format(
        status.get("warnings", "0"), status.get("errors", "0")
    ))
    if status.get("isPending"):
        print("  note:       still pending — Google has not processed this submission yet")
    print()


def print_url_table(rows):
    width = max(len(r["url"]) for r in rows)
    print("{}  {}".format("URL".ljust(width), "STATUS"))
    print("-" * (width + 40))
    for row in rows:
        print("{}  {}".format(row["url"].ljust(width), row["status"]))
    print()

    for row in rows:
        if row["indexed"] or row["detail"] is None:
            continue
        print(row["url"])
        for label, value in row["detail"]:
            print("  {:<18} {}".format(label + ":", value))
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Check GSC index status for every URL in sitemap.xml."
    )
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument(
        "--key",
        default=os.environ.get("GSC_SERVICE_ACCOUNT_KEY"),
        help="path to the service-account JSON key (or set GSC_SERVICE_ACCOUNT_KEY)",
    )
    parser.add_argument(
        "--site",
        default=os.environ.get("GSC_SITE", DEFAULT_SITE),
        help="Search Console property, e.g. https://isaacrothsolar.com/ or "
             "sc-domain:isaacrothsolar.com (default: %(default)s)",
    )
    parser.add_argument(
        "--sitemap",
        default=os.path.join(repo_root, "sitemap.xml"),
        help="sitemap to read URLs from — a local path or an http(s) URL "
             "(default: the repo's sitemap.xml)",
    )
    parser.add_argument(
        "--sitemap-url",
        help="the sitemap URL as submitted to Search Console "
             "(default: sitemap.xml at the site root)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    site = args.site
    if site.startswith("sc-domain:"):
        origin = "https://" + site[len("sc-domain:"):].rstrip("/") + "/"
    else:
        if not site.endswith("/"):
            site += "/"
        origin = site
    feed_url = args.sitemap_url or urllib.parse.urljoin(origin, "sitemap.xml")

    urls = read_sitemap(args.sitemap)
    session = load_session(args.key)

    sitemap_status = check_sitemap_status(session, site, feed_url)

    rows = []
    for page_url in urls:
        result = inspect_url(session, site, page_url)
        if "__error__" in result:
            rows.append({
                "url": page_url,
                "indexed": False,
                "status": "ERROR — " + result["__error__"],
                "detail": None,
                "raw": result,
            })
            continue

        coverage = result.get("coverageState", "unknown")
        indexed = result.get("verdict") == "PASS"
        rows.append({
            "url": page_url,
            "indexed": indexed,
            "status": ("INDEXED     " if indexed else "NOT INDEXED ") + "— " + coverage,
            "detail": [
                ("verdict", result.get("verdict") or "unknown"),
                ("robots.txt", result.get("robotsTxtState") or "unknown"),
                ("indexing", result.get("indexingState") or "unknown"),
                ("fetch", result.get("pageFetchState") or "not fetched"),
                ("last crawl", result.get("lastCrawlTime") or "never crawled"),
                ("google canonical", result.get("googleCanonical") or "none"),
                ("your canonical", result.get("userCanonical") or "none"),
            ],
            "raw": result,
        })

    if args.json:
        print(json.dumps(
            {
                "site": site,
                "sitemap": {"url": feed_url, "status": sitemap_status},
                "urls": [
                    {"url": r["url"], "indexed": r["indexed"], "result": r["raw"]}
                    for r in rows
                ],
            },
            indent=2,
        ))
    else:
        print()
        print("Property: " + site)
        print()
        print_sitemap_status(sitemap_status, feed_url)
        print_url_table(rows)
        indexed_count = sum(1 for r in rows if r["indexed"])
        error_count = sum(1 for r in rows if r["detail"] is None)
        checked = len(rows) - error_count
        if checked:
            print("{} of {} sitemap URLs indexed.".format(indexed_count, checked))
        if error_count:
            print("{} could not be checked — see the errors above.".format(error_count))
        elif indexed_count < checked:
            print(
                "\nFor anything showing 'Discovered - currently not indexed', request "
                "indexing in the GSC URL Inspection tool. 'Crawled - currently not "
                "indexed' means Google looked and passed — that's a content problem, "
                "not a technical one."
            )

    if any(r["detail"] is None for r in rows):
        return 2
    return 0 if all(r["indexed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
