"""ネットワーク不要のロジックテスト。

実行: python tests/test_screener.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import net_net_screener as sc  # noqa: E402


def make_stock_list_xlsx(path: Path) -> None:
    df = pd.DataFrame(
        {
            "日付": ["20260810"] * 6,
            "コード": ["1001", "1002", "1003", "1004", "1005", "1306"],
            "銘柄名": ["割安工業", "適正商事", "現金富豪", "欠損データ", "債務超過", "TOPIX ETF"],
            "市場・商品区分": [
                "スタンダード（内国株式）",
                "プライム（内国株式）",
                "スタンダード（内国株式）",
                "グロース（内国株式）",
                "スタンダード（内国株式）",
                "ETF・ETN",
            ],
            "33業種コード": ["3650"] * 6,
            "33業種区分": ["機械", "卸売業", "小売業", "情報・通信業", "機械", "-"],
        }
    )
    df.to_excel(path, index=False)


def make_cache() -> dict:
    return {
        # ネットネット指数 = 100 / (200+50+30+120-200=200) = 0.5 → グレアム基準該当
        "1001": {
            "code": "1001", "market_cap": 100e8, "price": 500.0, "pbr": 0.4,
            "cash": 200e8, "receivables": 50e8,
            "short_term_securities": 30e8, "long_term_securities": 120e8,
            "total_liabilities": 200e8, "operating_income": 10e8, "error": None,
        },
        # 指数 = 300 / (100+50+0+50-100=100) = 3.0 → 非該当
        "1002": {
            "code": "1002", "market_cap": 300e8, "price": 1500.0, "pbr": 1.2,
            "cash": 100e8, "receivables": 50e8,
            "short_term_securities": None, "long_term_securities": 50e8,
            "total_liabilities": 100e8, "operating_income": 30e8, "error": None,
        },
        # 指数 = 90 / (80+40+0+0-20=100) = 0.9 → 該当(グレアム基準は非該当)
        "1003": {
            "code": "1003", "market_cap": 90e8, "price": 900.0, "pbr": 0.8,
            "cash": 80e8, "receivables": 40e8,
            "short_term_securities": None, "long_term_securities": None,
            "total_liabilities": 20e8, "operating_income": 5e8, "error": None,
        },
        # 現金欠損 → スキップ
        "1004": {
            "code": "1004", "market_cap": 50e8, "price": 100.0, "pbr": None,
            "cash": None, "receivables": 10e8,
            "short_term_securities": None, "long_term_securities": None,
            "total_liabilities": 30e8, "operating_income": None, "error": None,
        },
        # 正味流動資産 < 0 → 抽出されない
        "1005": {
            "code": "1005", "market_cap": 10e8, "price": 50.0, "pbr": 0.3,
            "cash": 10e8, "receivables": 5e8,
            "short_term_securities": None, "long_term_securities": None,
            "total_liabilities": 100e8, "operating_income": -2e8, "error": None,
        },
    }


def main() -> None:
    tmp = Path("cache")
    tmp.mkdir(exist_ok=True)
    xlsx = tmp / "test_data_j.xlsx"
    make_stock_list_xlsx(xlsx)

    # --- 銘柄リスト読み込み: ETFが除外されること ---
    stocks = sc.load_stock_list(xlsx)
    assert len(stocks) == 5, f"普通株5件のはずが {len(stocks)}"
    assert "1306" not in set(stocks["code"]), "ETFが除外されていない"

    # --- 判定ロジック ---
    all_df, skipped = sc.evaluate(stocks, make_cache())
    assert len(all_df) == 4, f"計算対象4件のはずが {len(all_df)}"
    assert len(skipped) == 1 and skipped.iloc[0]["code"] == "1004"
    assert "現金及び現金同等物" in skipped.iloc[0]["reason"]

    r = all_df.set_index("銘柄コード")
    assert abs(r.loc["1001", "ネットネット指数"] - 0.5) < 1e-9
    assert abs(r.loc["1002", "ネットネット指数"] - 3.0) < 1e-9
    assert abs(r.loc["1003", "ネットネット指数"] - 0.9) < 1e-9
    assert pd.isna(r.loc["1005", "ネットネット指数"]) or \
        r.loc["1005", "ネットネット指数"] is None, "債務超過は指数None"

    # --- 抽出とソート ---
    hits = sc.screen(all_df)
    assert list(hits["銘柄コード"]) == ["1001", "1003"], f"抽出結果: {list(hits['銘柄コード'])}"
    assert bool(hits.iloc[0]["グレアム基準該当"]) is True
    assert bool(hits.iloc[1]["グレアム基準該当"]) is False

    # --- strict モード: 有価証券欠損もスキップ ---
    all_strict, skipped_strict = sc.evaluate(stocks, make_cache(), strict=True)
    assert len(all_strict) == 1 and all_strict.iloc[0]["銘柄コード"] == "1001"
    assert len(skipped_strict) == 4

    # --- レポート出力がエラーなく走ること ---
    sc.report(hits, all_df, skipped)
    assert Path(sc.RESULT_CSV).exists()

    print("\nすべてのテストに合格しました")


if __name__ == "__main__":
    main()
