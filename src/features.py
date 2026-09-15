"""
Feature engineering pre-jogo, sem leakage: tudo calculado apenas com
partidas ANTERIORES a data da partida em questao.

Produz:
1. features por partida (XGB baseline): data/processed/features.parquet
2. snapshots de grafo por rodada (Dynamic Attention GNN futuro):
   data/processed/snapshots/edges_r{season}_{round}.parquet
   (estado dos nodes congelado no inicio da rodada, incluido nas edges)
"""
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
SNAP_DIR = OUT_DIR / "snapshots"

ELO_K = 20.0
ELO_HOME_ADV = 65.0
ELO_START = 1500.0


class TeamState:
    """Estado acumulado de um time (atualizado apenas com jogos passados)."""

    def __init__(self, name: str):
        self.name = name
        self.elo = ELO_START
        self.recent = deque(maxlen=10)          # (pts, gf, ga)
        self.recent_home = deque(maxlen=5)
        self.recent_away = deque(maxlen=5)
        self.season = None
        self.season_pts = self.season_gf = self.season_ga = 0
        self.season_matches = 0
        self.last_match_date = None

    def features(self, as_of: SimpleNamespace) -> dict:
        r5 = list(self.recent)[:5]
        r10 = list(self.recent)
        cur_season = self.season == as_of.season
        return {
            "elo": self.elo,
            "form5_pts": sum(x[0] for x in r5), "form5_gf": sum(x[1] for x in r5),
            "form5_ga": sum(x[2] for x in r5),
            "form10_pts": sum(x[0] for x in r10), "form10_gf": sum(x[1] for x in r10),
            "form10_ga": sum(x[2] for x in r10),
            "home5_pts": sum(x[0] for x in self.recent_home),
            "home5_gf": sum(x[1] for x in self.recent_home),
            "home5_ga": sum(x[2] for x in self.recent_home),
            "away5_pts": sum(x[0] for x in self.recent_away),
            "away5_gf": sum(x[1] for x in self.recent_away),
            "away5_ga": sum(x[2] for x in self.recent_away),
            "season_pts": self.season_pts if cur_season else 0,
            "season_gd": (self.season_gf - self.season_ga) if cur_season else 0,
            "season_matches": self.season_matches if cur_season else 0,
            "rest_days": ((as_of.date - self.last_match_date).days
                          if self.last_match_date is not None else 30.0),
        }

    def update(self, gf, ga, is_home, date, season):
        pts = 3 if gf > ga else (1 if gf == ga else 0)
        self.recent.append((pts, gf, ga))
        (self.recent_home if is_home else self.recent_away).append((pts, gf, ga))
        if self.season != season:
            self.season = season
            self.season_pts = self.season_gf = self.season_ga = 0
            self.season_matches = 0
        self.season_pts += pts
        self.season_gf += gf
        self.season_ga += ga
        self.season_matches += 1
        self.last_match_date = date


def elo_update(elo_h: float, elo_a: float, hg: int, ag: int) -> tuple:
    """Atualizacao Elo padrao com vantagem de casa."""
    exp_h = 1.0 / (1.0 + 10 ** (((elo_a + ELO_HOME_ADV) - elo_h) / 400.0))
    score_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
    delta = ELO_K * (score_h - exp_h)
    return elo_h + delta, elo_a - delta


class H2HState:
    """Historico de confrontos diretos entre pares de times."""

    def __init__(self):
        self.hist: dict = {}

    def features(self, h: int, a: int, home_name: str) -> dict:
        games = list(self.hist.get(tuple(sorted((h, a))), []))[-5:]
        pts = gf = ga = 0
        for gh, ga_, home_then in games:
            if home_then == home_name:
                gf += gh
                ga += ga_
            else:
                gf += ga_
                ga += gh
            if (gh > ga_ and home_then == home_name) or \
               (ga_ > gh and home_then != home_name):
                pts += 3
            elif gh == ga_:
                pts += 1
        return {"h2h_matches": len(self.hist.get(tuple(sorted((h, a))), [])),
                "h2h_home_pts_last5": pts, "h2h_home_gf_last5": gf,
                "h2h_home_ga_last5": ga}

    def update(self, h, a, home_name, hg, ag):
        self.hist.setdefault(tuple(sorted((h, a))), deque(maxlen=20)).append(
            (hg, ag, home_name))


