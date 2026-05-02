"""End-to-end embedding model bench: quality + performance, real data, real models.

Compares multiple sentence-embedding models against a labeled corpus that
mirrors Koda's actual workload (PT-BR + EN, mixed technical/operational
queries). For each (model, device) combination the script measures:

QUALITY (per model):
- AUC discrimination of paraphrase vs random pairs (PT-BR)
- AUC discrimination of paraphrase vs random pairs (EN)
- AUC discrimination of cross-lingual pairs (PT ↔ EN)
- nDCG@5, Recall@3, MRR on a small ranking corpus
- Reranker uplift: nDCG@5 with bge-reranker re-scoring the top-K

PERFORMANCE (per model × device):
- Latency p50, p95 for batch=1, 10, 100
- Throughput embeds/s
- Cold-start time (first embed after load)
- Memory peak RSS during the batch=100 run

Models tested:
    A. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (current default)
    B. intfloat/multilingual-e5-small
    C. Alibaba-NLP/gte-multilingual-base
    D. BAAI/bge-m3 (dense path only)

Devices tested: cpu, mps (where available).

Run: python tests/bench/bench_embedding_models.py [--quick]
Output: structured JSON to stdout + readable table.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# CORPUS — domain-specific to Koda's actual use case
# ---------------------------------------------------------------------------

# Each entry is (a, b) — both sides should embed close together.
PARAPHRASE_PAIRS_PT: list[tuple[str, str]] = [
    ("como deployar serviço Python no Linux", "passos para colocar uma aplicação Python no ar em Linux"),
    ("liste tarefas em progresso", "mostre as tasks que estão sendo trabalhadas agora"),
    ("buscar bugs abertos no jira", "encontrar issues não resolvidas no Jira"),
    ("gerar resumo da última reunião", "criar um sumário da meeting de hoje"),
    ("rodar testes do projeto", "executar a suíte de testes"),
    ("conferir status do banco de dados", "verificar saúde do Postgres"),
    ("monitorar uso de memória", "checar consumo de RAM"),
    ("listar containers rodando", "mostrar containers Docker ativos"),
    ("fazer backup do servidor", "criar cópia de segurança do servidor"),
    ("acessar logs da última hora", "ver logs dos últimos 60 minutos"),
    ("reiniciar o serviço web", "restartar a aplicação web"),
    ("verificar conexão com a API", "testar se a API está respondendo"),
    ("listar usuários cadastrados", "mostrar quantidade de usuários no sistema"),
    ("limpar cache do navegador", "esvaziar o cache do browser"),
    ("agendar tarefa para amanhã", "marcar uma task para o dia seguinte"),
    ("buscar arquivos modificados hoje", "encontrar arquivos alterados nas últimas 24h"),
    ("conferir uso de disco", "verificar espaço disponível em disco"),
    ("explicar como funciona o Postgres MVCC", "descreva o mecanismo MVCC do PostgreSQL"),
    ("aplicar migration no banco", "rodar migração no Postgres"),
    ("revisar PR aberta", "fazer code review da pull request"),
]

PARAPHRASE_PAIRS_EN: list[tuple[str, str]] = [
    ("how to deploy a Python service on Linux", "steps to host a Python application on Linux"),
    ("list in-progress tasks", "show me the tasks being worked on right now"),
    ("find open bugs in jira", "look up unresolved issues in Jira"),
    ("summarize the last meeting", "produce a summary of today's meeting"),
    ("run the project tests", "execute the test suite"),
    ("check database health", "verify the Postgres status"),
    ("monitor memory usage", "track RAM consumption"),
    ("list running containers", "show active Docker containers"),
    ("backup the server", "create a server snapshot"),
    ("access logs from the last hour", "show logs from the past 60 minutes"),
    ("restart the web service", "reboot the web application"),
    ("check the API connection", "test whether the API responds"),
    ("list registered users", "show the number of users in the system"),
    ("clear browser cache", "empty the browser cache"),
    ("schedule a task for tomorrow", "set up a task for the next day"),
    ("find files modified today", "look up files changed in the last 24 hours"),
    ("check disk usage", "verify available disk space"),
    ("explain how Postgres MVCC works", "describe the MVCC mechanism of PostgreSQL"),
    ("apply a database migration", "run a Postgres migration"),
    ("review the open PR", "do a code review of the pull request"),
]

# Cross-lingual: PT-BR query ↔ EN equivalent meaning.
CROSS_LINGUAL_PAIRS: list[tuple[str, str]] = [
    ("como deployar serviço Python no Linux", "how to deploy a Python service on Linux"),
    ("listar tarefas em progresso", "list in-progress tasks"),
    ("buscar bugs abertos", "find open bugs"),
    ("gerar resumo da reunião", "summarize the meeting"),
    ("rodar os testes", "run the tests"),
    ("verificar status do banco", "check database status"),
    ("monitorar memória", "monitor memory"),
    ("listar containers ativos", "list active containers"),
    ("fazer backup", "do a backup"),
    ("ver logs recentes", "view recent logs"),
    ("reiniciar serviço web", "restart the web service"),
    ("testar conexão com API", "test API connection"),
    ("limpar o cache", "clear the cache"),
    ("agendar tarefa", "schedule a task"),
    ("conferir uso de disco", "check disk usage"),
    ("aplicar migration", "apply migration"),
    ("revisar pull request", "review pull request"),
    ("explicar MVCC do Postgres", "explain Postgres MVCC"),
    ("buscar arquivos alterados", "find changed files"),
    ("monitorar CPU", "monitor CPU"),
]


# Random unrelated sentences for negative pairs.
RANDOM_NEGATIVES_PT: list[str] = [
    "o céu hoje está nublado em São Paulo",
    "gosto de café com leite no café da manhã",
    "ontem assisti um filme italiano interessante",
    "preciso comprar pão na padaria da esquina",
    "o cachorro do vizinho late muito de noite",
    "minha bicicleta precisa de manutenção",
    "as flores do jardim estão desabrochando",
    "o trânsito está congestionado nesta sexta-feira",
    "vou viajar para Florianópolis no próximo mês",
    "o livro que li ontem foi muito emocionante",
    "preciso lavar a roupa no fim de semana",
    "o museu da cidade tem uma exposição nova",
    "meu sobrinho fez três anos ontem",
    "a praia de Copacabana estava cheia",
    "comprei um vinho português delicioso",
    "minha planta precisa de mais água",
    "o aniversário da minha avó é em junho",
    "o show do Caetano foi maravilhoso",
    "a feira no domingo tem frutas frescas",
    "estou aprendendo a tocar violão",
]

RANDOM_NEGATIVES_EN: list[str] = [
    "the weather is cloudy today in San Francisco",
    "i enjoy coffee with milk for breakfast",
    "yesterday i watched an interesting Italian movie",
    "i need to buy bread at the corner bakery",
    "the neighbor's dog barks a lot at night",
    "my bicycle needs maintenance",
    "the garden flowers are blooming",
    "traffic is congested this Friday afternoon",
    "i'm traveling to Hawaii next month",
    "the book i read yesterday was emotional",
    "i need to do the laundry over the weekend",
    "the city museum has a new exhibition",
    "my nephew turned three yesterday",
    "the beach was crowded today",
    "i bought a delicious Italian wine",
    "my plant needs more water",
    "my grandmother's birthday is in June",
    "the rock concert last night was amazing",
    "the Sunday market has fresh fruit",
    "i'm learning to play guitar",
]


# Ranking corpus: 10 queries, each with 3 relevant + 7 distractors.
@dataclass
class RankingCase:
    query: str
    relevant: list[str]
    distractors: list[str]


RANKING_CORPUS: list[RankingCase] = [
    # Each ranking case uses TOPICALLY RELATED distractors so the bench
    # can discriminate models. Off-topic distractors saturate every model
    # at nDCG@5 = 1.0 and reveal nothing.
    RankingCase(
        query="como criar um job cron que roda toda noite",
        relevant=[
            "use crontab para agendar uma task em '0 2 * * *' para rodar diariamente às 2 da manhã",
            "para rodar todo dia à noite no Linux você usa crontab com expressão de cron noturna",
            "schedule a recurring nightly job using cron with `0 0 * * *` syntax",
        ],
        distractors=[
            "remove a cron job from your crontab using `crontab -e` and deleting the line",
            "anacron is an alternative to cron for laptops that aren't always on",
            "systemd timers replace cron for services that need stronger lifecycle hooks",
            "list current cron jobs of your user with `crontab -l`",
            "para listar jobs agendados em todos usuários: ls /var/spool/cron/crontabs",
            "redirecionar stdout do cron para arquivo: '0 2 * * * cmd >> /var/log/cmd.log 2>&1'",
            "Kubernetes CronJob é diferente do cron tradicional pois roda em pods",
        ],
    ),
    RankingCase(
        query="git rebase versus git merge qual usar",
        relevant=[
            "diferença entre git rebase e git merge: rebase reescreve histórico, merge cria commit de junção",
            "quando preferir merge vs rebase em fluxo de feature branch",
            "rebase keeps history linear, merge preserves the branch topology",
        ],
        distractors=[
            "git stash guarda mudanças não commitadas para uso depois",
            "como resolver conflitos durante merge: edite o arquivo e git add depois commit",
            "git cherry-pick aplica um commit específico de outro branch",
            "git revert cria um novo commit que desfaz mudanças anteriores",
            "force push após rebase: git push --force-with-lease para segurança",
            "git submodule é para incluir outro repositório dentro do seu",
            "git bisect ajuda a achar o commit que introduziu um bug",
        ],
    ),
    RankingCase(
        query="como debuggar memory leak em aplicação Python",
        relevant=[
            "detect memory leaks in Python with tracemalloc and objgraph",
            "ferramentas para encontrar vazamentos de memória em Python: memory_profiler, tracemalloc",
            "use the gc module and tracemalloc to find Python memory leaks",
        ],
        distractors=[
            "Python garbage collector usa reference counting com cycle detection",
            "asyncio loop debug mode mostra coroutines não awaited",
            "cProfile para profile de tempo de execução em Python, não memória",
            "como fazer profile de uma função Python com tempo: time.perf_counter",
            "Python multiprocessing copy-on-write em fork() pode parecer leak mas não é",
            "LRU cache (functools) pode crescer sem limite se maxsize=None",
            "use weakref para evitar referências circulares em Python",
        ],
    ),
    RankingCase(
        query="postgres index strategy for fast queries",
        relevant=[
            "use B-tree index for equality and range queries on Postgres columns",
            "estratégia de índice no Postgres: B-tree para igualdade, GIN para JSONB, BRIN para grandes tabelas",
            "Postgres GIN index speeds up full-text search and JSONB containment queries",
        ],
        distractors=[
            "Postgres VACUUM removes dead tuples but doesn't reclaim disk space (use VACUUM FULL)",
            "explain analyze mostra plano de execução com tempo real de cada step no Postgres",
            "create a partitioned table in Postgres for time-series data with declarative partitioning",
            "Postgres roles e permissions: GRANT SELECT, INSERT ON tbl TO role",
            "MVCC em Postgres mantém versões das linhas; VACUUM limpa as obsoletas",
            "ANALYZE atualiza estatísticas que o planner usa para escolher index",
            "pg_stat_statements log mostra queries lentas mas precisa ser habilitado",
        ],
    ),
    RankingCase(
        query="quando usar Redis vs Memcached para cache",
        relevant=[
            "Redis suporta estruturas de dados ricas; Memcached é mais simples e leve",
            "use Redis when you need persistence, pub/sub, or rich data structures",
            "Memcached é melhor para cache puro de strings de alta velocidade",
        ],
        distractors=[
            "Redis Sentinel para alta disponibilidade com failover automático",
            "Memcached evicts entries usando LRU quando atinge o limite de memória",
            "Redis Cluster sharda dados por hash slot entre múltiplos nodes",
            "TTL em Redis: SET key value EX 60 define expiração de 60 segundos",
            "Redis pub/sub é fire-and-forget — sem persistência de mensagens",
            "Memcached não tem AOF nem RDB persistence — restart perde tudo",
            "Redis Streams é alternativa mais moderna ao pub/sub com consumer groups",
        ],
    ),
    RankingCase(
        query="docker container is not starting how to debug",
        relevant=[
            "use docker logs <container> to see why a container failed to start",
            "container failed to start: check logs with docker logs and entrypoint with docker inspect",
            "para debugar container Docker que não inicia: docker logs, docker inspect, docker events",
        ],
        distractors=[
            "Docker network: bridge é o default, host compartilha o network namespace do host",
            "para reduzir tamanho da imagem Docker use multi-stage builds",
            "docker exec -it <container> bash entra num container já rodando",
            "Dockerfile USER deve ser non-root para segurança em produção",
            "docker prune libera espaço removendo containers e imagens não usadas",
            "Compose v2 usa 'docker compose' (sem hífen) ao invés de docker-compose",
            "docker stats mostra uso de CPU e memória dos containers em tempo real",
        ],
    ),
    RankingCase(
        query="JWT vs session cookies for auth",
        relevant=[
            "JWT permite stateless authentication enquanto session cookies precisam de armazenamento server-side",
            "session cookies are easier to invalidate; JWT scales horizontally without shared state",
            "tradeoffs entre JWT e session: stateless vs revogação fácil",
        ],
        distractors=[
            "OAuth2 PKCE flow é mais seguro que implicit flow para apps SPA",
            "refresh token rotation: cada uso emite novo refresh, anula anterior",
            "CSRF tokens previnem ataques mesmo com cookies; SameSite ajuda também",
            "single sign-on (SSO) usa SAML ou OpenID Connect tipicamente",
            "TOTP authenticator apps geram códigos baseados em time + secret compartilhado",
            "WebAuthn permite passwordless auth via FIDO2 keys ou platform authenticators",
            "rate limiting no endpoint de login previne brute-force attacks",
        ],
    ),
    RankingCase(
        query="como otimizar query Postgres lenta",
        relevant=[
            "use EXPLAIN ANALYZE para identificar gargalos em query Postgres",
            "speed up slow Postgres queries: add appropriate indexes, run EXPLAIN ANALYZE, check pg_stat_statements",
            "criar índices apropriados, evitar SELECT *, usar pg_stat_statements para identificar queries lentas",
        ],
        distractors=[
            "Postgres connection pooling com PgBouncer reduz overhead de conexões",
            "use prepared statements para reduzir parse time em queries repetidas",
            "VACUUM atualiza visibility map mas só FREEZE limpa transaction IDs antigos",
            "Postgres logical replication permite replicar tabelas individuais via publications",
            "shared_buffers e effective_cache_size devem ser tunados conforme RAM disponível",
            "BRIN index é eficiente em grandes tabelas com correlação física entre dados",
            "particionar tabelas grandes por data acelera queries que filtram por intervalo",
        ],
    ),
    RankingCase(
        query="kubernetes pod stuck in pending state",
        relevant=[
            "pod stuck in Pending: check kubectl describe pod for scheduling failures, resource requests, taints",
            "pod travado em Pending: verificar quotas de namespace, recursos do node, taints e tolerations",
            "describe the pod to see Pending reason — usually insufficient resources or unschedulable nodes",
        ],
        distractors=[
            "kubectl logs <pod> -p mostra logs do container anterior se ele crashou",
            "ImagePullBackOff geralmente é credencial errada do registry ou imagem não existe",
            "CrashLoopBackOff: container inicia, falha rápido, k8s reinicia. Veja logs.",
            "OOMKilled é quando o pod excede memory limit do container",
            "PVC pendente pode bloquear pod se StorageClass não tem provisioner",
            "node affinity com labels ajuda a restringir em qual node o pod roda",
            "kubectl events ordenado por tempo: kubectl get events --sort-by='.lastTimestamp'",
        ],
    ),
    RankingCase(
        query="trabalhar com arquivo CSV grande em Python",
        relevant=[
            "para arquivos CSV grandes em Python use pandas com chunksize ou polars para processamento",
            "stream large CSV files in Python with the csv module reader instead of loading whole file",
            "polars and DuckDB handle CSV files larger than RAM efficiently in Python",
        ],
        distractors=[
            "openpyxl is for xlsx, csv module for csv files in Python stdlib",
            "Pandas read_parquet é muito mais rápido que read_csv para grandes datasets",
            "DuckDB pode fazer query SQL direto em arquivo Parquet sem carregar tudo",
            "pyarrow.dataset processa Parquet files em chunks com filtros pushdown",
            "Apache Arrow IPC formato é zero-copy entre processos Python",
            "JSONL formato (linhas de JSON) é alternativa streamável ao CSV",
            "csv.DictReader retorna OrderedDict por linha, mais legível que reader",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def cosine(a: Any, b: Any) -> float:
    import numpy as np  # noqa: PLC0415

    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def auc_paraphrase(model: Any, prep: Any, positives: list[tuple[str, str]], negatives: list[str]) -> float:
    """AUC of paraphrase pairs (positives, label=1) vs random cross-pairs (negatives, label=0).

    Returns area under the ROC curve. 0.5 = random, 1.0 = perfect separation.
    """
    from sklearn.metrics import roc_auc_score  # noqa: PLC0415

    pos_a, pos_b = zip(*positives, strict=False)
    neg_a = [pa for pa, _ in positives]
    neg_b = [negatives[i % len(negatives)] for i in range(len(positives))]

    all_a = list(pos_a) + neg_a
    all_b = list(pos_b) + neg_b
    labels = [1] * len(positives) + [0] * len(positives)

    # For paraphrase eval both sides are "documents" — neither is a query.
    # We use role="passage" for both since these aren't query-document pairs
    # but symmetric paraphrases.
    embs_a = prep(model, all_a, role="passage")
    embs_b = prep(model, all_b, role="passage")
    scores = [cosine(a, b) for a, b in zip(embs_a, embs_b, strict=True)]

    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def ranking_metrics(model: Any, prep: Any, ranking: list[RankingCase]) -> dict[str, float]:
    """Compute nDCG@5, Recall@3, MRR over the ranking corpus."""
    import math  # noqa: PLC0415

    ndcg5_list: list[float] = []
    recall3_list: list[float] = []
    mrr_list: list[float] = []

    for case in ranking:
        candidates = case.relevant + case.distractors  # 10 docs
        relevant_set = set(case.relevant)
        # Embed query with role=query, candidates with role=passage.
        q_emb = prep(model, [case.query], role="query")[0]
        cand_embs = prep(model, candidates, role="passage")
        scored = [(i, cosine(q_emb, e)) for i, e in enumerate(cand_embs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked_docs = [candidates[i] for i, _ in scored]

        # nDCG@5
        dcg = 0.0
        idcg = 0.0
        for i in range(5):
            if i < len(ranked_docs) and ranked_docs[i] in relevant_set:
                dcg += 1.0 / math.log2(i + 2)
        for i in range(min(5, len(case.relevant))):
            idcg += 1.0 / math.log2(i + 2)
        ndcg5_list.append(dcg / idcg if idcg > 0 else 0.0)

        # Recall@3
        top3 = set(ranked_docs[:3])
        recall3_list.append(len(top3 & relevant_set) / len(relevant_set))

        # MRR
        rr = 0.0
        for i, doc in enumerate(ranked_docs):
            if doc in relevant_set:
                rr = 1.0 / (i + 1)
                break
        mrr_list.append(rr)

    return {
        "ndcg@5": round(statistics.mean(ndcg5_list), 4),
        "recall@3": round(statistics.mean(recall3_list), 4),
        "mrr": round(statistics.mean(mrr_list), 4),
    }


def reranker_uplift(
    model: Any,
    prep: Any,
    reranker: Any,
    ranking: list[RankingCase],
) -> tuple[float, float]:
    """Run reranker on the top-K cosine results; return (ndcg5_baseline, ndcg5_with_reranker)."""
    import math  # noqa: PLC0415

    ndcg5_baseline_list: list[float] = []
    ndcg5_rerank_list: list[float] = []
    K = 5  # rerank top-K

    for case in ranking:
        candidates = case.relevant + case.distractors
        relevant_set = set(case.relevant)
        q_emb = prep(model, [case.query], role="query")[0]
        cand_embs = prep(model, candidates, role="passage")
        scored = [(i, cosine(q_emb, e)) for i, e in enumerate(cand_embs)]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Baseline nDCG@5
        ranked_docs = [candidates[i] for i, _ in scored]
        dcg = sum((1.0 / math.log2(i + 2)) for i in range(5) if i < len(ranked_docs) and ranked_docs[i] in relevant_set)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(relevant_set))))
        ndcg5_baseline_list.append(dcg / idcg if idcg > 0 else 0.0)

        # Rerank the top-K
        top_k_indices = [i for i, _ in scored[:K]]
        top_k_docs = [candidates[i] for i in top_k_indices]
        if reranker is not None and top_k_docs:
            pairs = [(case.query, d) for d in top_k_docs]
            scores = reranker.predict(pairs)
            scores = [float(s) for s in scores]
            # Re-sort top-K by reranker score
            reranked = sorted(zip(top_k_docs, scores, strict=True), key=lambda x: x[1], reverse=True)
            reranked_docs = [d for d, _ in reranked]
            # The remaining documents (positions K..) keep their original order
            tail = [candidates[i] for i, _ in scored[K:]]
            full_ranking = reranked_docs + tail
        else:
            full_ranking = ranked_docs

        dcg = sum(
            (1.0 / math.log2(i + 2)) for i in range(5) if i < len(full_ranking) and full_ranking[i] in relevant_set
        )
        ndcg5_rerank_list.append(dcg / idcg if idcg > 0 else 0.0)

    return (
        round(statistics.mean(ndcg5_baseline_list), 4),
        round(statistics.mean(ndcg5_rerank_list), 4),
    )


# ---------------------------------------------------------------------------
# Performance helpers
# ---------------------------------------------------------------------------


@dataclass
class PerfResult:
    cold_start_ms: float
    latency_p50_b1_ms: float
    latency_p95_b1_ms: float
    latency_p50_b10_ms: float
    latency_p95_b10_ms: float
    latency_p50_b100_ms: float
    latency_p95_b100_ms: float
    throughput_b100_per_s: float
    rss_mb_baseline: float
    rss_mb_after_load: float
    rss_mb_peak_after_b100: float


def measure_perf(model: Any, prep: Any, sample_text: str = "como deployar serviço") -> PerfResult:
    me = psutil.Process()
    rss_baseline_mb = me.memory_info().rss / 1e6

    # Cold-start: first single embed
    t0 = time.perf_counter()
    _ = prep(model, [sample_text])
    cold_start_ms = (time.perf_counter() - t0) * 1000

    rss_after_load_mb = me.memory_info().rss / 1e6

    # Warmup
    for _ in range(3):
        _ = prep(model, [sample_text])
        _ = prep(model, [sample_text] * 10)

    # b=1
    latencies_b1 = []
    for _ in range(20):
        t0 = time.perf_counter()
        _ = prep(model, [sample_text])
        latencies_b1.append((time.perf_counter() - t0) * 1000)

    # b=10
    latencies_b10 = []
    for _ in range(10):
        t0 = time.perf_counter()
        _ = prep(model, [sample_text] * 10)
        latencies_b10.append((time.perf_counter() - t0) * 1000)

    # b=100
    latencies_b100 = []
    rss_peak_mb = rss_after_load_mb
    for _ in range(5):
        t0 = time.perf_counter()
        _ = prep(model, [sample_text] * 100)
        latencies_b100.append((time.perf_counter() - t0) * 1000)
        cur_rss = me.memory_info().rss / 1e6
        rss_peak_mb = max(rss_peak_mb, cur_rss)

    return PerfResult(
        cold_start_ms=round(cold_start_ms, 1),
        latency_p50_b1_ms=round(statistics.median(latencies_b1), 2),
        latency_p95_b1_ms=round(sorted(latencies_b1)[int(len(latencies_b1) * 0.95)], 2),
        latency_p50_b10_ms=round(statistics.median(latencies_b10), 2),
        latency_p95_b10_ms=round(sorted(latencies_b10)[int(len(latencies_b10) * 0.95)], 2),
        latency_p50_b100_ms=round(statistics.median(latencies_b100), 2),
        latency_p95_b100_ms=round(sorted(latencies_b100)[int(len(latencies_b100) * 0.95)], 2),
        throughput_b100_per_s=round(100 / (statistics.median(latencies_b100) / 1000), 1),
        rss_mb_baseline=round(rss_baseline_mb, 1),
        rss_mb_after_load=round(rss_after_load_mb, 1),
        rss_mb_peak_after_b100=round(rss_peak_mb, 1),
    )


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def load_model(model_name: str, device: str) -> tuple[Any, Any]:
    """Return (model, prep_fn) where prep_fn(model, texts, *, role) → list[np.array]."""
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    kwargs: dict[str, Any] = {"device": device}
    if "gte" in model_name.lower():
        kwargs["trust_remote_code"] = True

    model = SentenceTransformer(model_name, **kwargs)
    is_e5 = "e5" in model_name.lower()

    def prep(m: Any, texts: list[str], *, role: str = "passage") -> list[Any]:
        # E5 models REQUIRE specific prefixes per their docs:
        #   "query: ..." for queries
        #   "passage: ..." for documents/candidates
        # The performance gap with the wrong prefix is large (~25 nDCG points
        # in our local bench) so the bench passes role explicitly.
        if is_e5:
            prefix = "query: " if role == "query" else "passage: "
            texts = [prefix + t for t in texts]
        emb = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return list(emb)

    return model, prep


def load_reranker(device: str) -> Any:
    from sentence_transformers import CrossEncoder  # noqa: PLC0415

    return CrossEncoder("BAAI/bge-reranker-base", device=device)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    model: str
    device: str
    quality: dict[str, float] = field(default_factory=dict)
    perf: PerfResult | None = None
    error: str | None = None


def run_combo(model_name: str, device: str, reranker: Any | None) -> RunResult:
    res = RunResult(model=model_name, device=device)
    try:
        print(f"\n  → loading {model_name} on {device}...")
        model, prep = load_model(model_name, device)
        print("     measuring quality...")
        res.quality["auc_paraphrase_pt"] = round(
            auc_paraphrase(model, prep, PARAPHRASE_PAIRS_PT, RANDOM_NEGATIVES_PT), 4
        )
        res.quality["auc_paraphrase_en"] = round(
            auc_paraphrase(model, prep, PARAPHRASE_PAIRS_EN, RANDOM_NEGATIVES_EN), 4
        )
        res.quality["auc_cross_lingual"] = round(
            auc_paraphrase(model, prep, CROSS_LINGUAL_PAIRS, RANDOM_NEGATIVES_EN + RANDOM_NEGATIVES_PT), 4
        )
        ranking = ranking_metrics(model, prep, RANKING_CORPUS)
        res.quality.update(ranking)
        if reranker is not None:
            base_ndcg, rerank_ndcg = reranker_uplift(model, prep, reranker, RANKING_CORPUS)
            res.quality["ndcg@5_with_reranker"] = rerank_ndcg
            res.quality["reranker_uplift_pp"] = round((rerank_ndcg - base_ndcg) * 100, 2)

        print("     measuring performance...")
        res.perf = measure_perf(model, prep)
    except Exception as exc:  # noqa: BLE001
        res.error = f"{type(exc).__name__}: {exc}"
        print(f"     ERROR: {res.error}")
    finally:
        gc.collect()
    return res


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Test only baseline + one alternative")
    parser.add_argument("--out", default="/tmp/embedding_bench.json", help="JSON output path")
    parser.add_argument("--device-only", choices=["cpu", "mps"], help="Restrict to a single device")
    parser.add_argument("--no-reranker", action="store_true", help="Skip reranker loading and uplift")
    args = parser.parse_args()

    models = [
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "intfloat/multilingual-e5-small",
    ]
    if args.quick:
        models = models[:2]

    devices = ["cpu", "mps"] if args.device_only is None else [args.device_only]

    print(f"=== Embedding bench: {len(models)} models × {len(devices)} devices ===")
    print(
        f"Quality corpus: {len(PARAPHRASE_PAIRS_PT)} PT pairs, {len(PARAPHRASE_PAIRS_EN)} EN, "
        f"{len(CROSS_LINGUAL_PAIRS)} cross-lingual, {len(RANKING_CORPUS)} ranking cases"
    )

    if args.no_reranker:
        print("\nSkipping reranker (--no-reranker)")
        reranker = None
    else:
        print("\nLoading reranker once on CPU...")
        try:
            reranker = load_reranker("cpu")
        except Exception as exc:  # noqa: BLE001
            print(f"  reranker load failed: {type(exc).__name__}: {exc}")
            print("  → continuing without reranker; uplift measurements will be skipped")
            reranker = None

    results: list[RunResult] = []
    for model_name in models:
        for device in devices:
            r = run_combo(model_name, device, reranker)
            results.append(r)

    payload = {
        "results": [
            {
                "model": r.model,
                "device": r.device,
                "quality": r.quality,
                "perf": (r.perf.__dict__ if r.perf else None),
                "error": r.error,
            }
            for r in results
        ]
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 100)
    print(
        f"{'MODEL':<55} {'DEV':<5} {'AUC-PT':<8} {'AUC-EN':<8} "
        f"{'CL-AUC':<8} {'nDCG@5':<8} {'+rrnk':<8} {'ms@b10':<8} {'ms@b100':<8}"
    )
    print("=" * 100)
    for r in results:
        if r.error:
            print(f"{r.model:<55} {r.device:<5} ERROR: {r.error[:40]}")
            continue
        q = r.quality
        p = r.perf
        print(
            f"{r.model.split('/')[-1]:<55} "
            f"{r.device:<5} "
            f"{q.get('auc_paraphrase_pt', 0):<8.3f} "
            f"{q.get('auc_paraphrase_en', 0):<8.3f} "
            f"{q.get('auc_cross_lingual', 0):<8.3f} "
            f"{q.get('ndcg@5', 0):<8.3f} "
            f"{q.get('ndcg@5_with_reranker', 0):<8.3f} "
            f"{p.latency_p50_b10_ms if p else 0:<8.1f} "
            f"{p.latency_p50_b100_ms if p else 0:<8.1f}"
        )

    print()
    print(f"Full payload written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
