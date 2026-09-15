"""
Carrega e limpa o BRA.csv (footballdata) em uma tabela cronologica limpa.

Saida: data/processed/matches.parquet
- uma linha por partida, ordenada por data
- colunas: match_id, season, round?, date, home, away, home_team_id, away_team_id,
  hg, ag, result (H/D/A), e odds de fechamento (PSCH/D/A, AvgC/D/A, MaxC/D/A)
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "BRA.csv"
OUT_DIR = ROOT / "data" / "processed"

ODD_COLS = {
    "PSCH": "odds_psc_h", "PSCD": "odds_psc_d", "PSCA": "odds_psc_a",
    "AvgCH": "odds_avg_h", "AvgCD": "odds_avg_d", "AvgCA": "odds_avg_a",
    "MaxCH": "odds_max_h", "MaxCD": "odds_max_d", "MaxCA": "odds_max_a",
}

# Normalizacao de nomes de clubes (BRA.csv usa variantes ao longo dos anos)
TEAM_ALIASES = {
    "Atletico MG": "Atletico Mineiro", "Atletico-MG": "Atletico Mineiro",
    "Athletico-PR": "Atletico Paranaense", "Atletico PR": "Atletico Paranaense",
    "Atletico GO": "Atletico Goianiense", "Atletico-GO": "Atletico Goianiense",
    "Botafogo RJ": "Botafogo", "Flamengo RJ": "Flamengo",
    "Vasco DA Gama": "Vasco", "Vasco Catarte": "Vasco",
    "Gremio Novorizontino": "Novorizontino",
    "Red Bull Bragantino": "Bragantino",
    "Cuiaba": "Cuiaba", "Criciuma": "Criciuma",
}


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW)
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
    df = df.rename(columns={"HG": "hg", "AG": "ag", "Res": "result",
                            "Season": "season"})
    df["home"] = df["Home"].map(lambda s: TEAM_ALIASES.get(s, s))
    df["away"] = df["Away"].map(lambda s: TEAM_ALIASES.get(s, s))
    df = df.rename(columns=ODD_COLS)
    keep = ["season", "Date", "Time", "home", "away", "hg", "ag", "result",
            *ODD_COLS.values()]
    df = df[keep].copy()
    df["odds_psc_h"] = pd.to_numeric(df["odds_psc_h"], errors="coerce")
    df["odds_psc_d"] = pd.to_numeric(df["odds_psc_d"], errors="coerce")
    df["odds_psc_a"] = pd.to_numeric(df["odds_psc_a"], errors="coerce")
    for c in ODD_COLS.values():
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["Date", "Time"]).reset_index(drop=True)
    df["match_id"] = df.index
    # IDs estaveis de time (alfabetico sobre o vocabulario canônico)
    teams = sorted(set(df["home"]) | set(df["away"]))
    tmap = {t: i for i, t in enumerate(teams)}
    df["home_team_id"] = df["home"].map(tmap)
    df["away_team_id"] = df["away"].map(tmap)
    df = df.dropna(subset=["hg", "ag", "result"])
    return df


def build() -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_raw()
    df.to_parquet(OUT_DIR / "matches.parquet", index=False)
    print(f"matches: {len(df)} rows, seasons {df['season'].min()}-{df['season'].max()}, "
          f"teams {df['home_team_id'].nunique()}")
    return df


if __name__ == "__main__":
    build()
