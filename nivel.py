import os
import json
import datetime

import config as cfg

_DEFAULT = {
    "nivel": 5.0,
    "total_previsoes": 0,
    "acertos": 0,
    "historico": [],
}


def carregar_nivel():
    if not os.path.exists(cfg.NIVEL_PATH):
        return dict(_DEFAULT)
    try:
        with open(cfg.NIVEL_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
        for k, v in _DEFAULT.items():
            dados.setdefault(k, v)
        return dados
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT)


def _salvar(dados):
    with open(cfg.NIVEL_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def obter_nivel():
    dados = carregar_nivel()
    total = dados["total_previsoes"]
    return {
        "nivel": round(dados["nivel"], 1),
        "total": total,
        "acertos": dados["acertos"],
        "win_rate": round(dados["acertos"] / total * 100, 1) if total > 0 else 0.0,
    }


def atualizar_nivel(jogo_str, acertou, confianca):
    dados = carregar_nivel()

    if acertou:
        delta = 0.2 if confianca >= 0.70 else (0.15 if confianca >= 0.50 else 0.1)
    else:
        delta = -0.25 if confianca >= 0.70 else (-0.15 if confianca >= 0.50 else -0.1)

    dados["nivel"] = max(0.0, min(10.0, dados["nivel"] + delta))
    dados["total_previsoes"] += 1
    if acertou:
        dados["acertos"] += 1

    dados["historico"].append({
        "data": datetime.date.today().isoformat(),
        "jogo": jogo_str,
        "acertou": acertou,
        "confianca": round(confianca, 3),
        "delta": round(delta, 3),
        "nivel_apos": round(dados["nivel"], 2),
    })

    _salvar(dados)
    return dados["nivel"]
