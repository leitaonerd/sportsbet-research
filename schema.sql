-- =============================================================================
-- Esquema MySQL do Brasileirão (Sofascore)
-- -----------------------------------------------------------------------------
-- Utilizado para criar as tabelas manualmente (ex.: via MySQL Workbench ou
-- `mysql < schema.sql`). O script `sofascore.py` TAMBEM cria este esquema
-- automaticamente ao conectar, caso prefira nao executá-lo a mao.
--
-- Recria as tabelas (idempotente) no banco `brasiliaodb`.
-- =============================================================================

USE brasiliaodb;

-- 1) Temporadas ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    id   INT PRIMARY KEY,
    year INT,
    name VARCHAR(255)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 2) Times ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id         INT PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    short_name VARCHAR(64)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 3) Jogadores -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id            INT PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    short_name    VARCHAR(64),
    position      VARCHAR(64),
    jersey_number INT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 4) Partidas ------------------------------------------------------------------
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

-- 5) Escalacoes ----------------------------------------------------------------
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

-- 6) Incidentes ----------------------------------------------------------------
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