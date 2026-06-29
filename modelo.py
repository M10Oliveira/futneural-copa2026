import os
import datetime
import numpy as np
import pandas as pd
import joblib
from scipy.stats import poisson

import config as cfg
import api_football as fb
import nivel

FEATURES = [
    "GF_Casa", "GC_Casa", "Forma_Casa", "Escanteios_Media_Casa", "Cartoes_Media_Casa",
    "GF_Fora", "GC_Fora", "Forma_Fora", "Escanteios_Media_Fora", "Cartoes_Media_Fora",
]


# ---------------------------------------------------------------------------
# Treino do modelo
# ---------------------------------------------------------------------------
def treinar_modelo():
    if os.path.exists(cfg.MODELO_PATH):
        modelo, scaler = joblib.load(cfg.MODELO_PATH)
        n = len(pd.read_csv(cfg.DATASET_PATH)) if os.path.exists(cfg.DATASET_PATH) else 0
        return modelo, scaler, n, "MLP"

    if not os.path.exists(cfg.DATASET_PATH):
        return None, None, 0, ""

    from sklearn.preprocessing import StandardScaler
    from sklearn.neural_network import MLPClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    df = pd.read_csv(cfg.DATASET_PATH)
    if len(df) < 20:
        return None, None, 0, ""

    X = df[FEATURES].fillna({
        "Escanteios_Media_Casa": 4.5, "Cartoes_Media_Casa": 2.0,
        "Escanteios_Media_Fora": 4.5, "Cartoes_Media_Fora": 2.0,
    })
    y = df["Resultado_Real"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=0
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    modelo = MLPClassifier(hidden_layer_sizes=(128, 64, 32), max_iter=1500, random_state=42)
    modelo.fit(X_train_s, y_train)

    joblib.dump((modelo, scaler), cfg.MODELO_PATH)
    return modelo, scaler, len(df), "MLP"


def retreinar_modelo(tentativas=10, callback=None):
    import random
    from sklearn.preprocessing import StandardScaler
    from sklearn.neural_network import MLPClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    if not os.path.exists(cfg.DATASET_PATH):
        return None, "Sem dataset para treinar."

    df = pd.read_csv(cfg.DATASET_PATH)
    if len(df) < 20:
        return None, f"Dataset muito pequeno ({len(df)} linhas, minimo 20)."

    X = df[FEATURES].fillna({
        "Escanteios_Media_Casa": 4.5, "Cartoes_Media_Casa": 2.0,
        "Escanteios_Media_Fora": 4.5, "Cartoes_Media_Fora": 2.0,
    })
    y = df["Resultado_Real"]

    # Split FIXO para todos: mesmo treino, mesmo teste, comparacao justa
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=0
    )

    acc_atual = 0.0
    if os.path.exists(cfg.MODELO_PATH):
        try:
            modelo_atual, scaler_atual = joblib.load(cfg.MODELO_PATH)
            X_test_s = scaler_atual.transform(X_test)
            preds_atual = modelo_atual.predict(X_test_s)
            acc_atual = accuracy_score(y_test, preds_atual) * 100
        except Exception:
            pass

    melhor_acc = acc_atual
    melhor_modelo = None
    melhor_scaler = None
    resultados = []

    if callback:
        callback(f"Acuracia atual: {acc_atual:.1f}% (so salva se superar)")

    scaler_base = StandardScaler()
    X_train_s = scaler_base.fit_transform(X_train)
    X_test_s = scaler_base.transform(X_test)

    for i in range(tentativas):
        seed = random.randint(1, 99999)

        modelo = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            max_iter=1500,
            random_state=seed,
        )
        modelo.fit(X_train_s, y_train)

        preds = modelo.predict(X_test_s)
        acc = accuracy_score(y_test, preds) * 100

        resultados.append(f"Tentativa {i+1}: {acc:.1f}% (seed {seed})")
        if callback:
            callback(f"Tentativa {i+1}/{tentativas}: {acc:.1f}%")

        if acc > melhor_acc:
            melhor_acc = acc
            melhor_modelo = modelo
            melhor_scaler = scaler_base

    resumo = "\n".join(resultados)

    if melhor_modelo:
        joblib.dump((melhor_modelo, melhor_scaler), cfg.MODELO_PATH)
        resumo += f"\n\nNovo recorde: {melhor_acc:.1f}% — modelo salvo ({len(df)} amostras)"
    else:
        resumo += (f"\n\nNenhuma tentativa superou o modelo atual ({acc_atual:.1f}%). "
                   f"Modelo anterior mantido.")

    ret = (melhor_modelo, melhor_scaler, len(df), "MLP") if melhor_modelo else None
    return ret, resumo


