#!/usr/bin/env python3
import argparse
import os
import re
import string
import logging
from time import perf_counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Iterable, Union

import numpy as np
import pandas as pd

"""
Proactive thread limiting and tokenizers parallelism off to avoid mutex locks
when importing heavy NLP stacks (tokenizers/torch) on some platforms.
These are safe defaults and can be overridden by user env.
"""
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("HF_HOME", "/Users/oleitao/Documents/Repos/RUMOS/FIA/unsupervised-models/hf")
os.environ.setdefault("TRANSFORMERS_CACHE", "/Users/oleitao/Documents/Repos/RUMOS/FIA/unsupervised-models/cache")

# Also try to disable tokenizer parallelism via API if available
try:  # pragma: no cover
    from tokenizers import parallelism as _tok_parallelism  # type: ignore
    try:
        _tok_parallelism.set_parallelism(False)  # type: ignore
    except Exception:
        pass
except Exception:
    pass

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import normalize
except Exception as e:  # pragma: no cover
    TfidfVectorizer = None  # type: ignore
    TruncatedSVD = None  # type: ignore
    MiniBatchKMeans = None  # type: ignore
    IsolationForest = None  # type: ignore
    normalize = None  # type: ignore


# ---------------------
# Text preprocessing
# ---------------------

PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def basic_clean(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.lower()
    # Replace URLs/emails
    t = re.sub(r"https?://\S+", " <url> ", t)
    t = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", " <email> ", t)
    # Remove punctuation (keep apostrophes for contractions)
    t = t.translate(PUNCT_TABLE)
    t = normalize_whitespace(t)
    return t


def clean_series(series: pd.Series) -> pd.Series:
    """Vectorized text cleaning for speed over large datasets."""
    s = series.astype(str).str.lower()
    s = s.str.replace(r"https?://\S+", " <url> ", regex=True)
    s = s.str.replace(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", " <email> ", regex=True)
    s = s.map(lambda x: x.translate(PUNCT_TABLE))
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return s


def log(msg: str) -> None:
    print(f"[unsup] {msg}")


# ---------------------
# Embeddings
# ---------------------

@dataclass
class EmbeddingResult:
    vectors: np.ndarray
    method: str
    vectorizer: Optional[TfidfVectorizer]
    tfidf_matrix: Optional["scipy.sparse.spmatrix"]  # type: ignore


def embed_texts(
    texts: List[str],
    method: str = "tfidf",
    svd_components: int = 100,
    max_features: int = 50_000,
    sentence_model: str = "all-MiniLM-L6-v2",
    hf_home: Optional[str] = None,
    hf_offline: bool = False,
    min_df: Union[int, float] = 2,
    max_df: Union[int, float] = 1.0,
    ngram_max: int = 2,
    stop_words: Optional[str] = None,
    st_batch_size: int = 64,
) -> EmbeddingResult:
    """
    Returns dense vectors for texts.
    - method=auto: try sentence-transformers, fallback to TF-IDF + SVD
    - method=sentence: require sentence-transformers
    - method=torch: use HuggingFace transformers (PyTorch) + mean pooling
    - method=tfidf: TF-IDF + SVD
    Also returns the TF-IDF vectorizer and matrix to allow cluster keyword summaries.
    """
    vec = None
    X_tfidf = None

    if method in {"auto", "sentence"}:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            # Also try to reduce torch threads if present
            try:
                import torch  # type: ignore
                try:
                    torch.set_num_threads(10)
                except Exception:
                    pass
            except Exception:
                pass
            # Optional cache control for offline/cached usage
            if hf_home:
                os.environ.setdefault("HF_HOME", hf_home)
                os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(hf_home, "transformers"))
                os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(hf_home, "sentence-transformers"))
            if hf_offline:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
            try:
                log(f"Loading sentence model: {sentence_model}")
                model = SentenceTransformer(sentence_model, device="cpu", cache_folder=(hf_home or None))
                embs = model.encode(texts, show_progress_bar=False, normalize_embeddings=True, batch_size=st_batch_size)
                return EmbeddingResult(vectors=np.asarray(embs), method="sentence", vectorizer=None, tfidf_matrix=None)
            except Exception as e:
                if method == "sentence":
                    raise
                # Fallback below
                log(f"Sentence embeddings unavailable or slow; falling back to TF-IDF. Reason: {type(e).__name__}")
        except Exception as e:
            if method == "sentence":
                raise
            log("sentence-transformers not installed; using TF-IDF embeddings.")

    if TfidfVectorizer is None or TruncatedSVD is None:
        raise RuntimeError("scikit-learn is required for TF-IDF embeddings but not available in this environment.")

    # Optional PyTorch/HF embeddings path
    if method == "torch":
        try:
            import torch  # type: ignore
            from transformers import AutoTokenizer, AutoModel  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "transformers (and torch) are required for method='torch'. Install with: pip install torch transformers"
            ) from e

        # Prepare env/cache
        if hf_home:
            os.environ.setdefault("HF_HOME", hf_home)
            os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(hf_home, "transformers"))
        if hf_offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        # Canonicalize model id for transformers (ensure repo prefix if omitted)
        model_id = sentence_model
        if "/" not in model_id:
            model_id = f"sentence-transformers/{model_id}"

        local_only = bool(hf_offline)
        tok = AutoTokenizer.from_pretrained(model_id, cache_dir=hf_home or None, local_files_only=local_only)
        mdl = AutoModel.from_pretrained(model_id, cache_dir=hf_home or None, local_files_only=local_only)
        mdl.eval()
        try:
            torch.set_num_threads(max(1, int(os.environ.get("OMP_NUM_THREADS", "1"))))
        except Exception:
            pass
        device = torch.device("cpu")

        def _batch_encode(batch: List[str]) -> np.ndarray:
            enc = tok(
                batch,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            with torch.no_grad():
                out = mdl(**{k: v.to(device) for k, v in enc.items()})
                if hasattr(out, "last_hidden_state"):
                    hidden = out.last_hidden_state  # [B, T, H]
                else:
                    # Fallback: try first element
                    hidden = out[0]
                mask = enc["attention_mask"].to(device).unsqueeze(-1).type_as(hidden)
                summed = (hidden * mask).sum(dim=1)
                counts = mask.sum(dim=1).clamp(min=1e-6)
                sent = summed / counts  # mean pooling
                # L2 normalize
                sent = torch.nn.functional.normalize(sent, p=2, dim=1)
                return sent.cpu().numpy()

        batch = int(max(1, st_batch_size))
        all_vecs: List[np.ndarray] = []
        for i in range(0, len(texts), batch):
            all_vecs.append(_batch_encode(texts[i : i + batch]))
        dense = np.vstack(all_vecs).astype(np.float32, copy=False)
        return EmbeddingResult(vectors=dense, method="torch", vectorizer=None, tfidf_matrix=None)

    vec = TfidfVectorizer(
        ngram_range=(1, int(ngram_max)),
        min_df=min_df,
        max_df=max_df,
        max_features=max_features,
        sublinear_tf=True,
        stop_words=(None if stop_words in (None, "none", "") else stop_words),
    )
    X_tfidf = vec.fit_transform(texts)
    svd = TruncatedSVD(n_components=svd_components, random_state=42)
    dense = svd.fit_transform(X_tfidf).astype(np.float32, copy=False)
    if normalize is not None:
        dense = normalize(dense)
    return EmbeddingResult(vectors=dense, method="tfidf", vectorizer=vec, tfidf_matrix=X_tfidf)


# ---------------------
# Clustering
# ---------------------

@dataclass
class ClusterResult:
    labels: np.ndarray
    k: int


def cluster_embeddings(embeddings: np.ndarray, k: Optional[int] = None, random_state: int = 42, mbatch_size: int = 2048) -> ClusterResult:
    n = embeddings.shape[0]
    if MiniBatchKMeans is None:
        raise RuntimeError("scikit-learn is required for clustering but not available in this environment.")

    if k is None:
        # Heuristic: small n -> 5; larger n -> sqrt(n/2) clamped [5, 25]
        k_guess = int(max(5, min(25, np.sqrt(max(2, n) / 2))))
        k = k_guess

    kmeans = MiniBatchKMeans(n_clusters=int(k), random_state=random_state, batch_size=mbatch_size, n_init=10, init="k-means++")
    labels = kmeans.fit_predict(embeddings)
    return ClusterResult(labels=labels.astype(int), k=int(k))


def top_keywords_per_cluster(
    labels: np.ndarray,
    vectorizer: Optional[TfidfVectorizer],
    X_tfidf: Optional["scipy.sparse.spmatrix"],  # type: ignore
    topn: int = 10,
) -> List[Tuple[int, List[Tuple[str, float]]]]:
    if vectorizer is None or X_tfidf is None:
        return []
    feature_names = np.array(vectorizer.get_feature_names_out())
    out: List[Tuple[int, List[Tuple[str, float]]]] = []
    for c in np.unique(labels):
        mask = (labels == c)
        if mask.sum() == 0:
            out.append((int(c), []))
            continue
        # Mean TF-IDF per term for this cluster
        mean_vec = X_tfidf[mask].mean(axis=0)
        if hasattr(mean_vec, "A1"):
            mean_arr = mean_vec.A1
        else:
            mean_arr = np.asarray(mean_vec).ravel()
        idx = np.argsort(-mean_arr)[:topn]
        out.append((int(c), [(feature_names[i], float(mean_arr[i])) for i in idx]))
    return out


# ---------------------
# Near-duplicate detection (SimHash)
# ---------------------

def stable_token_hash(token: str) -> int:
    # 64-bit hash derived from sha1 for repeatability
    import hashlib

    h = hashlib.sha1(token.encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(h[:8], byteorder="big", signed=False)


def simhash(text: str, weight_tokens: bool = True) -> int:
    tokens = [t for t in basic_clean(text).split() if t]
    if not tokens:
        return 0
    from collections import Counter

    counts = Counter(tokens)
    bits = [0] * 64
    for tok, cnt in counts.items():
        h = stable_token_hash(tok)
        w = cnt if weight_tokens else 1
        for i in range(64):
            if (h >> i) & 1:
                bits[i] += w
            else:
                bits[i] -= w
    # Build 64-bit fingerprint by bit sign
    fp = 0
    for i, val in enumerate(bits):
        if val >= 0:
            fp |= (1 << i)
    return fp


def hamming_distance64(a: int, b: int) -> int:
    return int(((a ^ b).bit_count()))


@dataclass
class NearDuplicate:
    i: int
    j: int
    dist: int


def find_near_duplicates(
    texts: List[str],
    max_hamming: int = 3,
    bucket_prefix_bits: int = 16,
    max_bucket_size: int = 2000,
) -> List[NearDuplicate]:
    n = len(texts)
    fps = [simhash(t) for t in texts]
    # Bucket by prefix to reduce comparisons
    buckets: Dict[int, List[int]] = {}
    for idx, fp in enumerate(fps):
        if bucket_prefix_bits <= 0:
            key = 0
        else:
            key = fp >> (64 - bucket_prefix_bits)
        buckets.setdefault(key, []).append(idx)

    pairs: List[NearDuplicate] = []
    for _, idxs in buckets.items():
        m = len(idxs)
        if m <= 1:
            continue
        # Guardrail against quadratic blow-up on massive buckets
        if max_bucket_size and m > max_bucket_size:
            continue
        for a in range(m):
            ia = idxs[a]
            fpa = fps[ia]
            for b in range(a + 1, m):
                ib = idxs[b]
                dist = hamming_distance64(fpa, fps[ib])
                if dist <= max_hamming:
                    pairs.append(NearDuplicate(i=ia, j=ib, dist=dist))
    return pairs


def exact_duplicate_groups(clean_texts: List[str]) -> Dict[int, int]:
    """Returns mapping index -> group_id for exact duplicates (case/space/punct normalized)."""
    groups: Dict[str, int] = {}
    mapping: Dict[int, int] = {}
    gid = 1
    for i, t in enumerate(clean_texts):
        key = t
        if key in groups:
            mapping[i] = groups[key]
        else:
            groups[key] = gid
            mapping[i] = gid
            gid += 1
    # Re-label groups that appear only once as 0 (unique)
    from collections import Counter

    counts = Counter(mapping.values())
    for i, g in list(mapping.items()):
        if counts[g] <= 1:
            mapping[i] = 0
    return mapping


def union_find(n: int) -> Tuple[List[int], callable]:
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx == ry:
            return
        if rank[rx] < rank[ry]:
            parent[rx] = ry
        elif rank[rx] > rank[ry]:
            parent[ry] = rx
        else:
            parent[ry] = rx
            rank[rx] += 1

    return parent, union


def build_near_duplicate_groups(n: int, pairs: List[NearDuplicate]) -> Dict[int, int]:
    parent, union = union_find(n)
    for p in pairs:
        union(p.i, p.j)

    # Assign compact group ids >=1 for components with size >=2
    # First, compute representative for each index
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    reps = [find(i) for i in range(n)]
    from collections import Counter

    counts = Counter(reps)
    rep_to_gid: Dict[int, int] = {}
    gid = 1
    for rep, c in counts.items():
        if c >= 2:
            rep_to_gid[rep] = gid
            gid += 1
    mapping: Dict[int, int] = {}
    for i, r in enumerate(reps):
        mapping[i] = rep_to_gid.get(r, 0)
    return mapping


# ---------------------
# Anomaly detection
# ---------------------

@dataclass
class AnomalyResult:
    scores: np.ndarray
    flags: np.ndarray


def detect_anomalies(embeddings: np.ndarray, contamination: float = 0.02, random_state: int = 42) -> AnomalyResult:
    n = embeddings.shape[0]
    if IsolationForest is None:
        # Simple fallback: distance from mean (z-score on L2 norms)
        norms = np.linalg.norm(embeddings - embeddings.mean(axis=0, keepdims=True), axis=1)
        z = (norms - norms.mean()) / (norms.std() + 1e-8)
        thresh = np.quantile(z, 1.0 - contamination)
        flags = (z >= thresh).astype(int)
        return AnomalyResult(scores=z.astype(float), flags=flags)

    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=random_state, n_jobs=-1)
    iso.fit(embeddings)
    # score_samples: higher => more normal. Convert to anomaly score by negation
    scores = -iso.score_samples(embeddings)
    # Threshold by contamination
    cut = np.quantile(scores, 1.0 - contamination)
    flags = (scores >= cut).astype(int)
    return AnomalyResult(scores=scores.astype(float), flags=flags)


# ---------------------
# Main runner
# ---------------------


def run(
    csv_path: str,
    text_col: str = "Comment",
    k: Optional[int] = None,
    embedding_method: str = "tfidf",
    svd_components: int = 100,
    max_features: int = 50_000,
    dedup_hamming: int = 3,
    bucket_prefix_bits: int = 16,
    contamination: float = 0.02,
    sample: Optional[int] = None,
    out_dir: Optional[str] = None,
    sentence_model: str = "all-MiniLM-L6-v2",
    hf_home: Optional[str] = None,
    hf_offline: bool = False,
    min_df: Union[int, float] = 2,
    max_df: Union[int, float] = 1.0,
    ngram_max: int = 2,
    stop_words: Optional[str] = None,
    st_batch_size: int = 64,
    mbatch_size: int = 2048,
    max_bucket_size: int = 2000,
    seed: int = 42,
    skip_cluster: bool = False,
    skip_dedup: bool = False,
    skip_anomaly: bool = False,
) -> str:
    if not os.path.exists(csv_path):
        raise SystemExit(f"Input CSV not found: {csv_path}")

    t0 = perf_counter()
    log(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    log(f"Loaded {len(df):,} rows. Columns: {list(df.columns)}")
    if text_col not in df.columns:
        raise SystemExit(f"Column '{text_col}' not found in CSV. Available: {list(df.columns)}")

    base_dir = os.path.dirname(os.path.abspath(csv_path))
    default_out_dir = os.path.join(base_dir, "unsupervised-models")
    out_dir = out_dir or default_out_dir
    os.makedirs(out_dir, exist_ok=True)

    log("Preprocessing text (vectorized cleaning)...")
    t_prep = perf_counter()
    data = df[[text_col]].copy()
    data["clean_text"] = clean_series(data[text_col])
    log(f"Preprocessing done in {perf_counter() - t_prep:.2f}s")

    if sample is not None and len(data) > sample:
        log(f"Sampling {sample:,} of {len(data):,} rows for faster run...")
        data = data.sample(n=sample, random_state=seed).reset_index(drop=False).rename(columns={"index": "orig_index"})
    else:
        data = data.reset_index(drop=False).rename(columns={"index": "orig_index"})

    texts = data[text_col].astype(str).tolist()
    clean_texts = data["clean_text"].astype(str).tolist()

    # Embeddings
    log(f"Computing embeddings with method='{embedding_method}'...")
    t_emb = perf_counter()
    emb_res = embed_texts(
        clean_texts,
        method=embedding_method,
        svd_components=svd_components,
        max_features=max_features,
        sentence_model=sentence_model,
        hf_home=hf_home,
        hf_offline=hf_offline,
        min_df=min_df,
        max_df=max_df,
        ngram_max=ngram_max,
        stop_words=stop_words,
        st_batch_size=st_batch_size,
    )
    embeddings = emb_res.vectors
    log(f"Embeddings ready using '{emb_res.method}' | shape={embeddings.shape} | {perf_counter() - t_emb:.2f}s")

    # Clustering
    if not skip_cluster:
        log(f"Clustering embeddings (k={'auto' if k is None else k})...")
        t_cl = perf_counter()
        cl_res = cluster_embeddings(embeddings, k=k, random_state=seed, mbatch_size=mbatch_size)
        data["cluster"] = cl_res.labels
        uniq, cnts = np.unique(cl_res.labels, return_counts=True)
        largest = int(cnts.max()) if len(cnts) else 0
        log(f"Clustering done: k={cl_res.k}, sizes min={int(cnts.min()) if len(cnts) else 0}, max={largest} | {perf_counter() - t_cl:.2f}s")
    else:
        data["cluster"] = -1
        cl_res = ClusterResult(labels=np.full(len(data), -1, dtype=int), k=0)
        log("Clustering skipped by flag.")

    # Cluster top keywords (build TF-IDF on demand if needed)
    if not skip_cluster:
        t_kw = perf_counter()
        vec_kw = emb_res.vectorizer
        X_kw = emb_res.tfidf_matrix
        built_local_tfidf = False
        if (vec_kw is None or X_kw is None) and TfidfVectorizer is not None:
            try:
                vec_kw = TfidfVectorizer(
                    ngram_range=(1, int(ngram_max)),
                    min_df=min_df,
                    max_df=max_df,
                    max_features=max_features,
                    sublinear_tf=True,
                    stop_words=(None if stop_words in (None, "none", "") else stop_words),
                )
                X_kw = vec_kw.fit_transform(clean_texts)
                built_local_tfidf = True
            except Exception as e:  # pragma: no cover
                vec_kw = None
                X_kw = None
        cluster_keywords = top_keywords_per_cluster(cl_res.labels, vec_kw, X_kw, topn=10)
        summary_rows = []
        for c, kws in cluster_keywords:
            for term, score in kws:
                summary_rows.append({"cluster": c, "term": term, "score": score})
        clusters_summary = pd.DataFrame(summary_rows)
        if not clusters_summary.empty:
            src = "local TF-IDF" if built_local_tfidf else "embedding TF-IDF"
            log(f"Computed cluster keywords from {src} in {perf_counter() - t_kw:.2f}s")
        else:
            log("Skipped keyword summary (TF-IDF unavailable)")
    else:
        clusters_summary = pd.DataFrame()

    # Deduplication: exact duplicates first
    if not skip_dedup:
        log("Detecting exact duplicates...")
        t_dx = perf_counter()
        exact_groups_map = exact_duplicate_groups(clean_texts)
        data["dup_exact_group"] = [exact_groups_map[i] for i in range(len(clean_texts))]
        exact_dups = int((data["dup_exact_group"].astype(int) > 0).sum())
        log(f"Exact duplicates flagged: {exact_dups} | {perf_counter() - t_dx:.2f}s")
    else:
        data["dup_exact_group"] = 0
        log("Exact duplicate detection skipped by flag.")

    # Near-duplicates via SimHash bucketing
    if not skip_dedup:
        log(f"Finding near-duplicates via SimHash (hamming<={dedup_hamming}, prefix_bits={bucket_prefix_bits})...")
        t_nd = perf_counter()
        near_pairs = find_near_duplicates(
            texts=clean_texts,
            max_hamming=dedup_hamming,
            bucket_prefix_bits=bucket_prefix_bits,
            max_bucket_size=max_bucket_size,
        )
        near_map = build_near_duplicate_groups(n=len(clean_texts), pairs=near_pairs)
        data["dup_near_group"] = [near_map[i] for i in range(len(clean_texts))]
        data["is_near_duplicate"] = data["dup_near_group"].astype(int).apply(lambda g: g > 0)
        near_pairs_ct = len(near_pairs)
        near_groups_ct = len({g for g in near_map.values() if g > 0})
        near_flagged = int(data["is_near_duplicate"].sum())
        log(f"Near-duplicates: pairs={near_pairs_ct}, groups={near_groups_ct}, flagged={near_flagged} | {perf_counter() - t_nd:.2f}s")
    else:
        data["dup_near_group"] = 0
        data["is_near_duplicate"] = False
        near_map = {}
        log("Near-duplicate detection skipped by flag.")

    # For reference record id per near-duplicate group
    ref_map: Dict[int, int] = {}
    for g in sorted([g for g in near_map.values() if g > 0]):
        if g not in ref_map:
            # choose the first occurrence as reference
            idx = int(np.where(data["dup_near_group"].values == g)[0][0])
            ref_map[g] = int(data.loc[idx, "orig_index"])  # original index in the source CSV
    data["near_duplicate_of"] = data["dup_near_group"].apply(lambda g: ref_map.get(int(g), -1))

    # Anomaly detection on embeddings
    if not skip_anomaly:
        log(f"Detecting anomalies (contamination={contamination:.3f})...")
        t_an = perf_counter()
        an_res = detect_anomalies(embeddings, contamination=contamination)
        data["anomaly_score"] = an_res.scores
        data["is_anomaly"] = (an_res.flags.astype(int) == 1)
        log(f"Anomalies flagged: {int(data['is_anomaly'].sum())} | {perf_counter() - t_an:.2f}s")
    else:
        data["anomaly_score"] = 0.0
        data["is_anomaly"] = False
        log("Anomaly detection skipped by flag.")

    # Build enriched output by joining back to original if needed
    t_join = perf_counter()
    enriched = data.merge(df.reset_index(drop=False).rename(columns={"index": "orig_index"}), on="orig_index", how="left")
    log(f"Join back to original done in {perf_counter() - t_join:.2f}s")

    # Output paths
    enriched_out = os.path.join(out_dir, "YoutubeComments_unsupervised_enriched.csv")
    log(f"Writing enriched dataset -> {enriched_out}")
    t_wr = perf_counter()
    enriched.to_csv(enriched_out, index=False)
    log(f"Enriched saved ({len(enriched):,} rows) in {perf_counter() - t_wr:.2f}s")

    # Clusters summary
    if not clusters_summary.empty:
        clusters_path = os.path.join(out_dir, "clusters_summary.csv")
        log(f"Writing clusters summary -> {clusters_path}")
        clusters_summary.sort_values(["cluster", "score"], ascending=[True, False]).to_csv(clusters_path, index=False)

    # Near-duplicates listing
    if data["is_near_duplicate"].any():
        dup_path = os.path.join(out_dir, "near_duplicates.csv")
        dup_list = data[data["is_near_duplicate"]][["orig_index", text_col, "clean_text", "dup_near_group", "near_duplicate_of"]].copy()
        log(f"Writing near-duplicates listing -> {dup_path}")
        dup_list.to_csv(dup_path, index=False)

    # Anomalies listing
    if data["is_anomaly"].any():
        an_path = os.path.join(out_dir, "anomalies.csv")
        an_list = data[data["is_anomaly"]][["orig_index", text_col, "clean_text", "anomaly_score", "cluster"]].copy()
        log(f"Writing anomalies listing -> {an_path}")
        an_list.sort_values("anomaly_score", ascending=False).to_csv(an_path, index=False)

    log(f"Done in {perf_counter() - t0:.2f}s total.")

    return enriched_out


def download_model(embedding_method: str, model_name: str, hf_home: Optional[str] = None, hf_offline: bool = False) -> None:
    """Download model weights/tokenizer into local cache and exit."""
    if hf_home:
        os.environ.setdefault("HF_HOME", hf_home)
        os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(hf_home, "transformers"))
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(hf_home, "sentence-transformers"))
    if hf_offline:
        log("hf_offline is set; download requires network. Ignoring offline for this step if no cache is present.")
    try:
        import torch  # noqa: F401
    except Exception:
        pass

    if embedding_method in {"sentence", "auto"}:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise SystemExit("sentence-transformers not installed. Install with: pip install sentence-transformers") from e
        log(f"Downloading sentence-transformers model: {model_name}")
        _ = SentenceTransformer(model_name, device="cpu", cache_folder=(hf_home or None))
        log("Download complete (cached).")
        return

    if embedding_method == "torch":
        try:
            from transformers import AutoTokenizer, AutoModel  # type: ignore
        except Exception as e:  # pragma: no cover
            raise SystemExit("transformers not installed. Install with: pip install transformers") from e
        repo = model_name if "/" in model_name else f"sentence-transformers/{model_name}"
        log(f"Downloading HF transformers model+tokenizer: {repo}")
        _ = AutoTokenizer.from_pretrained(repo, cache_dir=hf_home or None, local_files_only=False)
        _ = AutoModel.from_pretrained(repo, cache_dir=hf_home or None, local_files_only=False)
        log("Download complete (cached).")
        return

    log("No download needed for TF-IDF method.")

