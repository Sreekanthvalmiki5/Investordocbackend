"""Query PyPI JSON API for latest versions compatible with Python 3.10.16."""
import json
import sys
import urllib.request

from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.packaging.version import Version

TARGET = "3.10.16"


def supports(rp):
    if not rp:
        return True
    try:
        return SpecifierSet(rp).contains(TARGET, prereleases=True)
    except Exception:
        return True


def get(pkg):
    url = f"https://pypi.org/pypi/{pkg}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "req-check/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    info = data.get("info", {})
    releases = data.get("releases", {})
    latest = info.get("version", "")
    latest_rp = info.get("requires_python")

    # sort versions properly
    vers = []
    for v, files in releases.items():
        if not files:
            continue
        try:
            pv = Version(v)
        except Exception:
            continue
        vers.append((pv, v, files[0].get("requires_python")))
    vers.sort(key=lambda x: x[0])

    newest_ok = None
    newest_ok_rp = None
    for pv, v, rp in vers:
        if supports(rp):
            newest_ok = v
            newest_ok_rp = rp

    # top 8 newest versions that support 3.10
    ok_versions = [(pv, v, rp) for pv, v, rp in vers if supports(rp)]
    top = [v for pv, v, rp in ok_versions[-8:]][::-1]

    print(f"{pkg}|latest={latest}|latest_rp={latest_rp}|newest_3.10={newest_ok}|newest_3.10_rp={newest_ok_rp}|top_3.10={top}")


if __name__ == "__main__":
    for pkg in sys.argv[1:]:
        try:
            get(pkg)
        except Exception as e:
            print(f"{pkg}|ERROR|{type(e).__name__}: {e}")