# ---------------------------------------------------------------------------
# Poisson — retorna lambdas, probs 1X2 e matriz de placares
# ---------------------------------------------------------------------------
def calcular_poisson(gf_casa, gc_fora, gf_fora, gc_casa, max_gols=12):
    lambda_casa = max((gf_casa * gc_fora) / cfg.MEDIA_GOLS_REFERENCIA, 0.35)
    lambda_fora = max((gf_fora * gc_casa) / cfg.MEDIA_GOLS_REFERENCIA, 0.35)
    # Teto para evitar distorcoes com poucos jogos (ex: 7x1 num unico jogo)
    lambda_casa = min(lambda_casa, 4.5)
    lambda_fora = min(lambda_fora, 4.5)

    matriz = np.zeros((max_gols, max_gols))
    for i in range(max_gols):
        for j in range(max_gols):
            matriz[i][j] = poisson.pmf(i, lambda_casa) * poisson.pmf(j, lambda_fora)

    prob_casa = prob_empate = prob_fora = 0.0
    for i in range(max_gols):
        for j in range(max_gols):
            if i > j:
                prob_casa += matriz[i][j]
            elif i == j:
                prob_empate += matriz[i][j]
            else:
                prob_fora += matriz[i][j]

    # Renormaliza para garantir que soma 100%
    total = prob_casa + prob_empate + prob_fora
    if total > 0:
        prob_casa /= total
        prob_empate /= total
        prob_fora /= total

    return lambda_casa, lambda_fora, prob_casa, prob_empate, prob_fora, matriz


# ---------------------------------------------------------------------------
# Mercados de aposta (derivados da matriz de Poisson)
# ---------------------------------------------------------------------------
def calcular_mercados(lambda_casa, lambda_fora, matriz, prob_casa, prob_empate, prob_fora,
                      stats_casa, stats_fora):
    max_gols = matriz.shape[0]
    mercados = {}

    # --- Over/Under gols ---
    for linha in [0.5, 1.5, 2.5, 3.5, 4.5]:
        over = 0.0
        for i in range(max_gols):
            for j in range(max_gols):
                if i + j > linha:
                    over += matriz[i][j]
        mercados[f"over_{linha}"] = round(over, 4)
        mercados[f"under_{linha}"] = round(1 - over, 4)

    # --- BTTS (Ambas Marcam) ---
    btts = 0.0
    for i in range(1, max_gols):
        for j in range(1, max_gols):
            btts += matriz[i][j]
    mercados["btts_sim"] = round(btts, 4)
    mercados["btts_nao"] = round(1 - btts, 4)

    # --- Chance Dupla ---
    mercados["chance_1x"] = round(prob_casa + prob_empate, 4)
    mercados["chance_x2"] = round(prob_empate + prob_fora, 4)
    mercados["chance_12"] = round(prob_casa + prob_fora, 4)

    # --- Placar exato (top 8) ---
    placares = []
    for i in range(max_gols):
        for j in range(max_gols):
            if matriz[i][j] > 0.005:
                placares.append((f"{i}x{j}", round(matriz[i][j], 4)))
    placares.sort(key=lambda x: x[1], reverse=True)
    mercados["placares_exatos"] = placares[:8]

    # --- Resultado 1o Tempo (Poisson com lambda/2) ---
    lc_ht = lambda_casa / 2
    lf_ht = lambda_fora / 2
    ht_casa = ht_empate = ht_fora = 0.0
    for i in range(5):
        for j in range(5):
            p = poisson.pmf(i, lc_ht) * poisson.pmf(j, lf_ht)
            if i > j:
                ht_casa += p
            elif i == j:
                ht_empate += p
            else:
                ht_fora += p
    ht_total = ht_casa + ht_empate + ht_fora
    if ht_total > 0:
        ht_casa /= ht_total
        ht_empate /= ht_total
        ht_fora /= ht_total
    mercados["ht_casa"] = round(ht_casa, 4)
    mercados["ht_empate"] = round(ht_empate, 4)
    mercados["ht_fora"] = round(ht_fora, 4)

    # --- Escanteios (dados reais quando disponíveis, senao heuristica) ---
    esc_casa = stats_casa.get("Escanteios_Media")
    esc_fora = stats_fora.get("Escanteios_Media")
    if esc_casa and esc_fora:
        lambda_escanteios = esc_casa + esc_fora
    else:
        ataque_total = stats_casa["GF_Media"] + stats_fora["GF_Media"]
        lambda_escanteios = cfg.MEDIA_ESCANTEIOS_BASE + (ataque_total - 2.0) * 1.5
    lambda_escanteios = max(lambda_escanteios, 6.0)
    mercados["escanteios_esperados"] = round(lambda_escanteios, 1)

    for linha in [7.5, 8.5, 9.5, 10.5, 11.5]:
        prob_over = 1 - sum(poisson.pmf(k, lambda_escanteios) for k in range(int(linha) + 1))
        mercados[f"escanteios_over_{linha}"] = round(prob_over, 4)

    # --- Cartoes (dados reais quando disponíveis, senao heuristica) ---
    cart_casa = stats_casa.get("Cartoes_Media")
    cart_fora = stats_fora.get("Cartoes_Media")
    if cart_casa and cart_fora:
        lambda_cartoes = cart_casa + cart_fora
    else:
        defesa = stats_casa["GC_Media"] + stats_fora["GC_Media"]
        lambda_cartoes = cfg.MEDIA_CARTOES_BASE + (defesa - 2.0) * 0.8
        forma_media = (stats_casa.get("Forma_Media", 1.5) + stats_fora.get("Forma_Media", 1.5)) / 2
        if forma_media < 1.2:
            lambda_cartoes += 0.5
    lambda_cartoes = max(lambda_cartoes, 2.5)
    mercados["cartoes_esperados"] = round(lambda_cartoes, 1)

    for linha in [2.5, 3.5, 4.5, 5.5]:
        prob_over = 1 - sum(poisson.pmf(k, lambda_cartoes) for k in range(int(linha) + 1))
        mercados[f"cartoes_over_{linha}"] = round(prob_over, 4)

    # --- Gols de cada time ---
    for linha in [0.5, 1.5, 2.5]:
        over_casa = 1 - sum(poisson.pmf(k, lambda_casa) for k in range(int(linha) + 1))
        over_fora = 1 - sum(poisson.pmf(k, lambda_fora) for k in range(int(linha) + 1))
        mercados[f"gols_casa_over_{linha}"] = round(over_casa, 4)
        mercados[f"gols_fora_over_{linha}"] = round(over_fora, 4)

    return mercados


