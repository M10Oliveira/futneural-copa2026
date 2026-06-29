import os

try:
    import config_local as _cfg
except ImportError:
    _cfg = None


def obter_chave(nome_env):
    valor = os.environ.get(nome_env, "").strip()
    if valor:
        return valor
    if _cfg is not None:
        return getattr(_cfg, nome_env, "").strip()
    return ""


# ---------------------------------------------------------------------------
# Chaves de API
# ---------------------------------------------------------------------------
FOOTBALL_API_KEY = obter_chave("FOOTBALL_API_KEY")
GROQ_API_KEY = obter_chave("GROQ_API_KEY")

# Cliente Groq (opcional — usado para traduzir nomes e como fallback de stats)
try:
    from groq import Groq
    GROQ_DISPONIVEL = True
except ImportError:
    GROQ_DISPONIVEL = False

groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_DISPONIVEL and GROQ_API_KEY) else None

# ---------------------------------------------------------------------------
# Copa do Mundo
# ---------------------------------------------------------------------------
LIGA_COPA_DO_MUNDO = 1
TEMPORADA_COPA = 2026

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EXCEL_PATH = "historico_predicoes.xlsx"
DATASET_PATH = "historico_jogos.csv"
MODELO_PATH = "cerebro_bot.joblib"
COPA_CSV_PATH = "copa_2026_resultados.csv"
NIVEL_PATH = "nivel_bot.json"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_api_football.json")

# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
MEDIA_GOLS_REFERENCIA = 1.3
MIN_AMOSTRAS_REGRESSAO = 15
MIN_AMOSTRAS_REDE_NEURAL = 40

# Heuristicas de escanteios e cartoes
MEDIA_ESCANTEIOS_BASE = 10.0
MEDIA_CARTOES_BASE = 4.0

# ---------------------------------------------------------------------------
# Colunas do Excel de previsoes
# ---------------------------------------------------------------------------
COLUNAS_EXCEL = [
    "ID", "Data/Hora", "Equipa Casa", "Equipa Fora", "ID Fixture API", "Fonte Dados",
    "xG Casa (Poisson)", "xG Fora (Poisson)",
    "Prob Casa (%)", "Prob Empate (%)", "Prob Fora (%)", "Escanteios Previstos",
    "Modelo Utilizado", "Peso Modelo IA (%)",
    "GF_Media_Casa", "GC_Media_Casa", "Forma_Casa", "Escanteios_Media_Casa", "Cartoes_Media_Casa",
    "GF_Media_Fora", "GC_Media_Fora", "Forma_Fora", "Escanteios_Media_Fora", "Cartoes_Media_Fora",
    "Gols Real Casa", "Gols Real Fora", "Resultado Real", "Status Previsao",
]
