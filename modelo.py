import os
import datetime
import numpy as np
import pandas as pd
import joblib
from scipy.stats import poisson

import config as cfg
import api_football as fb

FEATURES = ["GF_Casa", "GC_Casa", "Forma_Casa", "GF_Fora", "GC_Fora", "Forma_Fora"]


# ---------------------------------------------------------------------------
# Treino do modelo
# ---------------------------------------------------------------------------
def treinar_modelo():
    if os.path.exists(cfg.MODELO_PATH):
        modelo, scaler = joblib.load(cfg.MODELO_PATH)
        return modelo, scaler, 5000, "MLP"

    if not os.path.exists(cfg.DATASET_PATH):
        return None, None, 0, ""

    from sklearn.preprocessing import StandardScaler
    from sklearn.neural_network import MLPClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    df = pd.read_csv(cfg.DATASET_PATH)
    if len(df) < 20:
        return None, None, 0, ""

    X = df[FEATURES]
    y = df["Resultado_Real"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    modelo = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=1000, random_state=42)
    modelo.fit(X_train_s, y_train)

    preds = modelo.predict(X_test_s)
    acuracia = accuracy_score(y_test, preds) * 100

    joblib.dump((modelo, scaler), cfg.MODELO_PATH)

    return modelo, scaler, len(df), "MLP"


# ---------------------------------------------------------------------------
# Poisson
# ---------------------------------------------------------------------------
def calcular_poisson(gf_casa, gc_fora, gf_fora, gc_casa):
    lambda_casa = max((gf_casa * gc_fora) / cfg.MEDIA_GOLS_REFERENCIA, 0.35)
    lambda_fora = max((gf_fora * gc_casa) / cfg.MEDIA_GOLS_REFERENCIA, 0.35)

    prob_casa = prob_empate = prob_fora = 0.0
    for gc in range(7):
        for gf in range(7):
            prob = poisson.pmf(gc, lambda_casa) * poisson.pmf(gf, lambda_fora)
            if gc > gf:
                prob_casa += prob
            elif gc == gf:
                prob_empate += prob
            else:
                prob_fora += prob

    return lambda_casa, lambda_fora, prob_casa, prob_empate, prob_fora


def estimar_escanteios(stats_casa, stats_fora):
    tendencia = stats_casa["GF_Media"] + stats_fora["GF_Media"]
    return round(4.0 + tendencia * 2.0, 1)


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
# Previsao (retorna dict em vez de printar)
# ---------------------------------------------------------------------------
def realizar_previsao(time_casa, time_fora, modelo, scaler, n_amostras, nome_modelo):
    stats_casa, fonte_casa, id_casa = fb.obter_dados_time(time_casa)
    stats_fora, fonte_fora, id_fora = fb.obter_dados_time(time_fora)

    fixture_info = None
    if id_casa is not None and id_fora is not None:
        try:
            fixture_info = fb.localizar_jogo_copa(id_casa, id_fora)
        except fb.FootballAPIError:
            pass

    lambda_casa, lambda_fora, p_casa, p_emp, p_fora = calcular_poisson(
        stats_casa["GF_Media"], stats_fora["GC_Media"],
        stats_fora["GF_Media"], stats_casa["GC_Media"],
    )
    prob_poisson = (p_casa, p_emp, p_fora)

    modelo_usado = "Poisson Puro"
    peso_ml = 0.0
    prob_final = prob_poisson

    if modelo is not None and scaler is not None:
        features = np.array([[
            stats_casa["GF_Media"], stats_casa["GC_Media"],
            stats_casa.get("Forma_Media", 1.5),
            stats_fora["GF_Media"], stats_fora["GC_Media"],
            stats_fora.get("Forma_Media", 1.5),
        ]])
        features_s = scaler.transform(features)
        prob_array = modelo.predict_proba(features_s)[0]
        prob_dict = dict(zip(modelo.classes_, prob_array))
        prob_ml = (
            prob_dict.get("CASA", p_casa),
            prob_dict.get("EMPATE", p_emp),
            prob_dict.get("FORA", p_fora),
        )
        peso_ml = peso_modelo_ia(n_amostras, nome_modelo)
        prob_final = blend_probabilidades(prob_poisson, prob_ml, peso_ml)
        modelo_usado = f"Poisson + {nome_modelo} (blend)"

    escanteios = estimar_escanteios(stats_casa, stats_fora)
    p_c, p_e, p_f = prob_final

    resultado = {
        "time_casa": time_casa,
        "time_fora": time_fora,
        "prob_casa": p_c,
        "prob_empate": p_e,
        "prob_fora": p_f,
        "xg_casa": round(lambda_casa, 2),
        "xg_fora": round(lambda_fora, 2),
        "escanteios": escanteios,
        "modelo_usado": modelo_usado,
        "peso_ml": peso_ml,
        "fonte_casa": fonte_casa,
        "fonte_fora": fonte_fora,
        "stats_casa": stats_casa,
        "stats_fora": stats_fora,
        "fixture_info": fixture_info,
    }

    salvar_previsao_excel(resultado)
    return resultado


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
        "Escanteios Previstos": r["escanteios"],
        "Modelo Utilizado": r["modelo_usado"],
        "Peso Modelo IA (%)": round(r["peso_ml"] * 100, 1),
        "GF_Media_Casa": r["stats_casa"]["GF_Media"],
        "GC_Media_Casa": r["stats_casa"]["GC_Media"],
        "Forma_Casa": r["stats_casa"].get("Forma_Media", np.nan),
        "GF_Media_Fora": r["stats_fora"]["GF_Media"],
        "GC_Media_Fora": r["stats_fora"]["GC_Media"],
        "Forma_Fora": r["stats_fora"].get("Forma_Media", np.nan),
        "Gols Real Casa": np.nan,
        "Gols Real Fora": np.nan,
        "Resultado Real": np.nan,
        "Status Previsao": np.nan,
    }

    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    df.to_excel(cfg.EXCEL_PATH, index=False)