# ---------------------------------------------------------------------------
# Blend Poisson + ML
# ---------------------------------------------------------------------------
def peso_modelo_ia(n_amostras, nome_modelo):
    if "MLP" in nome_modelo or "Rede" in nome_modelo:
        return min(0.75, n_amostras / 150)
    if "Logistic" in nome_modelo or "Regressao" in nome_modelo:
        return min(0.45, n_amostras / 80)
    return 0.0


def blend_probabilidades(prob_poisson, prob_ml, peso_ml):
    combinado = tuple(
        peso_ml * ml + (1 - peso_ml) * po
        for po, ml in zip(prob_poisson, prob_ml)
    )
    soma = sum(combinado)
    return tuple(p / soma for p in combinado)


# ---------------------------------------------------------------------------
# Previsao completa (retorna dict com TODOS os mercados)
# ---------------------------------------------------------------------------
def realizar_previsao(time_casa, time_fora, modelo_ml, scaler, n_amostras, nome_modelo):
    stats_casa, fonte_casa, id_casa = fb.obter_dados_time(time_casa)
    stats_fora, fonte_fora, id_fora = fb.obter_dados_time(time_fora)

    fixture_info = None
    if id_casa is not None and id_fora is not None:
        try:
            fixture_info = fb.localizar_jogo_copa(id_casa, id_fora)
        except fb.FootballAPIError:
            pass

    lambda_casa, lambda_fora, p_casa, p_emp, p_fora, matriz = calcular_poisson(
        stats_casa["GF_Media"], stats_fora["GC_Media"],
        stats_fora["GF_Media"], stats_casa["GC_Media"],
    )
    prob_poisson = (p_casa, p_emp, p_fora)

    modelo_usado = "Poisson Puro"
    peso_ml = 0.0
    prob_final = prob_poisson

    if modelo_ml is not None and scaler is not None:
        features = np.array([[
            stats_casa["GF_Media"], stats_casa["GC_Media"],
            stats_casa.get("Forma_Media", 1.5),
            stats_casa.get("Escanteios_Media", 4.5),
            stats_casa.get("Cartoes_Media", 2.0),
            stats_fora["GF_Media"], stats_fora["GC_Media"],
            stats_fora.get("Forma_Media", 1.5),
            stats_fora.get("Escanteios_Media", 4.5),
            stats_fora.get("Cartoes_Media", 2.0),
        ]])
        features_s = scaler.transform(features)
        prob_array = modelo_ml.predict_proba(features_s)[0]
        prob_dict = dict(zip(modelo_ml.classes_, prob_array))
        prob_ml = (
            prob_dict.get("CASA", p_casa),
            prob_dict.get("EMPATE", p_emp),
            prob_dict.get("FORA", p_fora),
        )
        peso_ml = peso_modelo_ia(n_amostras, nome_modelo)
        prob_final = blend_probabilidades(prob_poisson, prob_ml, peso_ml)
        modelo_usado = f"Poisson + {nome_modelo} (blend)"

    p_c, p_e, p_f = prob_final

    mercados = calcular_mercados(
        lambda_casa, lambda_fora, matriz, p_c, p_e, p_f,
        stats_casa, stats_fora,
    )

    info_nivel = nivel.obter_nivel()

    resultado = {
        "time_casa": time_casa,
        "time_fora": time_fora,
        "prob_casa": p_c,
        "prob_empate": p_e,
        "prob_fora": p_f,
        "xg_casa": round(lambda_casa, 2),
        "xg_fora": round(lambda_fora, 2),
        "modelo_usado": modelo_usado,
        "peso_ml": peso_ml,
        "fonte_casa": fonte_casa,
        "fonte_fora": fonte_fora,
        "stats_casa": stats_casa,
        "stats_fora": stats_fora,
        "fixture_info": fixture_info,
        "mercados": mercados,
        "nivel": info_nivel,
    }

    resultado["explicacao"] = gerar_explicacao(resultado)

    salvar_previsao_excel(resultado)
    return resultado


