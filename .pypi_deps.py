"""Fetch requires_dist for a specific version, or list all 3.10-compatible versions."""
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


def get_version(pkg, ver):
    url = f"https://pypi.org/pypi/{pkg}/{ver}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "req-check/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    info = data.get("info", {})
    rd = info.get("requires_dist") or []
    print(f"=== {pkg}=={ver} requires_python={info.get('requires_python')}")
    for d in rd:
        print(f"    {d}")
    print()


def list_all(pkg):
    url = f"https://pypi.org/pypi/{pkg}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "req-check/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    releases = data.get("releases", {})
    vers = []
    for v, files in releases.items():
        if not files:
            continue
        try:
            pv = Version(v)
        except Exception:
            continue
        rp = files[0].get("requires_python")
        if supports(rp) and not pv.is_prerelease:
            vers.append((pv, v))
    vers.sort(key=lambda x: x[0])
    print(f"=== {pkg} (all stable versions compatible with 3.10):")
    print("    " + ", ".join(v for _, v in vers))
    print()


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if "==" in arg:
            pkg, ver = arg.split("==", 1)
            get_version(pkg, ver)
        else:
            list_all(arg)
