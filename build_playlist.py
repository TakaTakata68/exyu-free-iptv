#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EX-YU Free IPTV playlist builder

Downloads and merges public Free-TV/IPTV country playlists for:
North Macedonia, Serbia, Croatia, Bosnia and Herzegovina, Montenegro, Slovenia.
No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "1.0.0"
BASE_URL = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/"

COUNTRIES = [
    ("Severna Makedonija", "playlist_north_macedonia.m3u8"),
    ("Srbija", "playlist_serbia.m3u8"),
    ("Hrvatska", "playlist_croatia.m3u8"),
    ("Bosna i Hercegovina", "playlist_bosnia_and_herzegovina.m3u8"),
    ("Crna Gora", "playlist_montenegro.m3u8"),
    ("Slovenija", "playlist_slovenia.m3u8"),
]

USER_AGENT = f"EXYU-Free-IPTV-Builder/{VERSION}"


def download_text(url: str, timeout: int = 30, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            return raw.decode("utf-8-sig", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Preuzimanje nije uspelo: {url}\nRazlog: {last_error}")


def parse_playlist(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    epg_urls: list[str] = []
    entries: list[tuple[str, str]] = []
    pending_extinf: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            match = re.search(r'x-tvg-url="([^"]+)"', line, flags=re.IGNORECASE)
            if match:
                for item in match.group(1).split(","):
                    item = item.strip()
                    if item and item not in epg_urls:
                        epg_urls.append(item)
        elif line.startswith("#EXTINF:"):
            pending_extinf = line
        elif line.startswith("#"):
            continue
        elif pending_extinf:
            entries.append((pending_extinf, line))
            pending_extinf = None

    return epg_urls, entries


def set_group_title(extinf: str, country: str) -> str:
    escaped = country.replace('"', "'")
    if re.search(r'\bgroup-title="[^"]*"', extinf, flags=re.IGNORECASE):
        return re.sub(
            r'\bgroup-title="[^"]*"',
            f'group-title="{escaped}"',
            extinf,
            count=1,
            flags=re.IGNORECASE,
        )
    comma = extinf.find(",")
    if comma >= 0:
        return extinf[:comma] + f' group-title="{escaped}"' + extinf[comma:]
    return extinf + f' group-title="{escaped}"'


def channel_name(extinf: str) -> str:
    return extinf.split(",", 1)[1].strip() if "," in extinf else extinf


def build_playlist(output_path: Path, timeout: int, retries: int) -> tuple[int, list[str]]:
    all_epg: list[str] = []
    all_entries: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    warnings: list[str] = []

    for country, filename in COUNTRIES:
        url = BASE_URL + filename
        print(f"Preuzimam: {country}")
        try:
            text = download_text(url, timeout=timeout, retries=retries)
            epg_urls, entries = parse_playlist(text)
        except RuntimeError as exc:
            warnings.append(str(exc))
            print(f"  UPOZORENJE: lista nije preuzeta.")
            continue

        for epg_url in epg_urls:
            if epg_url not in all_epg:
                all_epg.append(epg_url)

        added = 0
        for extinf, stream_url in entries:
            normalized_url = stream_url.strip()
            if not normalized_url or normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            all_entries.append((set_group_title(extinf, country), normalized_url))
            added += 1
        print(f"  Dodato kanala: {added}")

    all_entries.sort(key=lambda item: (
        next((i for i, (c, _) in enumerate(COUNTRIES) if f'group-title="{c}"' in item[0]), 999),
        channel_name(item[0]).casefold(),
    ))

    header = "#EXTM3U"
    if all_epg:
        header += ' x-tvg-url="' + ",".join(all_epg) + '"'

    lines = [header]
    for extinf, stream_url in all_entries:
        lines.extend((extinf, stream_url))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(all_entries), warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Spaja javne EX-YU Free-TV IPTV liste u jednu M3U8 listu."
    )
    parser.add_argument(
        "-o", "--output",
        default="EXYU_Free_TV.m3u8",
        help="Naziv izlazne M3U8 datoteke (podrazumevano: EXYU_Free_TV.m3u8)",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Mrežni timeout u sekundama")
    parser.add_argument("--retries", type=int, default=3, help="Broj pokušaja preuzimanja")
    args = parser.parse_args()

    output_path = Path(args.output).expanduser().resolve()
    print(f"EX-YU Free IPTV Builder v{VERSION}")
    print(f"Izlaz: {output_path}\n")

    try:
        count, warnings = build_playlist(output_path, max(5, args.timeout), max(1, args.retries))
    except OSError as exc:
        print(f"GRESKA pri upisu datoteke: {exc}", file=sys.stderr)
        return 1

    if count == 0:
        print("GRESKA: nijedan kanal nije dodat. Proveri internet vezu.", file=sys.stderr)
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return 2

    print(f"\nGotovo. Napravljena je lista sa {count} jedinstvenih streamova:")
    print(output_path)
    if warnings:
        print(f"\nZavršeno uz {len(warnings)} upozorenja. Ostale dostupne zemlje su ipak sačuvane.")
    print("\nDatoteku možeš kopirati na USB ili poslati na Android TV i otvoriti u IPTV plejeru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