# ---------------------------------------------------------------------------
# Previsao Copa 2026 (usa APENAS dados do torneio atual, Poisson puro)
# ---------------------------------------------------------------------------
def _resolver_nome_copa(nome):
    stats = fb.obter_estatisticas_copa(nome)
    if stats:
        return nome, stats
    traduzido = fb._traduzir_nome_groq(nome)
    if traduzido and traduzido.lower() != nome.lower():
        stats = fb.obter_estatisticas_copa(traduzido)
        if stats:
            return traduzido, stats
    return nome, None


def realizar_previsao_copa(time_casa, time_fora):
    nome_casa, stats_casa = _resolver_nome_copa(time_casa)
    nome_fora, stats_fora = _resolver_nome_copa(time_fora)

    if not stats_casa:
        raise RuntimeError(
            f"'{time_casa}' nao tem jogos registrados na Copa 2026. "
            f"Registre os resultados na aba 'Jogos da Copa'."
        )
    if not stats_fora:
        raise RuntimeError(
            f"'{time_fora}' nao tem jogos registrados na Copa 2026. "
            f"Registre os resultados na aba 'Jogos da Copa'."
        )
    time_casa, time_fora = nome_casa, nome_fora

    fonte_casa = f"Copa 2026 ({stats_casa['Jogos_Analisados']} jogos)"
    fonte_fora = f"Copa 2026 ({stats_fora['Jogos_Analisados']} jogos)"

    lambda_casa, lambda_fora, p_c, p_e, p_f, matriz = calcular_poisson(
        stats_casa["GF_Media"], stats_fora["GC_Media"],
        stats_fora["GF_Media"], stats_casa["GC_Media"],
    )

    mercados = calcular_mercados(
        lambda_casa, lambda_fora, matriz, p_c, p_e, p_f,
        stats_casa, stats_fora,
    )

    info_nivel = nivel.obter_nivel()

    resultado = {
        "time_casa": time_casa,
        "time_fora": time_fora,
        "prob_casa": p_c,
        "prob_empate": p_e,
        "prob_fora": p_f,
        "xg_casa": round(lambda_casa, 2),
        "xg_fora": round(lambda_fora, 2),
        "modelo_usado": "Poisson Copa 2026",
        "peso_ml": 0.0,
        "fonte_casa": fonte_casa,
        "fonte_fora": fonte_fora,
        "stats_casa": stats_casa,
        "stats_fora": stats_fora,
        "fixture_info": None,
        "mercados": mercados,
        "nivel": info_nivel,
    }

    resultado["explicacao"] = gerar_explicacao(resultado)

    salvar_previsao_excel(resultado)
    return resultado


