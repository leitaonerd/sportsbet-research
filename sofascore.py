"""
Scraper do Brasileirão (Sofascore) -- Engenharia reversa da API interna.

Implementa o fluxo completo descrito em webscrapping.md:
    Fase 1: Descoberta de IDs (temporadas do torneio 325 / Série A).
    Fase 2: Coleta de eventos (partidas) por rodada (1 a 38).
    Fase 3: Extração de detalhes (escalações e incidentes) por partida.
    Seção 4: Persistência com SQL puro e inserções em lote, seguindo a ordem de
             carga: 1.Times 2.Jogadores 3.Partidas 4.Escalações 5.Incidentes.
    Seção 5: Headers miméticos, delays randomicos e retentativas contra 403/429.

Requisitos: pip install requests
Dependência de banco: sqlite3 (stdlib) -- nenhum ORM, rotinas SQL puras.
"""

import random
import time
from typing import Any, Dict, List, Optional

import mysql.connector
import requests

import config

# ---------------------------------------------------------------- Torneio fixo
# Brasileirão Série A
TOURNAMENT_ID = 325
TOTAL_ROUNDS = 38

# -------------------------------------------------- Headers miméticos (Seção 5)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# Intervalos de delay (segundos) conforme Seção 5 do plano.
DELAY_COLLECTION = (0.5, 1.5)      # endpoints de rodada (menos sensíveis)
DELAY_DETAILS = (1.5, 3.5)         # endpoints de detalhes de partida
MAX_ATTEMPTS = 5
REQUEST_TIMEOUT = 30

BASE_URL = "https://api.sofascore.com/api/v1"

