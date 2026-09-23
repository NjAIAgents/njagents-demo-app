#!/usr/bin/env python3
"""Send synthetic approval traffic to a Vercel deployment of this repo.

About one request in five is for the "northwind" account, whose commits fail. On a
2026.09 deployment those produce "approval not committed" warnings in Vercel's runtime
logs; on 2026.08 they return 500 instead. Read-only for everything except the demo app.

    python3 seed/drive_vercel.py https://njagents-demo-app.vercel.app --count 60
"""
import argparse, json, random, time, urllib.error, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("--count", type=int, default=60)
ap.add_argument("--seed", type=int, default=4830)
a = ap.parse_args()
rng = random.Random(a.seed)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # A protected deployment URL redirects to a login page, which would count as 200
    # while never reaching the app. Treat any redirect as a failure instead.
    def redirect_request(self, *args, **kwargs):
        return None


opener = urllib.request.build_opener(NoRedirect)
codes = {}
for i in range(a.count):
    acct = "northwind" if rng.random() < 0.2 else rng.choice(["contoso", "fabrikam", "tailspin"])
    url = f"{a.base.rstrip('/')}/api/approve?account={acct}&request=R-{10000 + i}"
    try:
        with opener.open(url, timeout=20) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    codes[code] = codes.get(code, 0) + 1
    time.sleep(0.2)
print(json.dumps({"sent": a.count, "status_codes": codes}))
if any(300 <= c < 400 for c in codes):
    raise SystemExit("Redirected: this URL is behind deployment protection. Use the public production domain.")