# ---------------------------------------------------------------------------
# Formatar previsao como texto (pronto para Telegram)
# ---------------------------------------------------------------------------
def formatar_previsao_texto(r):
    m = r["mercados"]
    n = r["nivel"]

    linhas = [
        f"{r['time_casa'].upper()} x {r['time_fora'].upper()}",
        f"",
        f"RESULTADO (1X2)",
        f"  Casa: {r['prob_casa']*100:.1f}%  |  Empate: {r['prob_empate']*100:.1f}%  |  Fora: {r['prob_fora']*100:.1f}%",
        f"  xG: {r['xg_casa']} - {r['xg_fora']}",
        f"",
        f"CHANCE DUPLA",
        f"  1X: {m['chance_1x']*100:.1f}%  |  X2: {m['chance_x2']*100:.1f}%  |  12: {m['chance_12']*100:.1f}%",
        f"",
        f"OVER/UNDER GOLS",
        f"  Over 0.5: {m['over_0.5']*100:.1f}%  |  Over 1.5: {m['over_1.5']*100:.1f}%",
        f"  Over 2.5: {m['over_2.5']*100:.1f}%  |  Over 3.5: {m['over_3.5']*100:.1f}%",
        f"",
        f"AMBAS MARCAM (BTTS)",
        f"  Sim: {m['btts_sim']*100:.1f}%  |  Nao: {m['btts_nao']*100:.1f}%",
        f"",
        f"GOLS POR EQUIPE",
        f"  {r['time_casa']}: Over 0.5 {m['gols_casa_over_0.5']*100:.0f}%  |  Over 1.5 {m['gols_casa_over_1.5']*100:.0f}%",
        f"  {r['time_fora']}: Over 0.5 {m['gols_fora_over_0.5']*100:.0f}%  |  Over 1.5 {m['gols_fora_over_1.5']*100:.0f}%",
        f"",
        f"1o TEMPO",
        f"  Casa: {m['ht_casa']*100:.1f}%  |  Empate: {m['ht_empate']*100:.1f}%  |  Fora: {m['ht_fora']*100:.1f}%",
        f"",
        f"PLACAR EXATO (mais provaveis)",
    ]

    for placar, prob in m["placares_exatos"]:
        linhas.append(f"  {placar}: {prob*100:.1f}%")

    linhas.extend([
        f"",
        f"ESCANTEIOS (~{m['escanteios_esperados']})",
        f"  Over 8.5: {m.get('escanteios_over_8.5', 0)*100:.0f}%  |  "
        f"Over 9.5: {m.get('escanteios_over_9.5', 0)*100:.0f}%  |  "
        f"Over 10.5: {m.get('escanteios_over_10.5', 0)*100:.0f}%",
        f"",
        f"CARTOES (~{m['cartoes_esperados']})",
        f"  Over 3.5: {m.get('cartoes_over_3.5', 0)*100:.0f}%  |  "
        f"Over 4.5: {m.get('cartoes_over_4.5', 0)*100:.0f}%  |  "
        f"Over 5.5: {m.get('cartoes_over_5.5', 0)*100:.0f}%",
        f"",
        f"ANALISE",
        f"  {r.get('explicacao', '')}",
        f"",
        f"Modelo: {r['modelo_usado']}",
        f"Nivel Bot: {n['nivel']}/10  ({n['win_rate']}% acerto em {n['total']} jogos)",
        f"Fonte: {r['fonte_casa']} | {r['fonte_fora']}",
    ])

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Explicacao humanizada (Groq reescreve dados tecnicos em linguagem natural)
# ---------------------------------------------------------------------------
def _gerar_resumo_tecnico(r):
    m = r["mercados"]
    sc = r["stats_casa"]
    sf = r["stats_fora"]
    casa = r["time_casa"]
    fora = r["time_fora"]

    pontos = []

    if r["prob_casa"] > r["prob_fora"] and r["prob_casa"] > r["prob_empate"]:
        favorito, prob = casa, r["prob_casa"]
    elif r["prob_fora"] > r["prob_casa"] and r["prob_fora"] > r["prob_empate"]:
        favorito, prob = fora, r["prob_fora"]
    else:
        favorito, prob = "empate", r["prob_empate"]
    pontos.append(f"Favorito: {favorito} ({prob*100:.1f}%).")

    pontos.append(f"{casa} marca em media {sc['GF_Media']} gols/jogo e sofre {sc['GC_Media']}.")
    pontos.append(f"{fora} marca em media {sf['GF_Media']} gols/jogo e sofre {sf['GC_Media']}.")

    forma_casa = sc.get("Forma_Media", 1.5)
    forma_fora = sf.get("Forma_Media", 1.5)
    if forma_casa >= 2.5:
        pontos.append(f"{casa} vem em otima fase ({forma_casa:.1f} pts/jogo).")
    elif forma_casa <= 1.0:
        pontos.append(f"{casa} vem em fase ruim ({forma_casa:.1f} pts/jogo).")
    if forma_fora >= 2.5:
        pontos.append(f"{fora} vem em otima fase ({forma_fora:.1f} pts/jogo).")
    elif forma_fora <= 1.0:
        pontos.append(f"{fora} vem em fase ruim ({forma_fora:.1f} pts/jogo).")

    pontos.append(f"xG esperado: {r['xg_casa']} x {r['xg_fora']}.")
    pontos.append(f"Over 2.5 gols: {m['over_2.5']*100:.0f}%. BTTS: {m['btts_sim']*100:.0f}%.")

    esc = m["escanteios_esperados"]
    cart = m["cartoes_esperados"]
    pontos.append(f"Escanteios esperados: ~{esc}. Cartoes esperados: ~{cart}.")

    if sc.get("Escanteios_Media"):
        pontos.append(f"{casa} tem media de {sc['Escanteios_Media']} escanteios/jogo.")
    if sf.get("Escanteios_Media"):
        pontos.append(f"{fora} tem media de {sf['Escanteios_Media']} escanteios/jogo.")
    if sc.get("Cartoes_Media"):
        pontos.append(f"{casa} recebe em media {sc['Cartoes_Media']} cartoes/jogo.")
    if sf.get("Cartoes_Media"):
        pontos.append(f"{fora} recebe em media {sf['Cartoes_Media']} cartoes/jogo.")

    top_placar = m["placares_exatos"][0] if m["placares_exatos"] else None
    if top_placar:
        pontos.append(f"Placar mais provavel: {top_placar[0]} ({top_placar[1]*100:.1f}%).")

    return " ".join(pontos)


