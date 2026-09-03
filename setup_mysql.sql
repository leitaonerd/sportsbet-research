-- =============================================================================
-- Setup one-shot do MySQL (cria banco + usuario dedicado).
-- -----------------------------------------------------------------------------
-- Rode como root/administrador UMA vez:
--   mysql -u root -p < setup_mysql.sql
-- Depois configure as mesmas credenciais no arquivo `.env`.
-- =============================================================================

-- Cria o banco de dados da aplicacao.
CREATE DATABASE IF NOT EXISTS brasiliaodb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Cria um usuario dedicado (nao usar root no dia a dia).
-- Ajuste a senha antes de rodar em producao!
CREATE USER IF NOT EXISTS 'sportsbet'@'localhost' IDENTIFIED BY 'sportsbet123';
CREATE USER IF NOT EXISTS 'sportsbet'@'%' IDENTIFIED BY 'sportsbet123';

-- Concede acesso total apenas ao banco da aplicacao.
GRANT ALL PRIVILEGES ON brasiliaodb.* TO 'sportsbet'@'localhost';
GRANT ALL PRIVILEGES ON brasiliaodb.* TO 'sportsbet'@'%';

FLUSH PRIVILEGES;