#!/usr/bin/env python3
"""かぶ1000流ネットネット株スクリーナー(日本株全銘柄).

手順:
  1. JPX公式の上場銘柄一覧 (data_j.xls) をダウンロードして銘柄コードを取得
     (ETF・ETN・REIT・インフラファンド等は除外し、普通株のみ対象)
  2. yfinance で時価総額・貸借対照表(現金、売掛金、有価証券、投資有価証券、負債合計)を取得
  3. 正味流動資産 = 現金及び預金 + 受取手形及び売掛金 + 有価証券 + 投資有価証券 - 負債合計
     ネットネット指数 = 時価総額 / 正味流動資産
     正味流動資産 > 0 かつ ネットネット指数 < 1.0 を抽出 (指数 < 0.67 はグレアム基準フラグ)
  4. 結果を CSV 出力し、上位30銘柄をコンソール表示

使い方:
  python net_net_screener.py                 # 全銘柄スクリーニング(キャッシュ利用)
  python net_net_screener.py --limit 100     # 先頭100銘柄のみ(動作確認用)
  python net_net_screener.py --codes 7203 8306  # 指定銘柄のみ
  python net_net_screener.py --refresh       # キャッシュを無視して再取得
  python net_net_screener.py --strict        # 有価証券・投資有価証券も欠損ならスキップ

注意:
  yfinance の財務データは連結/単体の別や項目名の揺れで不正確な場合があります。
  抽出された上位銘柄は必ず決算短信(貸借対照表)の原本で確認してください。
"""

from __future__ import annotations

import argparse
import io
import logging
import math
import pickle
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

JPX_LIST_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JPX_BASE = "https://www.jpx.co.jp"
# ページ解析に失敗した場合のフォールバック(過去に使われていた直リンク)
JPX_FALLBACK_XLS = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
)

CACHE_DIR = Path("cache")
JPX_XLS_PATH = CACHE_DIR / "data_j.xls"
FUND_CACHE_PATH = CACHE_DIR / "fundamentals.pkl"

RESULT_CSV = "net_net_results.csv"
ALL_DATA_CSV = "all_data.csv"
SKIPPED_CSV = "skipped.csv"

SLEEP_BASE = 0.6          # 銘柄間の基本スリープ秒(+ジッター)
MAX_RETRIES = 3
RETRY_BACKOFF = 5.0       # リトライ時の待機秒(指数的に増加)
PROGRESS_EVERY = 100
CACHE_SAVE_EVERY = 100

GRAHAM_THRESHOLD = 0.67
NET_NET_THRESHOLD = 1.0

# 市場・商品区分のうち普通株として扱わない区分(部分一致)
EXCLUDE_SEGMENT_KEYWORDS = [
    "ETF",
    "ETN",
    "REIT",
    "リート",
    "インフラファンド",
    "カントリーファンド",
    "ベンチャーファンド",
    "出資証券",
]

# ---------------------------------------------------------------------------
# 貸借対照表の項目名候補 (yfinance は銘柄によって項目名が揺れる)
# 先頭からの first-hit で採用する
# ---------------------------------------------------------------------------

CASH_KEYS = [
    "Cash And Cash Equivalents",
    "Cash Financial",
    "Cash Equivalents",
]
RECEIVABLE_KEYS = [
    "Accounts Receivable",
    "Gross Accounts Receivable",
    "Receivables",
]
SHORT_TERM_SEC_KEYS = [
    "Other Short Term Investments",
    "Trading Securities",
]
LONG_TERM_SEC_KEYS = [
    "Investments And Advances",
    "Investmentin Financial Assets",
    "Available For Sale Securities",
    "Long Term Equity Investment",
]
TOTAL_LIAB_KEYS = [
    "Total Liabilities Net Minority Interest",
    "Total Liab",
]
OPERATING_INCOME_KEYS = [
    "Operating Income",
    "Total Operating Income As Reported",
]

log = logging.getLogger("netnet")


# ---------------------------------------------------------------------------
# 1. JPX 銘柄リスト
# ---------------------------------------------------------------------------

def download_jpx_list(force: bool = False) -> Path:
    """JPXの上場銘柄一覧Excel(data_j.xls)をダウンロードして保存する。"""
    CACHE_DIR.mkdir(exist_ok=True)
    if JPX_XLS_PATH.exists() and not force:
        log.info("銘柄リストはキャッシュを使用: %s", JPX_XLS_PATH)
        return JPX_XLS_PATH

    headers = {"User-Agent": "Mozilla/5.0 (net-net screener)"}
    url = None
    try:
        page = requests.get(JPX_LIST_PAGE, headers=headers, timeout=30)
        page.raise_for_status()
        m = re.search(r'href="([^"]+data_j\.xls)"', page.text)
        if m:
            url = m.group(1)
            if url.startswith("/"):
                url = JPX_BASE + url
    except Exception as e:  # ページ解析失敗はフォールバックへ
        log.warning("JPX一覧ページの取得に失敗 (%s)。フォールバックURLを使用します", e)

    for candidate in filter(None, [url, JPX_FALLBACK_XLS]):
        try:
            log.info("data_j.xls をダウンロード中: %s", candidate)
            r = requests.get(candidate, headers=headers, timeout=60)
            r.raise_for_status()
            JPX_XLS_PATH.write_bytes(r.content)
            return JPX_XLS_PATH
        except Exception as e:
            log.warning("ダウンロード失敗: %s (%s)", candidate, e)

    raise RuntimeError("data_j.xls のダウンロードに失敗しました")


