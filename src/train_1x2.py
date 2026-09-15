"""
Treino XGBoost 1X2 (H/D/A) com validacao walk-forward temporal.

- Expanding window: treino em todas as temporadas anteriores a temporada de teste.
- Calibracao isotônica das probabilidades (necessaria para fair odds).
- Baseline de comparacao: probabilidades implicitas de mercado de-vigadas (AvgC).
- Saida: data/processed/predictions/xgb_{season}.parquet + metricas impressas.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent.parent
FEATS = ROOT / "data" / "processed" / "features.parquet"
OUT = ROOT / "data" / "processed"
PRED_DIR = ROOT / "data" / "processed" / "predictions"

EXCLUDE = {"match_id", "season", "date", "home", "away", "home_team_id",
           "away_team_id", "hg", "ag", "result"}
RESULTS = ["H", "D", "A"]

PARAMS = dict(n_estimators=150, max_depth=4, learning_rate=0.08,
              subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
              eval_metric="mlogloss", tree_method="hist", n_jobs=4,
              objective="multi:softprob", num_class=3, random_state=42)


def devig(o_h, o_d, o_a):
    """Probabilidades implicitas de mercado com vig removido."""
    inv = np.column_stack([1 / o_h, 1 / o_d, 1 / o_a])
    return inv / inv.sum(axis=1, keepdims=True)


def load():
    df = pd.read_parquet(FEATS)
    matches = pd.read_parquet(OUT / "matches.parquet")
    odds = matches[["match_id", "odds_avg_h", "odds_avg_d", "odds_avg_a",
                    "odds_max_h", "odds_max_d", "odds_max_a"]]
    df = df.merge(odds, on="match_id", how="left")
    return df.sort_values("date").reset_index(drop=True)


def feature_cols(df):
    return [c for c in df.columns
            if c not in EXCLUDE and not c.startswith("odds_")]


def market_baseline(test):
    return devig(test["odds_avg_h"], test["odds_avg_d"], test["odds_avg_a"])


def run(seasons_test=(2022, 2023, 2024)):
    df = load()
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    y = df["result"].map({r: i for i, r in enumerate(RESULTS)}).values
    cols = feature_cols(df)
    print(f"features: {len(cols)} cols | rows: {len(df)}")

    all_metrics = []
    for season in seasons_test:
        tr_idx = df["season"] < season
        te_idx = df["season"] == season
        Xtr, ytr = df.loc[tr_idx, cols], y[tr_idx.values]
        Xte, yte = df.loc[te_idx, cols], y[te_idx.values]

        base = XGBClassifier(**PARAMS)
        clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
        clf.fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)
        pred = proba.argmax(axis=1)

        mkt = market_baseline(df.loc[te_idx])
        # Brier multiclasse: media do somatorio quadratico por amostra
        brier = float(np.mean(np.sum((proba - np.eye(3)[yte]) ** 2, axis=1)))
        brier_mkt = float(np.mean(np.sum((mkt - np.eye(3)[yte]) ** 2, axis=1)))
        m = {
            "season": season, "n": len(Xte),
            "xgb_logloss": log_loss(yte, proba),
            "mkt_logloss": log_loss(yte, mkt),
            "xgb_brier": brier,
            "mkt_brier": brier_mkt,
            "xgb_acc": accuracy_score(yte, pred),
            "mkt_acc": accuracy_score(yte, mkt.argmax(axis=1)),
        }
        all_metrics.append(m)

        out = df.loc[te_idx, ["match_id", "season", "date", "home", "away",
                              "result", "odds_avg_h", "odds_avg_d",
                              "odds_avg_a"]].copy()
        out[["p_home", "p_draw", "p_away"]] = proba
        out.to_parquet(PRED_DIR / f"xgb_{season}.parquet", index=False)

    met = pd.DataFrame(all_metrics)
    met["logloss_vs_market"] = met["xgb_logloss"] / met["mkt_logloss"]
    print(met.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\nNota: logloss_vs_market < 1.0 significa modelo melhor que o mercado.")
    return met


if __name__ == "__main__":
    run()
