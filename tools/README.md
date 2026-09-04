# tools

## gsc-index-check.py

Prints the Google Search Console index status of every URL in `sitemap.xml`,
so you don't have to click through the GSC UI page by page.

```
$ python3 tools/gsc-index-check.py --key ~/gsc-service-account.json

Property: https://isaacrothsolar.com/

Sitemap: https://isaacrothsolar.com/sitemap.xml
  submitted:  2026-08-26T18:04:11.000Z
  downloaded: 2026-09-02T04:11:52.000Z
  URLs found: 3
  warnings:   0    errors: 0

URL                                       STATUS
--------------------------------------------------------------------------------
https://isaacrothsolar.com/               INDEXED     — Submitted and indexed
https://isaacrothsolar.com/services.html  INDEXED     — Submitted and indexed
https://isaacrothsolar.com/about.html     INDEXED     — Submitted and indexed

3 of 3 sitemap URLs indexed.
```

Anything not indexed gets a detail block underneath — robots.txt state, fetch
state, last crawl time, and the canonical Google picked versus the one the page
declares (a mismatch there is the usual reason a page silently drops out).

Exit codes: `0` everything indexed, `1` something isn't, `2` setup or API error.

### One-time setup

1. **Create a service account.** In the [Google Cloud console](https://console.cloud.google.com/),
   pick or create a project, then IAM & Admin → Service Accounts → Create.
   No roles are needed — the permission that matters is granted in Search
   Console, not in Cloud.
2. **Download a JSON key** for it (Keys → Add key → JSON). Keep it outside this
   repo; it is a credential.
3. **Enable the Google Search Console API** for that project: APIs & Services →
   Library → "Google Search Console API" → Enable.
4. **Grant it access to the property.** In Search Console → Settings → Users and
   permissions → Add user, paste the service account's email (it looks like
   `something@project-id.iam.gserviceaccount.com`) and give it **Full**.
   Restricted is not enough — the URL Inspection API rejects it.
5. **Install the dependencies:**
   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r tools/requirements.txt
   ```

Then run it:

```sh
.venv/bin/python tools/gsc-index-check.py --key ~/gsc-service-account.json
```

Or set `GSC_SERVICE_ACCOUNT_KEY` once and drop the flag.

### Options

| Flag | Default | Notes |
|---|---|---|
| `--key` | `$GSC_SERVICE_ACCOUNT_KEY` | Path to the service-account JSON key. |
| `--site` | `https://isaacrothsolar.com/` | The property, exactly as GSC shows it. Domain properties use `sc-domain:isaacrothsolar.com`. |
| `--sitemap` | the repo's `sitemap.xml` | Where to read URLs from. Accepts a local path or an `https://` URL — point it at the live site to check what Google actually sees. |
| `--sitemap-url` | `<site>/sitemap.xml` | The sitemap URL as submitted to GSC, if it differs. |
| `--json` | off | Machine-readable output, including the raw API results. |

### Notes

- The URL Inspection API is limited to 2,000 calls per day and 600 per minute.
  This site has three URLs, so that is not a concern.
- The sitemap's `indexed` count in Google's API is deprecated and always
  reports `0`. That's why this script inspects each URL individually instead of
  trusting that number — ignore it if you see it in `--json` output.
- Index status reflects what Google knew at its last crawl, not this instant.
  After publishing changes, expect a lag of days before it updates.