def gerar_explicacao(r):
    resumo = _gerar_resumo_tecnico(r)

    if cfg.groq_client is None:
        return resumo

    contexto = ""
    if "Copa 2026" in r.get("modelo_usado", ""):
        contexto = (
            "CONTEXTO: esta previsao usa APENAS dados reais dos jogos da Copa "
            "do Mundo 2026 em andamento. Mencione isso na analise. "
        )

    prompt = (
        f"Voce e um analista de futebol. Reescreva os dados abaixo em um texto "
        f"natural e fluido em portugues (3-5 frases), como se estivesse explicando "
        f"a previsao para alguem que vai apostar. NAO invente informacoes que nao "
        f"estejam nos dados. NAO mencione nomes de jogadores. Use apenas os "
        f"numeros e fatos fornecidos. {contexto}\n\n"
        f"Jogo: {r['time_casa']} x {r['time_fora']}\n"
        f"Dados: {resumo}"
    )

    try:
        resposta = cfg.groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=300,
        )
        return resposta.choices[0].message.content.strip()
    except Exception:
        return resumo


# ---------------------------------------------------------------------------
# Excel I/O
# ---------------------------------------------------------------------------
def _inicializar_excel():
    if not os.path.exists(cfg.EXCEL_PATH):
        pd.DataFrame(columns=cfg.COLUNAS_EXCEL).to_excel(cfg.EXCEL_PATH, index=False)