def load_stock_list(xls_path: Path) -> pd.DataFrame:
    """data_j.xls を読み、普通株のみの DataFrame(code, name, segment, sector33)を返す。"""
    df = pd.read_excel(xls_path, dtype=str)
    # 列名の揺れに備えて部分一致で特定する
    cols = {c: str(c) for c in df.columns}

    def find_col(*keywords):
        for c, name in cols.items():
            if all(k in name for k in keywords):
                return c
        raise KeyError(f"列が見つかりません: {keywords} (実際の列: {list(df.columns)})")

    code_col = find_col("コード")
    name_col = find_col("銘柄名")
    seg_col = find_col("市場")
    sector_col = None
    for c, name in cols.items():
        if "33業種区分" in name:
            sector_col = c
            break

    out = pd.DataFrame(
        {
            "code": df[code_col].astype(str).str.strip(),
            "name": df[name_col].astype(str).str.strip(),
            "segment": df[seg_col].astype(str).str.strip(),
            "sector33": df[sector_col].astype(str).str.strip() if sector_col else "",
        }
    )

    total = len(out)
    mask = ~out["segment"].apply(
        lambda s: any(k in s for k in EXCLUDE_SEGMENT_KEYWORDS)
    )
    out = out[mask].reset_index(drop=True)
    log.info(
        "銘柄リスト: 全%d件 → 普通株 %d件 (ETF/REIT等 %d件を除外)",
        total, len(out), total - len(out),
    )
    return out


# ---------------------------------------------------------------------------
# 2. yfinance によるデータ取得
# ---------------------------------------------------------------------------

def _first_hit(series_index, frame: pd.DataFrame, keys: list[str]):
    """balance_sheet 等の DataFrame から候補キーの first-hit で最新期の値を返す。

    戻り値: (値 or None, 使用したキー or None)
    NaN は欠損として扱う。
    """
    if frame is None or frame.empty:
        return None, None
    for key in keys:
        if key in frame.index:
            row = frame.loc[key]
            # 最新期(先頭列)から順に有効値を探す
            for v in row.values:
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v), key
    return None, None


