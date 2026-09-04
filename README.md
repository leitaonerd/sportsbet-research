# Brasileirão Scraper (Sofascore) 🏆

Extrator completo do histórico de partidas do **Brasileirão Série A**, consumindo
diretamente a **API interna (não documentada)** do [Sofascore](https://www.sofascore.com/)
(engenharia reversa de XHR/Fetch — sem Selenium, sem parse de HTML).

Os dados extraídos são persistidos em um banco **MySQL** com **SQL puro e
inserções em lote** (sem ORM), seguindo a ordem relacional estrita definida no
plano [`webscrapping.md`](webscrapping.md).

---

## 📋 O que o scraper coleta

Para cada temporada do Brasileirão (torneio `325`, Série A):

| Fase | Endpoint (API Sofascore) | Dados extraídos |
| :--- | :--- | :--- |
| **1. Descoberta** | `/unique-tournament/325/seasons` | Lista de temporadas disponíveis |
| **2. Eventos** | `/unique-tournament/325/season/{id}/events/round/{1..38}` | Partidas por rodada (times, placar, status) |
| **3a. Escalações** | `/event/{id}/lineups` | Titulares, reservas, posições, formação tática |
| **3b. Incidentes** | `/event/{id}/incidents` | Gols, cartões, substituições com minutagem exata |
---

## 🧱 Modelo de dados (MySQL)

O esquema segue a ordem de carga **1.Times → 2.Jogadores → 3.Partidas →
4.Escalações → 5.Incidentes** (ver tabelas em [`schema.sql`](schema.sql)).

| Tabela      | Descrição | Chaves estrangeiras |
|-------------|-----------|---------------------|
| `seasons`   | Temporadas do torneio | — |
| `teams`     | Clubes (nome / sigla) | — |
| `players`   | Jogadores | — |
| `matches`   | Partidas (rodada, placar, status, timestamp) | `seasons`, `teams`(x2) |
| `lineups`   | Escalação por partida/time/jogador | `matches`, `teams`, `players` |
| `incidents` | Gols, cartões, subs. (minutagem) | `matches`, `players`(x3) |

> Todas as tabelas usam `CREATE TABLE IF NOT EXISTS` e `INSERT IGNORE`, então o
> script é **idempotente** — reexecutar não duplica dados.

---

## 🚀 Como rodar na sua máquina

### 1. Pré-requisitos

- **Python 3.9+** ([python.org](https://www.python.org/downloads/))
- **MySQL Server 8.x** instalado e rodando localmente
  - Windows: [MySQL Installer](https://dev.mysql.com/downloads/installer/)
  - Ubuntu/Debian: `sudo apt install mysql-server`
  - macOS: `brew install mysql`
- **pip** e, opcionalmente, um **virtualenv**

### 2. Clone o repositório

```bash
git clone <URL-do-seu-repositorio>
cd sportsbet
```

### 3. Crie e ative o ambiente virtual (opcional, recomendado)

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Instale as dependências

```bash
pip install -r requirements.txt
```

Depende de: `requests`, `mysql-connector-python`, `python-dotenv`.

### 5. Configure o MySQL

Existem **duas** formas equivalentes — escolha uma.

> **Opção A (recomendada para dev local):** o próprio script cria o banco e as
> tabelas automaticamente na primeira execução. Basta o servidor MySQL estar no
> ar e você ter um usuário com permissão de criar banco (ex.: `root`).

> **Opção B (manual):** rode o bootstrap com `root` para criar o banco e um
> usuário dedicado, depois aplique o schema:

```bash
mysql -u root -p < setup_mysql.sql     # cria banco + usuario 'sportsbet'
mysql -u sportsbet -psportsbet123 brasiliaodb < schema.sql
```

> **Opção C (Workbench):** abra e execute o `schema.sql` no MySQL Workbench.

### 6. Configure as credenciais (`.env`)

Copie o modelo e preencha com os dados do seu MySQL:

```bash
cp .env.example .env           # Linux/macOS
copy .env.example .env        # Windows
```

```ini
# .env
DB_HOST=localhost
DB_PORT=3306
DB_USER=sportsbet
DB_PASSWORD=sportsbet123
DB_NAME=brasiliaodb
```

Se não criar o `.env`, os padrões usados são: `localhost:3306`, usuário `root`,
senha vazia, banco `brasiliaodb`.

### 7. Rode o scraper

```bash
python sofascore.py
```

O pipeline executa as fases 1→3 e persiste tudo no MySQL. Para extrair outra
temporada, edite a chamada no final do arquivo:

```python
if __name__ == "__main__":
    main(year=2023)   # troque o ano desejado
```
---

## 📂 Estrutura do projeto

```
sportsbet/
├── .env.example        # Modelo de configuração (copie p/ .env)
├── .gitignore          # Ignora .env, *.db, __pycache__, .venv etc.
├── README.md           # Este documento
├── requirements.txt    # Dependências Python
├── schema.sql          # DDL MySQL (cria as 6 tabelas)
├── setup_mysql.sql     # One-shot: cria banco + usuário dedicado
├── sofascore.py        # Scraper completo (Fases 1-3 + persistência MySQL)
├── config.py           # Lê a configuração do MySQL via .env
└── webscrapping.md     # Plano/especificação original
```

## ⚙️ Configuração (variáveis de ambiente)

Todas as variáveis são lidas pelo [`config.py`](config.py) (via `python-dotenv`):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DB_HOST` | `localhost` | Host/servidor MySQL |
| `DB_PORT` | `3306` | Porta MySQL |
| `DB_USER` | `root` | Usuário do banco |
| `DB_PASSWORD` | (vazio) | Senha do usuário |
| `DB_NAME` | `brasiliaodb` | Nome do database |

---

## 🔧 Resolução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `Connection refused` / `[DB] Falha ao conectar` | MySQL desligado ou porta errada | Inicie o serviço MySQL e confira `DB_HOST`/`DB_PORT` |
| `Access denied for user` | Credenciais erradas | Verifique `DB_USER`/`DB_PASSWORD` no `.env` |
| `Unknown database` | Banco não criado | Opção A faz bootstrap automático; ou rode `setup_mysql.sql` |
| `403 Forbidden` nos requests | Anti-bot/Cloudflare do Sofascore | O scraper já usa headers miméticos + retentativas; confirme o `User-Agent` atual |
| `429 Too Many Requests` | Rate limit do Sofascore | O script aguarda `time.sleep(random.uniform(1.5,3.5))` entre detalhes; aumente `MAX_ATTEMPTS`/delays se necessário |

> ⚠️ **Nota sobre o Sofascore:** a API interna usada não é pública e pode mudar
> ou bloquear requisições externas. Execute com moderação (respeite o rate
> limit) e sob sua própria responsabilidade, em conformidade com os termos do site.

## ✅ Verificação rápida após rodar

```sql
USE brasiliaodb;
SELECT COUNT(*) AS partidas    FROM matches;
SELECT COUNT(*) AS incidentes  FROM incidents;
SELECT COUNT(*) AS escalacoes  FROM lineups;
```