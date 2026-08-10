#!/usr/bin/env python3
"""上位銘柄の決算短信PDFを取得し、テキスト抽出して results/kessan/ に保存する。

ネットネット指数の検証用。直リンクを順に試し、全滅した場合は
決算プロ(ke.kabupro.jp)の銘柄ページから最新の「決算短信」リンクを拾う。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

OUT_DIR = Path("results/kessan")
HEADERS = {"User-Agent": "Mozilla/5.0 (kessan fetcher for personal screening)"}

# 各銘柄: 直リンク候補(新しい順に試す)。空なら決算プロから探す。
TARGETS = [
    {
        "code": "7034",
        "name": "プロレド・パートナーズ",
        "urls": ["https://pdf.irpocket.com/C7034/ccdN/YKcb/NZzQ.pdf"],
    },
    {
        "code": "6619",
        "name": "ダブル・スコープ",
        "urls": ["https://www.release.tdnet.info/inbs/140120260319585267.pdf"],
    },
    {
        "code": "1897",
        "name": "金下建設",
        "urls": [
            "https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260513/20260402597678.pdf"
        ],
    },
    {"code": "5918", "name": "瀧上工業", "urls": []},
    {
        "code": "6986",
        "name": "双葉電子工業",
        "urls": [
            "https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260512/20260511523151.pdf"
        ],
    },
    {"code": "5921", "name": "川岸工業", "urls": []},
]

ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def kabupro_latest_tanshin(code: str) -> list[str]:
    """決算プロの銘柄ページから決算短信PDFのURL候補(新しい順)を返す。"""
    url = f"http://ke.kabupro.jp/code/{code}.htm"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.encoding = r.apparent_encoding
    cands = []
    for href, text in ANCHOR_RE.findall(r.text):
        text = re.sub(r"<[^>]+>", "", text)
        if "決算短信" in text and href.lower().endswith(".pdf"):
            if href.startswith("/"):
                href = "http://ke.kabupro.jp" + href
            elif not href.startswith("http"):
                href = "http://ke.kabupro.jp/code/" + href
            cands.append(href)
    return cands


def download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            print(f"    PDFではない応答: {url}")
            return None
        return r.content
    except Exception as e:
        print(f"    取得失敗: {url} ({e})")
        return None


def extract_text(pdf_path: Path) -> str:
    import pdfplumber

    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            chunks.append(f"\n===== page {i} =====\n{text}")
    return "\n".join(chunks)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for t in TARGETS:
        code, name = t["code"], t["name"]
        print(f"[{code}] {name}")
        urls = list(t["urls"])
        try:
            urls += kabupro_latest_tanshin(code)[:3]
        except Exception as e:
            print(f"    決算プロの一覧取得失敗: {e}")

        content = None
        used = None
        for url in urls:
            content = download(url)
            if content:
                used = url
                break
        if not content:
            failures.append(code)
            continue

        pdf_path = OUT_DIR / f"{code}.pdf"
        pdf_path.write_bytes(content)
        text = f"source: {used}\n" + extract_text(pdf_path)
        (OUT_DIR / f"{code}.txt").write_text(text, encoding="utf-8")
        print(f"    OK: {used} ({len(content)//1024}KB)")

    if failures:
        print(f"取得できなかった銘柄: {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