def fetch_one(code: str) -> dict:
    """1銘柄分の生データを取得する。失敗時は error キーを持つ dict を返す。"""
    import yfinance as yf

    ticker = f"{code}.T"
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t = yf.Ticker(ticker)
            bs = t.balance_sheet
            info = t.info or {}

            market_cap = info.get("marketCap")
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price is None:
                try:
                    price = t.fast_info.last_price
                except Exception:
                    price = None
            pbr = info.get("priceToBook")

            cash, cash_key = _first_hit(None, bs, CASH_KEYS)
            recv, recv_key = _first_hit(None, bs, RECEIVABLE_KEYS)
            st_sec, st_key = _first_hit(None, bs, SHORT_TERM_SEC_KEYS)
            lt_sec, lt_key = _first_hit(None, bs, LONG_TERM_SEC_KEYS)
            liab, liab_key = _first_hit(None, bs, TOTAL_LIAB_KEYS)

            op_income = None
            try:
                inc = t.income_stmt
                op_income, _ = _first_hit(None, inc, OPERATING_INCOME_KEYS)
            except Exception:
                pass

            return {
                "code": code,
                "market_cap": market_cap,
                "price": price,
                "pbr": pbr,
                "cash": cash,
                "receivables": recv,
                "short_term_securities": st_sec,
                "long_term_securities": lt_sec,
                "total_liabilities": liab,
                "operating_income": op_income,
                "keys_used": {
                    "cash": cash_key,
                    "receivables": recv_key,
                    "short_term_securities": st_key,
                    "long_term_securities": lt_key,
                    "total_liabilities": liab_key,
                },
                "error": None,
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * (2 ** (attempt - 1))
                log.debug("%s: 取得失敗(%s)。%.0f秒後にリトライ (%d/%d)",
                          ticker, e, wait, attempt, MAX_RETRIES)
                time.sleep(wait)

    return {
        "code": code,
        "error": f"{type(last_err).__name__}: {last_err}",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def load_cache() -> dict:
    if FUND_CACHE_PATH.exists():
        with open(FUND_CACHE_PATH, "rb") as f:
            cache = pickle.load(f)
        log.info("キャッシュ読み込み: %d銘柄分 (%s)", len(cache), FUND_CACHE_PATH)
        return cache
    return {}


def save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = FUND_CACHE_PATH.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(cache, f)
    tmp.replace(FUND_CACHE_PATH)


def fetch_all(stocks: pd.DataFrame, refresh: bool = False,
              sleep_base: float = SLEEP_BASE) -> dict:
    """全銘柄のデータを取得(キャッシュ利用)して dict[code] = raw を返す。"""
    cache = {} if refresh else load_cache()
    codes = list(stocks["code"])
    todo = [c for c in codes if c not in cache]
    log.info("取得対象: %d銘柄 (キャッシュ済み %d銘柄はスキップ)",
             len(todo), len(codes) - len(todo))

    for i, code in enumerate(todo, 1):
        cache[code] = fetch_one(code)
        if i % PROGRESS_EVERY == 0:
            ok = sum(1 for c in todo[:i] if cache[c].get("error") is None)
            log.info("進捗: %d/%d 銘柄 取得済み (成功 %d / 失敗 %d)",
                     i, len(todo), ok, i - ok)
        if i % CACHE_SAVE_EVERY == 0:
            save_cache(cache)
        time.sleep(sleep_base + random.uniform(0, sleep_base * 0.5))

    save_cache(cache)
    return cache


# ---------------------------------------------------------------------------
# 3. 判定ロジック (かぶ1000流)
# ---------------------------------------------------------------------------

def evaluate(stocks: pd.DataFrame, cache: dict, strict: bool = False):
    """取得データからネットネット指数を計算する。

    戻り値: (全計算結果の DataFrame, スキップ一覧の DataFrame)

    正味流動資産 = 現金及び預金 + 受取手形及び売掛金 + 有価証券 + 投資有価証券
                   - 負債合計
    ネットネット指数 = 時価総額 / 正味流動資産

    注意: Yahoo Finance は値がゼロの項目を行ごと省略するため、
    有価証券・投資有価証券の欠損は「保有なし(0)」とみなす(--strict で厳格化)。
    現金・売掛金・負債合計・時価総額の欠損はスキップ。
    """
    rows, skipped = [], []
    for _, s in stocks.iterrows():
        code, name = s["code"], s["name"]
        raw = cache.get(code)
        if raw is None:
            skipped.append({"code": code, "name": name, "reason": "未取得"})
            continue
        if raw.get("error"):
            skipped.append({"code": code, "name": name,
                            "reason": f"取得エラー: {raw['error']}"})
            continue

        missing = [label for label, key in [
            ("時価総額", "market_cap"),
            ("現金及び現金同等物", "cash"),
            ("売掛金・受取手形", "receivables"),
            ("負債合計", "total_liabilities"),
        ] if raw.get(key) is None]
        if strict:
            missing += [label for label, key in [
                ("有価証券", "short_term_securities"),
                ("投資有価証券", "long_term_securities"),
            ] if raw.get(key) is None]
        if missing:
            skipped.append({"code": code, "name": name,
                            "reason": "項目欠損: " + "・".join(missing)})
            continue

        st_sec = raw.get("short_term_securities") or 0.0
        lt_sec = raw.get("long_term_securities") or 0.0
        nca = (raw["cash"] + raw["receivables"] + st_sec + lt_sec
               - raw["total_liabilities"])
        market_cap = raw["market_cap"]
        ratio = market_cap / nca if nca > 0 else None

        rows.append({
            "銘柄コード": code,
            "銘柄名": name,
            "業種": s.get("sector33", ""),
            "株価": raw.get("price"),
            "時価総額": market_cap,
            "現金及び現金同等物": raw["cash"],
            "売掛金・受取手形": raw["receivables"],
            "有価証券": st_sec,
            "投資有価証券": lt_sec,
            "負債合計": raw["total_liabilities"],
            "正味流動資産": nca,
            "ネットネット指数": ratio,
            "グレアム基準該当": (ratio is not None and ratio < GRAHAM_THRESHOLD),
            "PBR": raw.get("pbr"),
            "直近営業利益": raw.get("operating_income"),
        })

    return pd.DataFrame(rows), pd.DataFrame(skipped)


def screen(all_df: pd.DataFrame) -> pd.DataFrame:
    """正味流動資産 > 0 かつ ネットネット指数 < 1.0 を抽出して昇順ソート。"""
    if all_df.empty:
        return all_df
    hit = all_df[
        (all_df["正味流動資産"] > 0)
        & all_df["ネットネット指数"].notna()
        & (all_df["ネットネット指数"] < NET_NET_THRESHOLD)
    ].copy()
    return hit.sort_values("ネットネット指数").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5-6. 出力とサマリー
# ---------------------------------------------------------------------------

OUTPUT_COLS = [
    "銘柄コード", "銘柄名", "株価", "時価総額", "正味流動資産",
    "ネットネット指数", "グレアム基準該当", "PBR", "直近営業利益",
]


def report(hits: pd.DataFrame, all_df: pd.DataFrame,
           skipped: pd.DataFrame) -> None:
    hits_out = hits[OUTPUT_COLS + ["業種"]] if not hits.empty else hits
    hits_out.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
    all_df.to_csv(ALL_DATA_CSV, index=False, encoding="utf-8-sig")
    skipped.to_csv(SKIPPED_CSV, index=False, encoding="utf-8-sig")
    log.info("CSV出力: %s (%d件) / %s (%d件) / %s (%d件)",
             RESULT_CSV, len(hits), ALL_DATA_CSV, len(all_df),
             SKIPPED_CSV, len(skipped))

    print("\n===== ネットネット株 上位30銘柄 (ネットネット指数 昇順) =====")
    if hits.empty:
        print("該当銘柄なし")
    else:
        top = hits.head(30).copy()
        top["時価総額(億円)"] = (top["時価総額"] / 1e8).round(1)
        top["正味流動資産(億円)"] = (top["正味流動資産"] / 1e8).round(1)
        top["営業利益(億円)"] = (top["直近営業利益"] / 1e8).round(1)
        top["ネットネット指数"] = top["ネットネット指数"].round(3)
        top["PBR"] = top["PBR"].round(2)
        view = top[["銘柄コード", "銘柄名", "業種", "株価", "時価総額(億円)",
                    "正味流動資産(億円)", "ネットネット指数", "グレアム基準該当",
                    "PBR", "営業利益(億円)"]]
        try:
            from tabulate import tabulate
            print(tabulate(view, headers="keys", tablefmt="simple",
                           showindex=False))
        except ImportError:
            print(view.to_string(index=False))

    # ----- 傾向サマリー -----
    print("\n===== 結果の傾向 =====")
    n_all = len(all_df)
    n_hit = len(hits)
    print(f"計算対象: {n_all}銘柄 / 抽出(指数<1.0): {n_hit}銘柄 / "
          f"グレアム基準(指数<0.67): "
          f"{int(hits['グレアム基準該当'].sum()) if n_hit else 0}銘柄 / "
          f"スキップ: {len(skipped)}銘柄")

    if n_hit:
        print("\n[業種の偏り] (抽出銘柄の業種内訳 上位10)")
        print(hits["業種"].value_counts().head(10).to_string())

        print("\n[ネットネット指数の分布]")
        bins = [0, 0.5, 0.67, 0.8, 0.9, 1.0]
        labels = ["〜0.5", "0.5〜0.67", "0.67〜0.8", "0.8〜0.9", "0.9〜1.0"]
        dist = pd.cut(hits["ネットネット指数"], bins=bins, labels=labels)
        print(dist.value_counts().reindex(labels).to_string())

    if not skipped.empty:
        print("\n[スキップ理由 上位]")
        reason_head = skipped["reason"].str.split(":").str[0]
        print(reason_head.value_counts().head(5).to_string())

    print(
        "\n※ 注意: yfinance の財務データは連結/単体の別・項目名の揺れ・更新遅延に"
        "より不正確な場合があります。\n"
        "  上位銘柄は必ず最新の決算短信(貸借対照表)で数値を確認してください。"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="かぶ1000流ネットネット株スクリーナー")
    ap.add_argument("--limit", type=int, default=None,
                    help="先頭N銘柄のみ処理(動作確認用)")
    ap.add_argument("--codes", nargs="*", default=None,
                    help="指定した銘柄コードのみ処理")
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して再取得")
    ap.add_argument("--refresh-list", action="store_true",
                    help="JPX銘柄リストを再ダウンロード")
    ap.add_argument("--strict", action="store_true",
                    help="有価証券・投資有価証券の欠損もスキップ扱いにする")
    ap.add_argument("--sleep", type=float, default=SLEEP_BASE,
                    help=f"銘柄間の基本スリープ秒 (default: {SLEEP_BASE})")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    xls = download_jpx_list(force=args.refresh_list)
    stocks = load_stock_list(xls)

    if args.codes:
        stocks = stocks[stocks["code"].isin(args.codes)].reset_index(drop=True)
        log.info("指定銘柄のみ: %d件", len(stocks))
    if args.limit:
        stocks = stocks.head(args.limit)
        log.info("先頭%d銘柄に限定", args.limit)

    cache = fetch_all(stocks, refresh=args.refresh, sleep_base=args.sleep)
    all_df, skipped = evaluate(stocks, cache, strict=args.strict)
    hits = screen(all_df)
    report(hits, all_df, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