def main():
    ap = argparse.ArgumentParser(description="FIA: Unsupervised semantic analysis (clustering, dedup, anomalies)")
    ap.add_argument("--csv", default="/Users/oleitao/Documents/Repos/RUMOS/FIA/YoutubeCommentsDataSet.csv", help="Path to input CSV with at least a text column")
    ap.add_argument("--text-col", default="Comment", help="Name of the text column")
    ap.add_argument("--k", type=int, default=None, help="Number of clusters (default: heuristic)")
    ap.add_argument("--embedding", choices=["auto", "sentence", "tfidf", "torch"], default="tfidf", help="Embedding method")
    ap.add_argument("--svd-components", type=int, default=100, help="Components for TF-IDF SVD embeddings")
    ap.add_argument("--max-features", type=int, default=50_000, help="Max features for TF-IDF")
    ap.add_argument("--min-df", type=float, default=2, help="TF-IDF min_df (int count or float proportion)")
    ap.add_argument("--max-df", type=float, default=1.0, help="TF-IDF max_df (float proportion)")
    ap.add_argument("--ngram-max", type=int, default=2, help="TF-IDF max n-gram size")
    ap.add_argument("--stop-words", default=None, help="TF-IDF stop words: english|portuguese|none")
    ap.add_argument("--dedup-hamming", type=int, default=3, help="Max Hamming distance for SimHash near-duplicates")
    ap.add_argument("--bucket-prefix-bits", type=int, default=16, help="Bucket prefix bits for SimHash banding")
    ap.add_argument("--max-bucket-size", type=int, default=2000, help="Max bucket size to compare pairs (guardrail)")
    ap.add_argument("--contamination", type=float, default=0.02, help="Anomaly fraction for IsolationForest")
    ap.add_argument("--sample", type=int, default=None, help="Optional sample size to speed up iteration")
    ap.add_argument("--out-dir", default=None, help="Directory to save outputs (default: FIA/unsupervised-models)")
    ap.add_argument("--sentence-model", default="all-MiniLM-L6-v2", help="SentenceTransformer model name or local path")
    ap.add_argument("--hf-home", default=None, help="HuggingFace cache dir (to use pre-downloaded models)")
    ap.add_argument("--hf-offline", action="store_true", help="Use HuggingFace in offline mode (no downloads)")
    ap.add_argument("--st-batch-size", type=int, default=64, help="Batch size for sentence-transformers encoding")
    ap.add_argument("--kmeans-batch-size", type=int, default=2048, help="MiniBatchKMeans batch_size")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    ap.add_argument("--skip-cluster", action="store_true", help="Skip clustering step")
    ap.add_argument("--skip-dedup", action="store_true", help="Skip dedup/near-dup steps")
    ap.add_argument("--skip-anomaly", action="store_true", help="Skip anomaly detection")
    ap.add_argument("--check-heavy", action="store_true", help="Only check heavy libs (torch/sentence-transformers) and exit")
    ap.add_argument("--download-model", action="store_true", help="Download the embedding model to cache and exit")
    args = ap.parse_args()

    # Apply heavy-lib env early (before any potential import inside run)
    if args.embedding in {"sentence", "auto", "torch"}:
        if args.hf_home:
            os.environ.setdefault("HF_HOME", args.hf_home)
            os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(args.hf_home, "transformers"))
            os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(args.hf_home, "sentence-transformers"))
        if args.hf_offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    if args.check_heavy:
        log("Checking heavy libraries...")
        try:
            import torch  # type: ignore
            ver = getattr(torch, "__version__", "?")
            mps = getattr(getattr(torch, "backends", object()), "mps", None)
            cuda = getattr(torch, "cuda", None)
            log(f"torch version: {ver}")
            if mps and hasattr(mps, "is_available"):
                log(f"MPS available: {mps.is_available()}")
            if cuda and hasattr(cuda, "is_available"):
                log(f"CUDA available: {cuda.is_available()}")
        except Exception as e:
            log(f"ERROR torch import failed: {type(e).__name__}: {e}")
        try:
            import sentence_transformers  # type: ignore
            ver = getattr(sentence_transformers, "__version__", "?")
            log(f"sentence-transformers version: {ver}")
            if args.embedding in {"sentence", "auto"}:
                from sentence_transformers import SentenceTransformer  # type: ignore
                # env already applied above
                log(f"Attempting to load model: {args.sentence_model}")
                try:
                    _ = SentenceTransformer(args.sentence_model, device="cpu")
                    log("Model load OK.")
                except Exception as e:
                    log(f"ERROR model load failed: {type(e).__name__}: {e}")
        except Exception as e:
            log(f"ERROR sentence-transformers import failed: {type(e).__name__}: {e}")
        if args.embedding == "torch":
            try:
                from transformers import AutoTokenizer, AutoModel  # type: ignore
                repo = args.sentence_model if "/" in args.sentence_model else f"sentence-transformers/{args.sentence_model}"
                log(f"Attempting to load HF model+tokenizer: {repo}")
                try:
                    _ = AutoTokenizer.from_pretrained(repo)
                    _ = AutoModel.from_pretrained(repo)
                    log("Transformers load OK.")
                except Exception as e:
                    log(f"ERROR transformers load failed: {type(e).__name__}: {e}")
            except Exception as e:
                log(f"ERROR transformers import failed: {type(e).__name__}: {e}")
        return

    if args.download_model:
        download_model(args.embedding, args.sentence_model, hf_home=args.hf_home, hf_offline=args.hf_offline)
        return

    out = run(
        csv_path=args.csv,
        text_col=args.text_col,
        k=args.k,
        embedding_method=args.embedding,
        svd_components=args.svd_components,
        max_features=args.max_features,
        dedup_hamming=args.dedup_hamming,
        bucket_prefix_bits=args.bucket_prefix_bits,
        contamination=args.contamination,
        sample=args.sample,
        out_dir=args.out_dir,
        sentence_model=args.sentence_model,
        hf_home=args.hf_home,
        hf_offline=args.hf_offline,
        min_df=args.min_df,
        max_df=args.max_df,
        ngram_max=args.ngram_max,
        stop_words=(None if (args.stop_words in [None, "none", ""]) else args.stop_words),
        st_batch_size=args.st_batch_size,
        mbatch_size=args.kmeans_batch_size,
        max_bucket_size=args.max_bucket_size,
        seed=args.seed,
        skip_cluster=args.skip_cluster,
        skip_dedup=args.skip_dedup,
        skip_anomaly=args.skip_anomaly,
    )
    print(f"Saved enriched dataset to: {out}")


if __name__ == "__main__":
    main()