def salvar_previsao_excel(r):
    _inicializar_excel()
    df = pd.read_excel(cfg.EXCEL_PATH)

    fixture_id = (
        r["fixture_info"]["fixture_id"] if r["fixture_info"] else np.nan
    )

    if not df.empty:
        if r["fixture_info"]:
            if not df[df["ID Fixture API"] == fixture_id].empty:
                return
        else:
            hoje = datetime.date.today().strftime("%Y-%m-%d")
            dup = df[
                (df["Equipa Casa"] == r["time_casa"])
                & (df["Equipa Fora"] == r["time_fora"])
                & (df["Data/Hora"].str.startswith(hoje, na=False))
            ]
            if not dup.empty:
                return

    m = r["mercados"]
    nova = {
        "ID": len(df) + 1,
        "Data/Hora": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Equipa Casa": r["time_casa"],
        "Equipa Fora": r["time_fora"],
        "ID Fixture API": fixture_id,
        "Fonte Dados": f"{r['fonte_casa']} | {r['fonte_fora']}",
        "xG Casa (Poisson)": r["xg_casa"],
        "xG Fora (Poisson)": r["xg_fora"],
        "Prob Casa (%)": round(r["prob_casa"] * 100, 1),
        "Prob Empate (%)": round(r["prob_empate"] * 100, 1),
        "Prob Fora (%)": round(r["prob_fora"] * 100, 1),
        "Escanteios Previstos": m["escanteios_esperados"],
        "Modelo Utilizado": r["modelo_usado"],
        "Peso Modelo IA (%)": round(r["peso_ml"] * 100, 1),
        "GF_Media_Casa": r["stats_casa"]["GF_Media"],
        "GC_Media_Casa": r["stats_casa"]["GC_Media"],
        "Forma_Casa": r["stats_casa"].get("Forma_Media", np.nan),
        "Escanteios_Media_Casa": r["stats_casa"].get("Escanteios_Media", 4.5),
        "Cartoes_Media_Casa": r["stats_casa"].get("Cartoes_Media", 2.0),
        "GF_Media_Fora": r["stats_fora"]["GF_Media"],
        "GC_Media_Fora": r["stats_fora"]["GC_Media"],
        "Forma_Fora": r["stats_fora"].get("Forma_Media", np.nan),
        "Escanteios_Media_Fora": r["stats_fora"].get("Escanteios_Media", 4.5),
        "Cartoes_Media_Fora": r["stats_fora"].get("Cartoes_Media", 2.0),
        "Gols Real Casa": np.nan,
        "Gols Real Fora": np.nan,
        "Resultado Real": np.nan,
        "Status Previsao": np.nan,
    }

    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    df.to_excel(cfg.EXCEL_PATH, index=False)


# ---------------------------------------------------------------------------
# Fechamento de resultados (com atualizacao de nivel)
# ---------------------------------------------------------------------------
def _adicionar_ao_dataset(df, idx, resultado_real, gols_casa=0, gols_fora=0):
    import csv
    row = df.loc[idx]
    esc_casa = row.get("Escanteios_Media_Casa", 4.5)
    esc_fora = row.get("Escanteios_Media_Fora", 4.5)
    cart_casa = row.get("Cartoes_Media_Casa", 2.0)
    cart_fora = row.get("Cartoes_Media_Fora", 2.0)
    nova_linha = {
        "GF_Casa": row.get("GF_Media_Casa", 1.5),
        "GC_Casa": row.get("GC_Media_Casa", 1.0),
        "Forma_Casa": row.get("Forma_Casa", 1.5),
        "Escanteios_Media_Casa": esc_casa,
        "Cartoes_Media_Casa": cart_casa,
        "GF_Fora": row.get("GF_Media_Fora", 1.5),
        "GC_Fora": row.get("GC_Media_Fora", 1.0),
        "Forma_Fora": row.get("Forma_Fora", 1.5),
        "Escanteios_Media_Fora": esc_fora,
        "Cartoes_Media_Fora": cart_fora,
        "Escanteios_Total": round(esc_casa + esc_fora),
        "Cartoes_Total": round(cart_casa + cart_fora),
        "Resultado_Real": resultado_real,
    }
    cabecalho = list(nova_linha.keys())
    existe = os.path.exists(cfg.DATASET_PATH)
    with open(cfg.DATASET_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cabecalho)
        if not existe:
            writer.writeheader()
        writer.writerow(nova_linha)


def _classificar(df, idx, gols_casa, gols_fora):
    res_real = "CASA" if gols_casa > gols_fora else ("EMPATE" if gols_casa == gols_fora else "FORA")
    p_c = df.at[idx, "Prob Casa (%)"]
    p_e = df.at[idx, "Prob Empate (%)"]
    p_f = df.at[idx, "Prob Fora (%)"]
    maior = max(p_c, p_e, p_f)
    palpite = "CASA" if maior == p_c else ("EMPATE" if maior == p_e else "FORA")
    acertou = palpite == res_real
    confianca = maior / 100.0

    df.at[idx, "Gols Real Casa"] = gols_casa
    df.at[idx, "Gols Real Fora"] = gols_fora
    df.at[idx, "Resultado Real"] = res_real
    _adicionar_ao_dataset(df, idx, res_real)
    df.at[idx, "Status Previsao"] = "ACERTOU" if acertou else "ERROU"

    jogo_str = f"{df.at[idx, 'Equipa Casa']} x {df.at[idx, 'Equipa Fora']}"
    nivel.atualizar_nivel(jogo_str, acertou, confianca)

    return res_real


