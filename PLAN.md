# Sportsbet — Baseline XGBoost → Fair Odds → (futuro) Dynamic Attention GNN

## Objetivo

Construir um **baseline XGBoost** para prever resultados do Brasileirão Série A
(1X2 e gols), derivar **odds justas (fair odds)** a partir das probabilidades
calibradas, e deixar toda a infraestrutura pronta para uma comparação futura
com uma **Dynamic Attention GNN**.

Fonte de dados v1: **BRA.csv** (footballdata — temporadas 2012–2024, com
resultados e odds de fechamento PSCH/D/A, MaxC/D/A, AvgC/D/A, B365C/D/A).
Enriquecimento com MySQL (sofascore: lineups, incidents) fica para v2.

---

## Arquitetura em dois estágios

### Estágio 1 — XGBoost

- **Target primário: 1X2** — classificação multinomial (`multi:softprob`)
  → P(H), P(D), P(A).
- **Target secundário: gols** — duas regressões (`count:poisson`) para gols
  home e away → deriva O/U 2.5, BTTS, e 1X2 via Poisson (cross-check).

### Estágio 2 — Fair odds

- **Fair odds = 1 / probabilidade** (após calibração isotônica das probs).
- **Edge = bookmaker_odds × model_probability − 1** (valor quando > 0).
- Benchmark: `AvgC` (média de mercado, de-vigada) como baseline;
  backtest de ROI com `MaxC` (melhor preço alcançável), stake flat.

---

## Design orientado à Dynamic Attention GNN (comparação justa)

1. **Features decompostas por time** (home/away separados, não pré-diferenciadas)
   → viram node features do grafo.
2. **Snapshots de grafo**: pipeline emite
   - `nodes_r{round}.parquet` — estado de **todos os 20 times** congelado no
     boundary da rodada (cursor global de tempo, sem vazamento);
   - `edges_r{round}.parquet` — arestas = partidas, com features de aresta
     (venue, rest days, H2H) + label (resultado/gols).
   - Tabela crua com `start_timestamp` mantida para opção **continuous-time**
     (TGAT/TGN-style) no futuro.
3. **Protocolo de avaliação congelado e compartilhado**: mesmos folds
   walk-forward, mesmas métricas (log loss, Brier, accuracy, calibração; RMSE/MAE
   para gols; ROI para value bets) para qualquer modelo.
4. **Escada de ablação**:
   1. Mercado (odds de-vigadas) — a régua
   2. XGBoost em features tabulares
   3. XGBoost + features de H2H (aproxima tabular do "attention over past meetings")
   4. Dynamic Attention GNN sobre os mesmos snapshots

---

## Features (todas estritamente pré-jogo, sem leakage)

- **Elo rating** por time (atualizado pós-jogo) — "message passing pobre".
- **Forma rolling** (N=5, 10): pontos, gols pró, gols contra — splits home/away.
- **Força de temporada**: pontos/jogo, saldo, posição — até a rodada atual.
- **Rest days** desde a última partida; nº da rodada; flag time recém-promovido.
- **H2H**: últimos k confrontos, recência, específico por venue.

---

## Validação

- **Split temporal apenas**: walk-forward expanding window
  (treino 2012→N−1, teste temporada N; foco 2022/2023/2024).
- Métricas vs **probabilidades implícitas do mercado de-vigadas**
  (normalizar 1/AvgCH + 1/AvgCD + 1/AvgCA para somar 1).
- Backtest de ROI das value bets por temporada.

---

## Estrutura de arquivos

```
data/processed/
├── matches.parquet              # tabela crônológica limpa (fonte da verdade)
├── snapshots/
│   ├── nodes_r{round}.parquet   # estado dos 20 times congelado por rodada
│   └── edges_r{round}.parquet   # partidas + features de aresta + labels
└── predictions/
    └── xgb_{fold}.parquet       # preds XGB + probs do mercado (schema padrão)

src/
├── data_loader.py      # carrega/limpa BRA.csv → parquet
├── features.py         # Elo, forma, H2H, rest days → snapshots
├── train_1x2.py        # XGBoost multiclass + calibração isotônica
├── train_goals.py      # Poisson home/away → O/U 2.5, BTTS
├── fair_odds.py        # fair odds, edge, backtest ROI
├── evaluate.py         # avaliador model-agnostic (consumido pelo GNN depois)
└── predict.py          # CLI: fixture → probs, fair odds, edge
```

`requirements.txt` recebe: `xgboost`, `pandas`, `pyarrow`, `scikit-learn`,
`numpy`, `matplotlib`.

---

## Roadmap de execução

- [x] Passo 1 — `data_loader.py` + `matches.parquet`
- [x] Passo 2 — `features.py` + snapshots (nodes/edges por rodada)
- [x] Passo 3 — `train_1x2.py` + calibração + walk-forward vs mercado
- [ ] Passo 4 — `train_goals.py` (Poisson)
- [ ] Passo 5 — `fair_odds.py` + backtest ROI
- [ ] Passo 6 — `evaluate.py` (harness model-agnostic)
- [ ] Passo 7 — `predict.py` (CLI)
- [ ] v2 — enriquecer com MySQL (lineups/incidents); Dynamic Attention GNN

## Premissas

- v1 usa só BRA.csv (completo 2012–2024; precisa das odds para fair-odds/edge).
- AvgC = benchmark de valor; MaxC = preço do backtest.
- Fair odds assumem probs calibradas; mercado inclui vig, modelo não.
