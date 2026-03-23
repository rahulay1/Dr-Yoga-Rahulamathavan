#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def http_get_json(url: str, *, accept: str = "application/json") -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "Dr-Yoga-Rahulamathavan-site/1.0 (GitHub Actions)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def best_work_url(work: dict[str, Any]) -> str | None:
    external_ids = (
        work.get("external-ids", {}).get("external-id", [])
        if isinstance(work.get("external-ids"), dict)
        else []
    )
    doi = None
    for eid in external_ids:
        if not isinstance(eid, dict):
            continue
        if (eid.get("external-id-type") or "").lower() == "doi":
            doi = eid.get("external-id-value")
            if doi:
                break
    if doi:
        doi = doi.strip()
        if doi.startswith("http"):
            return doi
        return f"https://doi.org/{doi}"

    url = work.get("url", {}).get("value") if isinstance(work.get("url"), dict) else None
    return url.strip() if isinstance(url, str) and url.strip() else None


def best_year(work: dict[str, Any]) -> int | None:
    pub_date = work.get("publication-date") or {}
    year = pub_date.get("year", {}).get("value") if isinstance(pub_date, dict) else None
    try:
        return int(year)
    except Exception:
        return None


def best_title(work: dict[str, Any]) -> str | None:
    title = work.get("title") or {}
    t = title.get("title", {}).get("value") if isinstance(title, dict) else None
    if isinstance(t, str) and t.strip():
        return t.strip()
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fetch_orcid_publications.py <ORCID> [out_json_path] [max_items]", file=sys.stderr)
        return 2

    orcid = sys.argv[1].strip()
    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("data/publications.json")
    max_items = int(sys.argv[3]) if len(sys.argv) >= 4 else 20

    works_index_url = f"https://pub.orcid.org/v3.0/{orcid}/works"

    try:
        index = http_get_json(works_index_url)
    except urllib.error.HTTPError as e:
        print(f"ORCID API error fetching works index: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error fetching works index: {e}", file=sys.stderr)
        return 1

    groups = index.get("group") if isinstance(index, dict) else None
    if not isinstance(groups, list):
        print("Unexpected ORCID response shape (missing group list).", file=sys.stderr)
        return 1

    put_codes: list[str] = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        summaries = g.get("work-summary")
        if not isinstance(summaries, list):
            continue
        for s in summaries:
            if not isinstance(s, dict):
                continue
            put_code = s.get("put-code")
            if put_code is not None:
                put_codes.append(str(put_code))

    # De-duplicate and keep it bounded
    seen: set[str] = set()
    unique_put_codes: list[str] = []
    for pc in put_codes:
        if pc in seen:
            continue
        seen.add(pc)
        unique_put_codes.append(pc)
        if len(unique_put_codes) >= 100:
            break

    works: list[dict[str, Any]] = []
    for pc in unique_put_codes:
        url = f"https://pub.orcid.org/v3.0/{orcid}/work/{pc}"
        try:
            work = http_get_json(url)
        except Exception:
            continue
        if isinstance(work, dict):
            works.append(work)

    items: list[dict[str, Any]] = []
    for w in works:
        title = best_title(w)
        if not title:
            continue
        items.append(
            {
                "title": title,
                "year": best_year(w),
                "url": best_work_url(w),
                "type": (w.get("type") or "").lower() if isinstance(w.get("type"), str) else None,
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        year = item.get("year")
        try:
            y = int(year) if year is not None else 0
        except Exception:
            y = 0
        return (y, item.get("title") or "")

    items.sort(key=sort_key, reverse=True)
    items = items[: max(1, max_items)]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} items to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

