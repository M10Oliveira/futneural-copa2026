"""
gerar_dataset.py
================
Constroi o historico_jogos.csv a partir de jogos REAIS baixados da
API-Football.

Cada linha do CSV representa um CONFRONTO (nao um time isolado), com
as estatisticas rolling de ambos os lados calculadas a partir dos jogos
ANTERIORES — sem vazamento de dados.

Colunas de saida:
  GF_Casa, GC_Casa, Forma_Casa, GF_Fora, GC_Fora, Forma_Fora, Resultado_Real

O rate limiting e o cache de fixtures sao tratados pelo api_football.py,
entao re-executar este script nao gasta cota de API se os dados ja
estiverem cacheados.
"""

import csv
import api_football as fb

# ------------------------------------------------------------------
# CONFIGURACAO
# ------------------------------------------------------------------
SELECOES = [
    "Brazil", "Argentina", "France", "Germany", "Spain",
    "England", "Portugal", "Netherlands", "Belgium", "Italy",
    "Uruguay", "Colombia", "Mexico", "USA", "Japan",
    "Morocco", "Senegal", "South Korea", "Australia", "Croatia",
]

JANELA = 5
TEMPORADAS = [2022, 2023, 2024]
ARQUIVO_SAIDA = "historico_jogos.csv"
MIN_HISTORICO = 3

# ------------------------------------------------------------------


def _media(lista, n):
    trecho = lista[-n:] if len(lista) >= n else lista
    return round(sum(trecho) / len(trecho), 2) if trecho else None


def gerar_dataset():
    if not fb.chave_configurada():
        print("FOOTBALL_API_KEY nao configurada.")
        return

    print(f"Baixando jogos de {len(SELECOES)} selecoes em {TEMPORADAS}...")
    print(f"Janela de features: {JANELA} jogos anteriores\n")

    # 1. Resolver IDs de todos os times
    ids_times = {}
    for nome in SELECOES:
        print(f"  Buscando ID: {nome}...", end=" ", flush=True)
        try:
            encontrado = fb.buscar_id_time(nome)
            if encontrado:
                ids_times[encontrado[0]] = encontrado[1]
                print(f"OK (id={encontrado[0]}, {encontrado[1]})")
            else:
                print("nao encontrado.")
        except fb.FootballAPIError as e:
            print(f"erro: {e}")

    if not ids_times:
        print("\nNenhum time encontrado.")
        return

    # 2. Baixar TODOS os fixtures, deduplicar por fixture_id
    todos_fixtures = {}
    for team_id, nome in ids_times.items():
        print(f"  Fixtures: {nome}...", end=" ", flush=True)
        count = 0
        for temporada in TEMPORADAS:
            fxs = fb.baixar_fixtures_temporada(team_id, temporada)
            for fx in fxs:
                fid = fx["fixture"]["id"]
                if fid not in todos_fixtures:
                    todos_fixtures[fid] = fx
                    count += 1
        print(f"{count} novos fixtures.")

    print(f"\nTotal de fixtures unicos: {len(todos_fixtures)}")

    # 3. Ordenar cronologicamente
    fixtures_ordenados = sorted(
        todos_fixtures.values(),
        key=lambda x: x["fixture"]["timestamp"],
    )

    # 4. Processar: manter historico rolling por team_id
    historicos = {}  # team_id -> {"gf": [], "gc": [], "pts": []}
    linhas = []

    for fx in fixtures_ordenados:
        home_id = fx["teams"]["home"]["id"]
        away_id = fx["teams"]["away"]["id"]
        gols_home = fx["goals"]["home"]
        gols_away = fx["goals"]["away"]

        if gols_home is None or gols_away is None:
            continue

        hist_home = historicos.get(home_id)
        hist_away = historicos.get(away_id)

        tem_hist_home = hist_home and len(hist_home["gf"]) >= MIN_HISTORICO
        tem_hist_away = hist_away and len(hist_away["gf"]) >= MIN_HISTORICO

        if tem_hist_home and tem_hist_away:
            gf_casa = _media(hist_home["gf"], JANELA)
            gc_casa = _media(hist_home["gc"], JANELA)
            forma_casa = _media(hist_home["pts"], JANELA)

            gf_fora = _media(hist_away["gf"], JANELA)
            gc_fora = _media(hist_away["gc"], JANELA)
            forma_fora = _media(hist_away["pts"], JANELA)

            if gols_home > gols_away:
                resultado = "CASA"
            elif gols_home == gols_away:
                resultado = "EMPATE"
            else:
                resultado = "FORA"

            linhas.append({
                "GF_Casa": gf_casa,
                "GC_Casa": gc_casa,
                "Forma_Casa": forma_casa,
                "GF_Fora": gf_fora,
                "GC_Fora": gc_fora,
                "Forma_Fora": forma_fora,
                "Resultado_Real": resultado,
            })

        # Atualizar historico de ambos os times APOS gerar a linha
        if home_id not in historicos:
            historicos[home_id] = {"gf": [], "gc": [], "pts": []}
        historicos[home_id]["gf"].append(gols_home)
        historicos[home_id]["gc"].append(gols_away)
        historicos[home_id]["pts"].append(3 if gols_home > gols_away else (1 if gols_home == gols_away else 0))

        if away_id not in historicos:
            historicos[away_id] = {"gf": [], "gc": [], "pts": []}
        historicos[away_id]["gf"].append(gols_away)
        historicos[away_id]["gc"].append(gols_home)
        historicos[away_id]["pts"].append(3 if gols_away > gols_home else (1 if gols_away == gols_home else 0))

    if not linhas:
        print("\nNenhum dado gerado. Verifique a chave da API e a cota.")
        return

    # 5. Salvar CSV
    colunas = ["GF_Casa", "GC_Casa", "Forma_Casa", "GF_Fora", "GC_Fora", "Forma_Fora", "Resultado_Real"]
    with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colunas)
        writer.writeheader()
        writer.writerows(linhas)

    print(f"\nDataset gerado: {len(linhas)} linhas -> '{ARQUIVO_SAIDA}'")

    dist = {}
    for l in linhas:
        dist[l["Resultado_Real"]] = dist.get(l["Resultado_Real"], 0) + 1
    total = len(linhas)
    print("Distribuicao:")
    for k, v in sorted(dist.items()):
        print(f"  {k}: {v} ({v / total * 100:.1f}%)")

    import os
    if os.path.exists("cerebro_bot.joblib"):
        print(f"\nApague 'cerebro_bot.joblib' para forcar retreino com os novos dados.")


if __name__ == "__main__":
    gerar_dataset()