# ------------------------------------------------------------- Cliente HTTP
def fetch_json(url: str, delay_range: tuple = DELAY_DETAILS) -> Optional[dict]:
    """Executa uma requisição JSON com retentativa contra 403/429 e rate limiting.

    Retorna o JSON decodificado em caso de sucesso, ou None após esgotar as
    tentativas. Aplica um sleep randomico ao final a cada chamada bem-sucedida.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                time.sleep(random.uniform(*delay_range))
                return resp.json()

            if resp.status_code == 429:
                # Rate limit: aguarde mais e tente de novo.
                wait = random.uniform(5, 10)
                print(f"  [429] Rate limit atingido. Aguardando {wait:.1f}s e "
                      f"repetindo ({attempt}/{MAX_ATTEMPTS}).")
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                # Headers inválidos / bloqueio. Reporta e tenta novamente.
                print(f"  [403] Acesso negado em {url} (tentativa "
                      f"{attempt}/{MAX_ATTEMPTS}). Revalidando headers.")
                time.sleep(random.uniform(3, 6))
                continue

            print(f"  [HTTP {resp.status_code}] Falha em {url}.")
            return None

        except requests.RequestException as exc:
            print(f"  [Erro de rede] {exc} em {url}.")
            time.sleep(random.uniform(2, 4))

    print(f"  [Sem sucesso] Requisição desistida: {url}")
    return None


# ------------------------------------------------------------ Fase 1: Seasons
def get_seasons() -> List[dict]:
    """Mapeia todas as temporadas disponíveis do torneio 325."""
    url = f"{BASE_URL}/unique-tournament/{TOURNAMENT_ID}/seasons"
    data = fetch_json(url, delay_range=DELAY_COLLECTION)
    return data.get("seasons", []) if data else []


def get_season_id(target_year) -> Optional[int]:
    """Retorna o season_id correspondente a um ano alvo (ex.: 2023)."""
    for season in get_seasons():
        if str(season.get("year")) == str(target_year):
            return season["id"]
    return None


# ------------------------------------------------- Fase 2: Eventos (partidas)
def get_round_events(season_id: int, round_num: int) -> List[dict]:
    """Coleta os eventos de uma rodada específica da temporada."""
    url = (
        f"{BASE_URL}/unique-tournament/{TOURNAMENT_ID}"
        f"/season/{season_id}/events/round/{round_num}"
    )
    data = fetch_json(url, delay_range=DELAY_COLLECTION)
    return data.get("events", []) if data else []


def collect_event_ids(season_id: int, total_rounds: int = TOTAL_ROUNDS) -> List[dict]:
    """Itera pelas rodadas e devolve a lista de eventos (com event_id)."""
    events: List[dict] = []
    for round_num in range(1, total_rounds + 1):
        round_events = get_round_events(season_id, round_num)
        for ev in round_events:
            events.append({
                "event_id": ev["id"],
                "round": round_num,
                "home_team_id": ev["homeTeam"]["id"],
                "home_team": ev["homeTeam"]["name"],
                "away_team_id": ev["awayTeam"]["id"],
                "away_team": ev["awayTeam"]["name"],
                "home_score": (ev.get("homeScore") or {}).get("current"),
                "away_score": (ev.get("awayScore") or {}).get("current"),
                "status": (ev.get("status") or {}).get("description"),
                "start_timestamp": ev.get("startTimestamp"),
            })
        print(f"Rodada {round_num} coletada "
              f"({len(round_events)} eventos; total acumulado: {len(events)}).")
    return events


# -------------------------------------------- Fase 3: Lineups e Incidentes
def get_lineups(event_id: int) -> List[dict]:
    """Consome /event/{event_id}/lineups (titulares, reservas, tática, comissão)."""
    url = f"{BASE_URL}/event/{event_id}/lineups"
    data = fetch_json(url, delay_range=DELAY_DETAILS)
    return data.get("lineups", []) if data else []


def get_incidents(event_id: int) -> List[dict]:
    """Consome /event/{event_id}/incidents (cronologia com minutagem exata)."""
    url = f"{BASE_URL}/event/{event_id}/incidents"
    data = fetch_json(url, delay_range=DELAY_DETAILS)
    return data.get("incidents", []) if data else []
# ---------------------------------------------------------- Seção 4: Persistência
class Database:
    """Routines SQL puras (mysql-connector) seguindo a ordem estrita de carga:
    1.Times 2.Jogadores 3.Partidas 4.Escalações 5.Incidentes.

    Conecta ao servidor MySQL, cria o banco e as tabelas (configuracao via
    `.env`/config.py) caso ainda nao existam, e expoe metodos de insert em
    lote para cada entidade do modelo relacional.

    Como o scraper fica mais lento (rate limiting) do que o banco, inserimos em
    lote (executemany) com um unico commit por entidade para maximizar eficiencia.

    Compatível com a "Seção 4" do plano: ordem estrita de carga e SQL puro
    (sem ORM).
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS seasons (
        id   INT PRIMARY KEY,
        year INT,
        name VARCHAR(255)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

    CREATE TABLE IF NOT EXISTS teams (
        id         INT PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        short_name VARCHAR(64)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

    CREATE TABLE IF NOT EXISTS players (
        id            INT PRIMARY KEY,
        name          VARCHAR(255) NOT NULL,
        short_name    VARCHAR(64),
        position      VARCHAR(64),
        jersey_number INT
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

    CREATE TABLE IF NOT EXISTS matches (
        id              INT PRIMARY KEY,
        season_id       INT NOT NULL,
        round           INT,
        home_team_id    INT,
        away_team_id    INT,
        home_score      INT,
        away_score      INT,
        status          VARCHAR(32),
        start_timestamp BIGINT,
        CONSTRAINT fk_matches_season FOREIGN KEY (season_id)
            REFERENCES seasons (id),
        CONSTRAINT fk_matches_home   FOREIGN KEY (home_team_id)
            REFERENCES teams (id),
        CONSTRAINT fk_matches_away   FOREIGN KEY (away_team_id)
            REFERENCES teams (id)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

    CREATE TABLE IF NOT EXISTS lineups (
        match_id      INT NOT NULL,
        team_id       INT NOT NULL,
        player_id     INT NOT NULL,
        is_starter    TINYINT(1),
        position      VARCHAR(64),
        jersey_number INT,
        formation     VARCHAR(16),
        PRIMARY KEY (match_id, team_id, player_id),
        CONSTRAINT fk_lineups_match  FOREIGN KEY (match_id)
            REFERENCES matches (id),
        CONSTRAINT fk_lineups_team   FOREIGN KEY (team_id)
            REFERENCES teams (id),
        CONSTRAINT fk_lineups_player FOREIGN KEY (player_id)
            REFERENCES players (id)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

    CREATE TABLE IF NOT EXISTS incidents (
        id             INT PRIMARY KEY,
        match_id       INT NOT NULL,
        minute         INT,
        added_minute   INT,
        incident_type  VARCHAR(32),
        incident_class VARCHAR(32),
        player_id      INT,
        player_in_id   INT,
        player_out_id  INT,
        home_score     INT,
        away_score     INT,
        is_home        TINYINT(1),
        reason         VARCHAR(255),
        CONSTRAINT fk_incidents_match      FOREIGN KEY (match_id)
            REFERENCES matches (id),
        CONSTRAINT fk_incidents_player     FOREIGN KEY (player_id)
            REFERENCES players (id),
        CONSTRAINT fk_incidents_player_in  FOREIGN KEY (player_in_id)
            REFERENCES players (id),
        CONSTRAINT fk_incidents_player_out FOREIGN KEY (player_out_id)
            REFERENCES players (id)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
    """

    def __init__(self):
        """Conecta ao MySQL e garante que banco + tabelas existem (bootstrap)."""
        try:
            # Passo 1: conecta ao servidor (sem banco) p/ criar o banco se preciso.
            bootstrap = mysql.connector.connect(
                **config.connection_params(include_db=False)
            )
            with bootstrap.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS {config.DB_NAME} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            bootstrap.commit()
            bootstrap.close()

            # Passo 2: conecta ao banco ja existente e cria o esquema tabelas.
            self.conn = mysql.connector.connect(**config.connection_params())
            cur = self.conn.cursor()
            for stmt in self.SCHEMA.strip().split(";"):
                if stmt.strip():
                    cur.execute(stmt)
            self.conn.commit()
            cur.close()
            print(f"  [DB] Conectado a {config.DB_NAME} em {config.DB_HOST}:"
                  f"{config.DB_PORT} (usuario {config.DB_USER}).")
        except mysql.connector.Error as exc:
            raise RuntimeError(
                f"Falha ao conectar ao MySQL em {config.DB_HOST}:{config.DB_PORT} "
                f"(user={config.DB_USER}): {exc}. Verifique se o servidor esta "
                f"no ar e se as credenciais no arquivo `.env` estao corretas."
            ) from exc

    def _insert_many(self, sql: str, rows: List[tuple]) -> int:
        """Insere em lote (executemany) num unico commit por entidade.


        Usa INSERT IGNORE para permanecer idempotente: re-executar o scraper nao
        duplica linhas ja gravadas (ex.: uma partida reprocessada).
        """
        if not rows:
            return 0
        try:
            cur = self.conn.cursor()
            cur.executemany(sql, rows)
            self.conn.commit()
            cur.close()
            return len(rows)
        except mysql.connector.Error as exc:
            print(f"  [SQL] Erro ao inserir lote: {exc}")
            self.conn.rollback()
            return 0

    # --- 1) Times
    def insert_teams(self, teams: Dict[int, Dict[str, Any]]) -> int:
        sql = "INSERT IGNORE INTO teams (id, name, short_name) VALUES (%s, %s, %s)"
        rows = [(tid, t["name"], t.get("short_name")) for tid, t in teams.items()]
        return self._insert_many(sql, rows)

    # --- 2) Jogadores
    def insert_players(self, players: Dict[int, Dict[str, Any]]) -> int:
        sql = ("INSERT IGNORE INTO players "
               "(id, name, short_name, position, jersey_number) "
               "VALUES (%s, %s, %s, %s, %s)")
        rows = [
            (pid, p["name"], p.get("short_name"), p.get("position"),
             p.get("jersey_number"))
            for pid, p in players.items()
        ]
        return self._insert_many(sql, rows)

    # --- 3) Partidas
    def insert_matches(self, matches: List[tuple]) -> int:
        sql = ("INSERT IGNORE INTO matches "
               "(id, season_id, round, home_team_id, away_team_id, home_score, "
               "away_score, status, start_timestamp) VALUES "
               "(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
        return self._insert_many(sql, matches)

    # --- 4) Escalações
    def insert_lineups(self, lineups: List[tuple]) -> int:
        sql = ("INSERT IGNORE INTO lineups "
               "(match_id, team_id, player_id, is_starter, position, "
               "jersey_number, formation) VALUES (%s, %s, %s, %s, %s, %s, %s)")
        return self._insert_many(sql, lineups)

    # --- 5) Incidentes
    def insert_incidents(self, incidents: List[tuple]) -> int:
        sql = ("INSERT IGNORE INTO incidents "
               "(id, match_id, minute, added_minute, incident_type, "
               "incident_class, player_id, player_in_id, player_out_id, "
               "home_score, away_score, is_home, reason) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
        return self._insert_many(sql, incidents)

    def close(self):
        self.conn.close()


# ------------------------------------------------------- Orquestração (pipeline)
def extract_season(season, db: Database) -> None:
    """Executa o fluxo completo de extração/persistência para uma temporada."""
    season_id = season["id"]

    print(f"\n===== FASE 2: Coletando partidas da temporada "
          f"{season_id} ({season.get('year')}) =====")
    events = collect_event_ids(season_id)

    print(f"\n===== FASE 3: Extraindo escalações e incidentes de "
          f"{len(events)} partidas =====")

    teams: Dict[int, Dict[str, Any]] = {}
    players: Dict[int, Dict[str, Any]] = {}

    match_rows: List[tuple] = []
    lineup_rows: List[tuple] = []
    incident_rows: List[tuple] = []

    for event in events:
        eid = event["event_id"]

        # --- Registra times das partidas
        for tid, tname in ((event["home_team_id"], event["home_team"]),
                           (event["away_team_id"], event["away_team"])):
            teams.setdefault(tid, {"id": tid, "name": tname,
                                   "short_name": None})

        # --- Linhas de partida
        match_rows.append((
            eid, season_id, event["round"],
            event["home_team_id"], event["away_team_id"],
            event["home_score"], event["away_score"],
            event["status"], event["start_timestamp"],
        ))

        # --- Escalações
        for lu in get_lineups(eid):
            team_id = lu["teamId"]
            formation = lu.get("formation")
            for entry in lu.get("players", []):
                p = entry.get("player", {})
                pid = p["id"]
                players.setdefault(pid, {
                    "id": pid,
                    "name": p.get("name"),
                    "short_name": p.get("shortName"),
                    "position": p.get("position"),
                    "jersey_number": p.get("jerseyNumber"),
                })
                lineup_rows.append((
                    eid, team_id, pid,
                    0 if entry.get("substitute") else 1,
                    entry.get("position") or p.get("position"),
                    entry.get("jerseyNumber") or p.get("jerseyNumber"),
                    formation,
                ))

        # --- Incidentes
        for inc in get_incidents(eid):
            pid = (inc.get("player") or {}).get("id")
            pin = (inc.get("playerIn") or {}).get("id")
            pout = (inc.get("playerOut") or {}).get("id")
            for ref in (inc.get("player"), inc.get("playerIn"),
                        inc.get("playerOut")):
                if not ref or not ref.get("id"):
                    continue
                rid = ref["id"]
                players.setdefault(rid, {
                    "id": rid,
                    "name": ref.get("name"),
                    "short_name": ref.get("shortName"),
                    "position": ref.get("position"),
                    "jersey_number": ref.get("jerseyNumber"),
                })
            incident_rows.append((
                inc["id"], eid,
                inc.get("time"), inc.get("addedTime"),
                inc.get("incidentType"), inc.get("incidentClass"),
                pid, pin, pout,
                inc.get("homeScore"), inc.get("awayScore"),
                1 if inc.get("isHome") else 0,
                inc.get("reason"),
            ))

        print(f"Partida {eid} processada "
              f"({event['home_team']} x {event['away_team']}).")

    # ---- Persistência na ordem estrita: Times -> Jogadores -> Partidas
    # ---- -> Escalações -> Incidentes
    print(f"\n===== SEÇÃO 4: Persistindo dados em SQL puro =====")
    db.insert_teams(teams)
    db.insert_players(players)
    db.insert_matches(match_rows)
    db.insert_lineups(lineup_rows)
    db.insert_incidents(incident_rows)

    print(f"  Times: {len(teams)} | Jogadores: {len(players)} | "
          f"Partidas: {len(match_rows)} | Escalações: {len(lineup_rows)} | "
          f"Incidentes: {len(incident_rows)}")


def main(year: int) -> None:
    """Pipeline completo: Fase 1 -> Fase 2 -> Fase 3 -> Persistência (MySQL)."""
    print("===== FASE 1: Descobrindo temporadas =====")
    all_seasons = get_seasons()
    target = [s for s in all_seasons if str(s.get("year")) == str(year)]
    if not target:
        available = sorted({s.get("year") for s in all_seasons}, reverse=True)
        print(f"Temporada {year} não encontrada. Disponíveis: {available}")
        return
    season = target[0]
    print(f"Temporada selecionada: id={season['id']}, year={season['year']}")

    db = Database()
    try:
        # Seed das temporadas disponíveis (INSERT IGNORE mantem a operacao idempotente).
        seasons_tbl = [(s["id"], s.get("year"), s.get("name"))
                       for s in all_seasons]
        cur = db.conn.cursor()
        cur.executemany(
            "INSERT IGNORE INTO seasons (id, year, name) VALUES (%s, %s, %s)",
            seasons_tbl,
        )
        db.conn.commit()
        cur.close()
        extract_season(season, db)
    finally:
        db.close()

    print("\nPipeline concluído com sucesso.")


if __name__ == "__main__":
    # Ano alvo facilmente configurável. Ex.: extrair a temporada de 2023.
    main(year=2023)