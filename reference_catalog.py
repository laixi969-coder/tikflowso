"""Load the editorial video references bundled with the workspace."""
from datetime import date
import json
from pathlib import Path
import re

CATALOG = Path(__file__).parent / "web" / "filming-references.json"
PLATFORMS = {
    "Bilibili": r"https://www\.bilibili\.com/video/(?:BV[A-Za-z0-9]{10}|av[0-9]+)/?",
    "抖音": r"https://www\.douyin\.com/video/[0-9]+",
    "YouTube": r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}",
}


def references():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    reviewed = date.fromisoformat(catalog["reviewed"])
    grouped = {}
    for row in sorted(catalog["videos"], key=lambda v: v["added"], reverse=True):
        platform = next((name for name, pattern in PLATFORMS.items() if re.fullmatch(pattern, row["url"])), None)
        if not platform or not date.fromisoformat(row["published"]) <= date.fromisoformat(row["added"]) <= reviewed:
            raise ValueError("原片链接或日期无效")
        grouped.setdefault(row["topic"], []).append({**row, "platform": platform})
    return reviewed.isoformat(), grouped