# ---------------------------------------------------------------------------
# Fechamento de resultados
# ---------------------------------------------------------------------------
def _classificar(df, idx, gols_casa, gols_fora):
    res_real = "CASA" if gols_casa > gols_fora else ("EMPATE" if gols_casa == gols_fora else "FORA")
    p_c = df.at[idx, "Prob Casa (%)"]
    p_e = df.at[idx, "Prob Empate (%)"]
    p_f = df.at[idx, "Prob Fora (%)"]
    maior = max(p_c, p_e, p_f)
    palpite = "CASA" if maior == p_c else ("EMPATE" if maior == p_e else "FORA")

    df.at[idx, "Gols Real Casa"] = gols_casa
    df.at[idx, "Gols Real Fora"] = gols_fora
    df.at[idx, "Resultado Real"] = res_real
    df.at[idx, "Status Previsao"] = "ACERTOU" if palpite == res_real else "ERROU"
    return res_real


def fechar_resultados(callback_log=None):
    """
    Fecha resultados automaticamente via API.
    Retorna (mensagens: list[str], pendentes_manuais: list[dict]).
    pendentes_manuais = [{"idx": int, "id": int, "casa": str, "fora": str}, ...]
    """
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
            _log(f"ID {row['ID']}: erro ao consultar — {e}")
            continue

        if resultado["status"] in fb.STATUS_FINALIZADOS:
            _classificar(df, idx, resultado["gols_casa"], resultado["gols_fora"])
            _log(f"ID {row['ID']}: {row['Equipa Casa']} {resultado['gols_casa']} x "
                 f"{resultado['gols_fora']} {row['Equipa Fora']} — fechado automaticamente.")
            houve_alteracao = True
        elif resultado["status"] in fb.STATUS_CANCELADOS:
            _log(f"ID {row['ID']}: jogo cancelado/suspenso ({resultado['status']}).")
        else:
            _log(f"ID {row['ID']}: ainda nao terminou ({resultado['status']}).")

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

    return log, manuais


def fechar_resultado_manual(idx, gols_casa, gols_fora):
    df = pd.read_excel(cfg.EXCEL_PATH)
    for col in ["Resultado Real", "Status Previsao"]:
        df[col] = df[col].astype(object)
    _classificar(df, idx, gols_casa, gols_fora)
    df.to_excel(cfg.EXCEL_PATH, index=False)