EDGE_FEATURES = ["h2h_matches", "h2h_home_pts_last5", "h2h_home_gf_last5",
                 "h2h_home_ga_last5"]



def build_features(matches: pd.DataFrame, save: bool = True):
    """Percorre as partidas em ordem cronologica emitindo features pre-jogo.

    Retorna (features_df, snapshot_map) onde snapshot_map[(season, round)] =
    (nodes_df, edges_df) com estado global congelado no primeiro jogo da rodada.
    """
    states, h2h, rows = {}, H2HState(), []
    snapshots: dict = {}
    season_count: dict = {}  # partidas ja vistas na temporada (para aproximar rodada)

    for _, m in matches.iterrows():
        season, date = int(m["season"]), m["Date"]
        # BRA.csv nao tem rodada; Serie A tem 10 jogos por rodada -> aproximacao
        rnd = season_count.get(season, 0) // 10
        season_count[season] = season_count.get(season, 0) + 1
        h, a = int(m["home_team_id"]), int(m["away_team_id"])
        as_of = SimpleNamespace(season=season, date=date)
        hs = states.setdefault(h, TeamState(m["home"]))
        aws = states.setdefault(a, TeamState(m["away"]))
        hf, af = hs.features(as_of), aws.features(as_of)
        hhf = h2h.features(h, a, m["home"])
        rows.append({
            "match_id": m["match_id"], "season": season, "date": date,
            "home": m["home"], "away": m["away"],
            "home_team_id": h, "away_team_id": a,
            **{f"home_{k}": v for k, v in hf.items()},
            **{f"away_{k}": v for k, v in af.items()},
            **hhf,
            "hg": int(m["hg"]), "ag": int(m["ag"]), "result": m["result"],
        })
        hg_, ag_ = int(m["hg"]), int(m["ag"])
        # --- snapshot pre-jogo da rodada: congelado no primeiro jogo ---
        key = (season, rnd)
        if key not in snapshots:
            nodes = pd.DataFrame([
                {"team_id": tid, "team": st.name, **st.features(as_of)}
                for tid, st in sorted(states.items())])
            edges = pd.DataFrame([{
                "season": season, "round": rnd, "home_team_id": h,
                "away_team_id": a, "match_id": m["match_id"],
                **hhf, "hg": hg_, "ag": ag_, "result": m["result"],
            }])
            snapshots[key] = (nodes, edges)
        else:
            snapshots[key][1].loc[len(snapshots[key][1])] = {
                "season": season, "round": rnd, "home_team_id": h,
                "away_team_id": a, "match_id": m["match_id"],
                **hhf, "hg": hg_, "ag": ag_, "result": m["result"],
            }
        # --- atualiza estados com o resultado (apos calcular features) ---
        hs.update(hg_, ag_, True, date, season)
        aws.update(ag_, hg_, False, date, season)
        hs.elo, aws.elo = elo_update(hs.elo, aws.elo, hg_, ag_)
        h2h.update(h, a, m["home"], hg_, ag_)

    feats = pd.DataFrame(rows)
    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        feats.to_parquet(OUT_DIR / "features.parquet", index=False)
        for (s, r), (nodes, edges) in snapshots.items():
            nodes.to_parquet(SNAP_DIR / f"nodes_r{s}_{r}.parquet", index=False)
            edges.to_parquet(SNAP_DIR / f"edges_r{s}_{r}.parquet", index=False)
    return feats, snapshots


def main():
    import data_loader
    matches = data_loader.load_raw()
    feats, snaps = build_features(matches)
    print(f"features: {len(feats)} rows x {feats.shape[1]} cols; "
          f"{len(snaps)} round snapshots")


if __name__ == "__main__":
    main()
