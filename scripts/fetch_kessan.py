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

# 各銘柄: 直リンク候補(新しい順に試す)。scrape はIRページからPDFリンクを探す。
TARGETS = [
    {
        "code": "7034",
        "name": "プロレド・パートナーズ",
        "urls": ["https://pdf.irpocket.com/C7034/ccdN/YKcb/NZzQ.pdf"],
    },
    {
        "code": "6619",
        "name": "ダブル・スコープ",
        # TDnet ID から JPX開示ミラーと Yahoo ストレージのURLを構成
        # 140120260611567862 = 2027年1月期Q1短信(2026-06-11) / 140120260319585267 = 2026年1月期本決算
        "urls": [
            "https://www2.jpx.co.jp/disc/66190/140120260611567862.pdf",
            "https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260611/20260611567862.pdf",
            "https://www2.jpx.co.jp/disc/66190/140120260319585267.pdf",
            "https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260319/20260319585267.pdf",
        ],
        "scrape": ["https://w-scope.co.jp/ir/library/earning.html"],
    },
    {
        "code": "1897",
        "name": "金下建設",
        # 12月決算に移行済み。IRライブラリと短信一覧(記事ページ経由の二段階)から探す
        "urls": [],
        "scrape": [
            "https://www.kaneshita.co.jp/ir/library/",
            "https://www.kaneshita.co.jp/news-cat/financial_results/",
        ],
    },
    {
        "code": "5918",
        "name": "瀧上工業",
        "urls": [],
        "scrape": ["https://www.takigami.co.jp/ir_information/ir_information.html"],
    },
    {
        "code": "6986",
        "name": "双葉電子工業",
        "urls": [
            "https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260512/20260511523151.pdf"
        ],
    },
    {
        "code": "5921",
        "name": "川岸工業",
        "urls": [],
        "scrape": ["https://kawagishi.co.jp/ir/library/"],
    },
]

ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def scrape_pdf_links(page_url: str, depth: int = 1) -> list[str]:
    """IRページからPDFリンク候補を返す。短信らしいリンクを優先し、全候補をログに出す。

    PDF直リンクが見つからない場合は「決算短信」を含むリンク先(記事ページ等)を
    depth 段階まで辿って探す。
    """
    from urllib.parse import urljoin

    r = requests.get(page_url, headers=HEADERS, timeout=30)
    r.encoding = r.apparent_encoding
    preferred, others, subpages = [], [], []
    for href, text in ANCHOR_RE.findall(r.text):
        text = re.sub(r"<[^>]+>", " ", text)
        full = urljoin(page_url, href)
        hay = href.lower() + " " + text
        if ".pdf" in href.lower():
            if any(k in hay for k in ["短信", "tanshin", "kessan", "results", "1401"]):
                preferred.append(full)
            else:
                others.append(full)
        elif "決算短信" in text and full != page_url:
            subpages.append(full)

    if subpages:
        print(f"    {page_url} の短信記事リンク候補 (先頭5件):")
        for u in subpages[:5]:
            print(f"      - {u}")

    cands = preferred + others
    if not preferred and subpages and depth > 0:
        for sub in subpages[:3]:
            try:
                cands = scrape_pdf_links(sub, depth=depth - 1) + cands
            except Exception as e:
                print(f"    下位ページ取得失敗: {sub} ({e})")

    print(f"    {page_url} のPDFリンク候補 (先頭10件):")
    for u in cands[:10]:
        print(f"      - {u}")
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
        if (OUT_DIR / f"{code}.txt").exists():
            print("    取得済みのためスキップ")
            continue
        urls = list(t["urls"])
        for page in t.get("scrape", []):
            try:
                urls += scrape_pdf_links(page)[:5]
            except Exception as e:
                print(f"    スクレイプ失敗: {page} ({e})")

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