def fechar_resultados(callback_log=None):
    log = []

    def _log(msg):
        log.append(msg)
        if callback_log:
            callback_log(msg)

    if not os.path.exists(cfg.EXCEL_PATH):
        _log("Ainda nao ha previsoes registadas.")
        return log, []

    df = pd.read_excel(cfg.EXCEL_PATH)
    for col in ["Resultado Real", "Status Previsao"]:
        df[col] = df[col].astype(object)

    pendentes = df[df["Resultado Real"].isna()]
    if pendentes.empty:
        _log("Nao ha previsoes pendentes.")
        return log, []

    houve_alteracao = False
    com_fixture = pendentes[pendentes["ID Fixture API"].notna()]
    sem_fixture = pendentes[pendentes["ID Fixture API"].isna()]

    for idx, row in com_fixture.iterrows():
        try:
            resultado = fb.obter_resultado_fixture(int(row["ID Fixture API"]))
        except fb.FootballAPIError as e:
            _log(f"ID {row['ID']}: erro — {e}")
            continue

        if resultado["status"] in fb.STATUS_FINALIZADOS:
            _classificar(df, idx, resultado["gols_casa"], resultado["gols_fora"])
            _log(f"ID {row['ID']}: {row['Equipa Casa']} {resultado['gols_casa']} x "
                 f"{resultado['gols_fora']} {row['Equipa Fora']} — fechado.")
            houve_alteracao = True
        elif resultado["status"] in fb.STATUS_CANCELADOS:
            _log(f"ID {row['ID']}: cancelado ({resultado['status']}).")
        else:
            _log(f"ID {row['ID']}: em andamento ({resultado['status']}).")

    manuais = []

    if not sem_fixture.empty and fb.chave_configurada():
        try:
            jogos_recentes = fb.listar_jogos_finalizados_recentes(dias=21)
        except fb.FootballAPIError:
            jogos_recentes = []

        for idx, row in sem_fixture.iterrows():
            try:
                casa = fb.buscar_id_time_com_traducao(row["Equipa Casa"])
                fora = fb.buscar_id_time_com_traducao(row["Equipa Fora"])
            except fb.FootballAPIError:
                casa = fora = None

            achou = False
            if casa and fora:
                ids_prev = {casa[0], fora[0]}
                for jogo in jogos_recentes:
                    if {jogo["id_casa"], jogo["id_fora"]} == ids_prev:
                        df.at[idx, "ID Fixture API"] = jogo["fixture_id"]
                        _classificar(df, idx, jogo["gols_casa"], jogo["gols_fora"])
                        _log(f"ID {row['ID']}: {row['Equipa Casa']} {jogo['gols_casa']} x "
                             f"{jogo['gols_fora']} {row['Equipa Fora']} — localizado e fechado.")
                        houve_alteracao = True
                        achou = True
                        break

            if not achou:
                manuais.append({
                    "idx": idx,
                    "id": row["ID"],
                    "casa": row["Equipa Casa"],
                    "fora": row["Equipa Fora"],
                })
    else:
        for idx, row in sem_fixture.iterrows():
            manuais.append({
                "idx": idx,
                "id": row["ID"],
                "casa": row["Equipa Casa"],
                "fora": row["Equipa Fora"],
            })

    if houve_alteracao:
        df.to_excel(cfg.EXCEL_PATH, index=False)
        _log("Ficheiro atualizado.")

    if manuais:
        _log(f"{len(manuais)} previsao(oes) precisam de placar manual.")

    n = nivel.obter_nivel()
    _log(f"Nivel do bot: {n['nivel']}/10 ({n['win_rate']}% acerto)")

    return log, manuais


def fechar_resultado_manual(id_previsao, gols_casa, gols_fora):
    df = pd.read_excel(cfg.EXCEL_PATH)
    for col in ["Resultado Real", "Status Previsao"]:
        df[col] = df[col].astype(object)
    match = df[df["ID"] == id_previsao]
    if match.empty:
        raise ValueError(f"Previsao ID {id_previsao} nao encontrada.")
    idx = match.index[0]
    _classificar(df, idx, gols_casa, gols_fora)
    df.to_excel(cfg.EXCEL_PATH, index=False)
