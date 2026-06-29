import json
import time
import datetime
import requests

import config as cfg

BASE_URL = "https://v3.football.api-sports.io"

STATUS_FINALIZADOS = {"FT", "AET", "PEN"}
STATUS_EM_ANDAMENTO = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
STATUS_NAO_INICIADO = {"NS", "TBD"}
STATUS_CANCELADOS = {"CANC", "ABD", "AWD", "WO", "SUSP", "PST"}


class FootballAPIError(Exception):
    pass


# ---------------------------------------------------------------------------
# Rate limiter (max 9 req/min para ficar seguro no limite de 10/min)
# ---------------------------------------------------------------------------
class _RateLimiter:
    def __init__(self, max_por_minuto=9):
        self._intervalo = 60.0 / max_por_minuto
        self._ultimo = 0.0

    def aguardar(self):
        agora = time.monotonic()
        espera = self._intervalo - (agora - self._ultimo)
        if espera > 0:
            time.sleep(espera)
        self._ultimo = time.monotonic()


_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# Cache em disco
# ---------------------------------------------------------------------------
def _carregar_cache():
    if not cfg.CACHE_PATH:
        return {"team_ids": {}, "team_stats": {}, "fixtures": {}}
    try:
        with open(cfg.CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        cache = {}
    cache.setdefault("team_ids", {})
    cache.setdefault("team_stats", {})
    cache.setdefault("fixtures", {})
    return cache


def _guardar_cache(cache):
    try:
        with open(cfg.CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _ttl_valido(entrada, horas):
    if not entrada or "timestamp" not in entrada:
        return False
    guardado = datetime.datetime.fromisoformat(entrada["timestamp"])
    return (datetime.datetime.now() - guardado) < datetime.timedelta(hours=horas)


# ---------------------------------------------------------------------------
# Requisicao HTTP
# ---------------------------------------------------------------------------
def chave_configurada():
    return bool(cfg.FOOTBALL_API_KEY)


def origem_chave():
    import os
    if os.environ.get("FOOTBALL_API_KEY", "").strip():
        return "variavel de ambiente"
    if cfg._cfg is not None and getattr(cfg._cfg, "FOOTBALL_API_KEY", "").strip():
        return "config_local.py"
    return None


def _requisitar(endpoint, params, tentativas=3):
    if not chave_configurada():
        raise FootballAPIError(
            "FOOTBALL_API_KEY nao configurada. Defina a variavel de ambiente "
            "ou preencha config_local.py."
        )

    _limiter.aguardar()

    headers = {"x-apisports-key": cfg.FOOTBALL_API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.RequestException as e:
            ultimo_erro = str(e)
            time.sleep(1.5 * tentativa)
            continue

        if resp.status_code == 429:
            raise FootballAPIError(
                "Cota diaria da API-Football esgotada (plano gratuito: 100 req/dia). "
                "Aguarde o reset (00:00 UTC) ou faca upgrade do plano."
            )
        if resp.status_code != 200:
            ultimo_erro = f"HTTP {resp.status_code}: {resp.text[:200]}"
            time.sleep(1.0 * tentativa)
            continue

        dados = resp.json()
        if dados.get("errors"):
            erros = dados["errors"]
            texto = str(erros).lower()
            if "rate" in texto and "limit" in texto:
                time.sleep(62)
                continue
            if "plan" in texto and "season" in texto:
                raise FootballAPIError(
                    f"Seu plano nao tem acesso a esta temporada: {erros}"
                )
            raise FootballAPIError(f"API-Football retornou erro: {erros}")

        return dados.get("response", [])

    raise FootballAPIError(f"Falha em '{endpoint}' apos {tentativas} tentativas: {ultimo_erro}")


# ---------------------------------------------------------------------------
# Status da conta
# ---------------------------------------------------------------------------
def consultar_status_conta():
    resposta = _requisitar("status", {})
    return resposta[0] if isinstance(resposta, list) and resposta else resposta


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------
def buscar_id_time(nome_time):
    cache = _carregar_cache()
    chave = nome_time.strip().lower()

    if chave in cache["team_ids"]:
        item = cache["team_ids"][chave]
        return tuple(item) if item else None

    termo = nome_time.strip()
    if len(termo) < 3:
        raise FootballAPIError("Nome do time precisa ter ao menos 3 letras.")

    resultado = _requisitar("teams", {"search": termo})

    escolhido = None
    if resultado:
        nacionais = [t for t in resultado if t.get("team", {}).get("national")]
        candidatos = nacionais or resultado
        melhor = min(candidatos, key=lambda t: abs(len(t["team"]["name"]) - len(termo)))
        escolhido = (melhor["team"]["id"], melhor["team"]["name"])

    cache["team_ids"][chave] = list(escolhido) if escolhido else None
    _guardar_cache(cache)
    return escolhido


def _traduzir_nome_groq(nome_time):
    if cfg.groq_client is None:
        return None
    prompt = (
        f"Qual e o nome oficial em ingles da selecao nacional de futebol "
        f"'{nome_time}', no formato usado pela FIFA (ex: 'Brasil' -> 'Brazil', "
        f"'Costa do Marfim' -> 'Ivory Coast')? "
        f'Responda APENAS em JSON: {{"nome_ingles": "..."}}. '
        f"Se o nome ja estiver em ingles, repita-o sem alteracoes."
    )
    try:
        resposta = cfg.groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
        )
        dados = json.loads(resposta.choices[0].message.content)
        return dados.get("nome_ingles", "").strip() or None
    except Exception:
        return None


def buscar_id_time_com_traducao(nome_time):
    encontrado = buscar_id_time(nome_time)
    if encontrado:
        return encontrado

    nome_traduzido = _traduzir_nome_groq(nome_time)
    if nome_traduzido and nome_traduzido.strip().lower() != nome_time.strip().lower():
        encontrado = buscar_id_time(nome_traduzido)
        if encontrado:
            return encontrado

    return None


def consultar_groq_fallback(nome_time):
    if cfg.groq_client is None:
        return None
    prompt = (
        f"Estime as medias de gols feitos (GF_Media) e sofridos (GC_Media) por jogo "
        f"da selecao '{nome_time}' em partidas recentes. Responda APENAS com JSON: "
        f'{{"GF_Media": 0.0, "GC_Media": 0.0}}'
    )
    try:
        resposta = cfg.groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
        )
        dados = json.loads(resposta.choices[0].message.content)
        dados["Forma_Media"] = 1.5
        dados["Jogos_Analisados"] = 0
        return dados
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Estatisticas de time (ultimos N jogos)
# ---------------------------------------------------------------------------
def obter_estatisticas_time(team_id, ultimos_n=10):
    cache = _carregar_cache()
    chave = str(team_id)
    if chave in cache["team_stats"] and _ttl_valido(cache["team_stats"][chave], 6):
        return cache["team_stats"][chave]["data"]

    ano_atual = datetime.date.today().year
    todos_fixtures = []

    for ano in [ano_atual, ano_atual - 1, ano_atual - 2]:
        try:
            resposta = _requisitar("fixtures", {"team": team_id, "season": ano})
            finalizados = [
                fx for fx in resposta
                if fx["fixture"]["status"]["short"] in STATUS_FINALIZADOS
            ]
            todos_fixtures.extend(finalizados)
            if len(todos_fixtures) >= ultimos_n:
                break
        except FootballAPIError:
            continue

    if not todos_fixtures:
        raise FootballAPIError(f"Nenhum jogo finalizado encontrado para o time {team_id}.")

    todos_fixtures.sort(key=lambda x: x["fixture"]["timestamp"], reverse=True)
    fixtures = todos_fixtures[:ultimos_n]

    gols_feitos, gols_sofridos, pontos = [], [], []
    for fx in fixtures:
        casa = fx["teams"]["home"]
        fora = fx["teams"]["away"]
        gc_raw = fx["goals"]["home"]
        gf_raw = fx["goals"]["away"]
        if gc_raw is None or gf_raw is None:
            continue
        if casa["id"] == team_id:
            gf, gc = gc_raw, gf_raw
        elif fora["id"] == team_id:
            gf, gc = gf_raw, gc_raw
        else:
            continue
        gols_feitos.append(gf)
        gols_sofridos.append(gc)
        pontos.append(3 if gf > gc else (1 if gf == gc else 0))

    if not gols_feitos:
        raise FootballAPIError(f"Dados de gols incompletos para o time {team_id}.")

    stats = {
        "GF_Media": round(sum(gols_feitos) / len(gols_feitos), 2),
        "GC_Media": round(sum(gols_sofridos) / len(gols_sofridos), 2),
        "Forma_Media": round(sum(pontos) / len(pontos), 2),
        "Jogos_Analisados": len(gols_feitos),
    }

    cache["team_stats"][chave] = {
        "timestamp": datetime.datetime.now().isoformat(),
        "data": stats,
    }
    _guardar_cache(cache)
    return stats


# ---------------------------------------------------------------------------
# Estatisticas da Copa 2026 (arquivo local — plano gratuito nao cobre 2026)
# ---------------------------------------------------------------------------
def _carregar_copa_csv():
    import csv
    import os
    if not os.path.exists(cfg.COPA_CSV_PATH):
        return []
    with open(cfg.COPA_CSV_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def registrar_resultado_copa(casa, fora, gols_casa, gols_fora,
                              escanteios_casa=0, escanteios_fora=0,
                              cartoes_casa=0, cartoes_fora=0):
    import csv
    import os
    cabecalho = [
        "Data", "Casa", "Fora", "Gols_Casa", "Gols_Fora",
        "Escanteios_Casa", "Escanteios_Fora", "Cartoes_Casa", "Cartoes_Fora",
    ]
    existe = os.path.exists(cfg.COPA_CSV_PATH)
    with open(cfg.COPA_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cabecalho)
        if not existe:
            writer.writeheader()
        writer.writerow({
            "Data": datetime.date.today().isoformat(),
            "Casa": casa.strip(),
            "Fora": fora.strip(),
            "Gols_Casa": int(gols_casa),
            "Gols_Fora": int(gols_fora),
            "Escanteios_Casa": int(escanteios_casa),
            "Escanteios_Fora": int(escanteios_fora),
            "Cartoes_Casa": int(cartoes_casa),
            "Cartoes_Fora": int(cartoes_fora),
        })


def obter_estatisticas_copa(nome_time):
    jogos = _carregar_copa_csv()
    if not jogos:
        return None

    nome = nome_time.strip().lower()
    gols_feitos, gols_sofridos, pontos = [], [], []
    escanteios, cartoes = [], []

    for j in jogos:
        casa = j["Casa"].strip().lower()
        fora = j["Fora"].strip().lower()
        try:
            g_casa = int(j["Gols_Casa"])
            g_fora = int(j["Gols_Fora"])
        except (ValueError, KeyError):
            continue

        if casa == nome:
            gf, gc = g_casa, g_fora
            esc = int(j.get("Escanteios_Casa", 0) or 0)
            cart = int(j.get("Cartoes_Casa", 0) or 0)
        elif fora == nome:
            gf, gc = g_fora, g_casa
            esc = int(j.get("Escanteios_Fora", 0) or 0)
            cart = int(j.get("Cartoes_Fora", 0) or 0)
        else:
            continue

        gols_feitos.append(gf)
        gols_sofridos.append(gc)
        pontos.append(3 if gf > gc else (1 if gf == gc else 0))
        if esc > 0:
            escanteios.append(esc)
        if cart > 0:
            cartoes.append(cart)

    if not gols_feitos:
        return None

    stats = {
        "GF_Media": round(sum(gols_feitos) / len(gols_feitos), 2),
        "GC_Media": round(sum(gols_sofridos) / len(gols_sofridos), 2),
        "Forma_Media": round(sum(pontos) / len(pontos), 2),
        "Jogos_Analisados": len(gols_feitos),
    }
    if escanteios:
        stats["Escanteios_Media"] = round(sum(escanteios) / len(escanteios), 1)
    if cartoes:
        stats["Cartoes_Media"] = round(sum(cartoes) / len(cartoes), 1)
    return stats


# ---------------------------------------------------------------------------
# Obter dados de um time (Copa 2026 local > API geral > Groq fallback)
# ---------------------------------------------------------------------------
def obter_dados_time(nome_time):
    stats_copa = obter_estatisticas_copa(nome_time)
    if stats_copa and stats_copa["Jogos_Analisados"] >= 1:
        fonte = f"Copa 2026 local ({stats_copa['Jogos_Analisados']} jogos reais)"
        team_id = None
        if chave_configurada():
            try:
                encontrado = buscar_id_time_com_traducao(nome_time)
                if encontrado:
                    team_id = encontrado[0]
            except FootballAPIError:
                pass
        return stats_copa, fonte, team_id

    if not chave_configurada():
        estimativa = consultar_groq_fallback(nome_time)
        if estimativa:
            return estimativa, "Estimativa IA (Groq) — sem API e sem dados Copa local", None
        raise RuntimeError(
            "Nenhuma fonte de dados disponivel. Configure FOOTBALL_API_KEY ou "
            "registre jogos da Copa em copa_2026_resultados.csv."
        )

    try:
        encontrado = buscar_id_time_com_traducao(nome_time)
        if not encontrado:
            raise FootballAPIError(f"Time '{nome_time}' nao encontrado na API-Football.")
        team_id, nome_oficial = encontrado
        stats = obter_estatisticas_time(team_id)
        fonte = f"API-Football ({stats['Jogos_Analisados']} jogos recentes) — {nome_oficial}"
        return stats, fonte, team_id
    except FootballAPIError as e:
        estimativa = consultar_groq_fallback(nome_time)
        if estimativa:
            return estimativa, "Estimativa IA (Groq) — API-Football indisponivel", None
        raise RuntimeError(f"Nao foi possivel obter dados para '{nome_time}': {e}")


# ---------------------------------------------------------------------------
# Fixtures da Copa do Mundo 2026
# ---------------------------------------------------------------------------
def localizar_jogo_copa(id_casa, id_fora):
    fixtures = _requisitar(
        "fixtures",
        {"league": cfg.LIGA_COPA_DO_MUNDO, "season": cfg.TEMPORADA_COPA, "team": id_casa},
    )

    candidatos = [
        fx for fx in fixtures
        if id_fora in (fx["teams"]["home"]["id"], fx["teams"]["away"]["id"])
    ]
    if not candidatos:
        return None

    agora = datetime.datetime.now(datetime.timezone.utc)

    def distancia(fx):
        data_jogo = datetime.datetime.fromisoformat(fx["fixture"]["date"])
        return abs((data_jogo - agora).total_seconds())

    escolhido = min(candidatos, key=distancia)
    return {
        "fixture_id": escolhido["fixture"]["id"],
        "data": escolhido["fixture"]["date"],
        "status": escolhido["fixture"]["status"]["short"],
        "gols_casa": escolhido["goals"]["home"],
        "gols_fora": escolhido["goals"]["away"],
    }


def obter_resultado_fixture(fixture_id):
    resultado = _requisitar("fixtures", {"id": fixture_id})
    if not resultado:
        raise FootballAPIError(f"Fixture {fixture_id} nao encontrado.")
    fx = resultado[0]
    return {
        "status": fx["fixture"]["status"]["short"],
        "gols_casa": fx["goals"]["home"],
        "gols_fora": fx["goals"]["away"],
    }


def obter_tabela_grupos():
    resposta = _requisitar(
        "standings",
        {"league": cfg.LIGA_COPA_DO_MUNDO, "season": cfg.TEMPORADA_COPA},
    )
    if not resposta:
        return []
    return resposta[0]["league"]["standings"]


def listar_jogos_finalizados_recentes(dias=21):
    hoje = datetime.date.today()
    de = (hoje - datetime.timedelta(days=dias)).isoformat()
    ate = hoje.isoformat()
    fixtures = _requisitar(
        "fixtures",
        {
            "league": cfg.LIGA_COPA_DO_MUNDO,
            "season": cfg.TEMPORADA_COPA,
            "from": de,
            "to": ate,
            "status": "FT-AET-PEN",
        },
    )
    return [
        {
            "fixture_id": fx["fixture"]["id"],
            "id_casa": fx["teams"]["home"]["id"],
            "id_fora": fx["teams"]["away"]["id"],
            "time_casa": fx["teams"]["home"]["name"],
            "time_fora": fx["teams"]["away"]["name"],
            "gols_casa": fx["goals"]["home"],
            "gols_fora": fx["goals"]["away"],
        }
        for fx in fixtures
    ]


# ---------------------------------------------------------------------------
# Fixtures cacheadas (usado pelo gerar_dataset.py)
# ---------------------------------------------------------------------------
def baixar_fixtures_temporada(team_id, temporada):
    cache = _carregar_cache()
    chave = f"{team_id}_{temporada}"

    ano_atual = datetime.date.today().year
    ttl = 168 if temporada < ano_atual else 6

    if chave in cache["fixtures"] and _ttl_valido(cache["fixtures"][chave], ttl):
        return cache["fixtures"][chave]["data"]

    try:
        resposta = _requisitar("fixtures", {"team": team_id, "season": temporada})
    except FootballAPIError:
        return []

    finalizados = [
        fx for fx in resposta
        if fx["fixture"]["status"]["short"] in STATUS_FINALIZADOS
    ]

    cache["fixtures"][chave] = {
        "timestamp": datetime.datetime.now().isoformat(),
        "data": finalizados,
    }
    _guardar_cache(cache)
    return finalizados
