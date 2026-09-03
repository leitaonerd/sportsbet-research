# Plano de Extração: Dados do Brasileirão (Sofascore)

## 1. Objetivo
Realizar a extração do histórico completo de partidas do Brasileirão, incluindo dados detalhados de times, jogadores, escalações completas e eventos (substituições, cartões, etc).

## 2. Abordagem Principal
O Sofascore é uma Single Page Application (SPA). Ferramentas de extração baseadas em parse de HTML (BS4, Selenium) são ineficientes, pesadas e altamente suscetíveis a bloqueios.
**Estratégia:** Engenharia reversa da API interna do frontend (XHR/Fetch) para consumo direto dos endpoints não documentados e extração dos dados já estruturados em JSON.

## 3. Fluxo de Execução (Workflow)

### Fase 1: Descoberta de IDs
1. **Torneio:** Fixado como Brasileirão Série A (`uniqueTournamentId: 325`).
2. **Temporadas:** Consultar `/api/v1/unique-tournament/325/seasons` para mapear os anos disponíveis e capturar os respectivos `season_id`.

### Fase 2: Coleta de Eventos (Partidas)
1. **Iteração de Rodadas:** Para cada `season_id`, realizar um loop das rodadas (1 a 38).
2. **Endpoint:** `/api/v1/unique-tournament/325/season/{season_id}/events/round/{rodada}`
3. **Ação:** Armazenar a lista de identificadores únicos (`event_id`) de cada partida retornada.

### Fase 3: Extração de Detalhes (Lineups e Incidentes)
Para cada `event_id` coletado:
1. **Escalações:** Consumir `/api/v1/event/{event_id}/lineups` para obter titulares, reservas, posição tática e comissão técnica.
2. **Substituições/Eventos:** Consumir `/api/v1/event/{event_id}/incidents` para capturar a cronologia da partida (cartões, gols, substituições) com a minutagem exata.

## 4. Arquitetura e Persistência de Dados
* **Orquestração:** Python com a biblioteca `requests`.
* **Persistência:** Implementação de rotinas SQL puras para garantir inserções em lote eficientes e ter total controle sobre as constraints de concorrência relacional, evitando o overhead de ORMs na manipulação de grandes volumes de relacionamentos.

## 5. Desafios Esperados e Soluções

| Desafio | Causa | Solução |
| :--- | :--- | :--- |
| **Proteção Anti-bot / Cloudflare** | O site usa heurísticas de navegação para barrar scripts tradicionais. | Evitar baixar o HTML da página base. Apontar as requisições exclusivamente para os endpoints em JSON da API. |
| **Validação de Headers (403 Forbidden)** | A API verifica a origem da requisição para impedir acessos externos. | Mimetizar rigorosamente os headers de um navegador comum, com atenção especial ao `User-Agent`, `Origin`, e `Referer`. |
| **Rate Limiting (429 Too Many Requests)** | Alto volume de requisições disparadas por loops rápidos. | Implementar delays randômicos (ex: `time.sleep(random.uniform(1.5, 3.5))`) entre requisições nos endpoints de detalhes de partidas. |
| **Dependência Relacional Complexa** | Um incidente depende do jogador, que depende do time, que depende da partida. | Seguir uma ordem estrita de carga no SQL: 1. Times, 2. Jogadores, 3. Partidas, 4. Escalações, 5. Incidentes. |