#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential


# ----------------------------
# Small, file-based JSONL cache
# ----------------------------

class JsonlCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, int] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    try:
                        obj = json.loads(line)
                        key = obj.get("key")
                        if key:
                            self._index[key] = i
                    except Exception:
                        continue
        except Exception:
            pass

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        if key not in self._index:
            return None
        # Linear scan again (file may have grown); last write wins
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        if obj.get("key") == key:
                            return obj.get("value")
                    except Exception:
                        continue
        except Exception:
            return None
        return None

    def put(self, key: str, value: Dict[str, Any]):
        self._ensure_loaded()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
        self._index[key] = -1


# ----------------------------
# OpenAI minimal client wrapper
# ----------------------------

class OpenAIClient:
    def __init__(self, model: Optional[str] = None, cache: Optional[JsonlCache] = None, offline: bool = False):
        self.offline = offline or (os.environ.get("OPENAI_API_KEY") is None)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.cache = cache
        self._client = None
        if not self.offline:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI()
            except Exception as e:
                print(f"[WARN] OpenAI SDK not available or failed to init: {e}. Falling back to offline mode.")
                self.offline = True

    @staticmethod
    def _make_key(task: str, payload: Dict[str, Any]) -> str:
        m = hashlib.sha256()
        m.update(task.encode("utf-8"))
        m.update(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return m.hexdigest()

    def _cache_get(self, task: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.cache:
            return None
        return self.cache.get(self._make_key(task, payload))

    def _cache_put(self, task: str, payload: Dict[str, Any], value: Dict[str, Any]):
        if not self.cache:
            return
        self.cache.put(self._make_key(task, payload), value)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def chat_json(self, system: str, user: str, schema_hint: Optional[str] = None, task_name: str = "generic") -> Dict[str, Any]:
        payload = {
            "system": system,
            "user": user,
            "schema_hint": schema_hint or "",
            "model": self.model,
        }
        cached = self._cache_get(task_name, payload)
        if cached is not None:
            return cached

        if self.offline or self._client is None:
            # Very small heuristic fallback for offline mode
            faux = self._offline_response(user)
            self._cache_put(task_name, payload, faux)
            return faux

        content = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            # Use chat.completions for broad compatibility
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=content,
                temperature=0.2,
            )
            text = resp.choices[0].message.content or "{}"
        except Exception as e:
            # Fallback: bubble up for retry
            raise e

        data = self._extract_json(text)
        self._cache_put(task_name, payload, data)
        return data

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        # Try parse as JSON; else find first {...} block
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {"raw": text}
        return {"raw": text}

    @staticmethod
    def _offline_response(user_prompt: str) -> Dict[str, Any]:
        # Heuristics based on asked schema in the prompt
        if "label" in user_prompt and "confidence" in user_prompt:
            # very naive sentiment heuristics
            s = user_prompt.lower()
            neg_terms = ["bad", "not", "hate", "terrible", "awful", "no", "doesn't", "dont", "fees", "drag"]
            pos_terms = ["love", "great", "convenient", "secure", "easy", "helpful", "well done", "amazing"]
            pos = sum(t in s for t in pos_terms)
            neg = sum(t in s for t in neg_terms)
            label = "neutral"
            if pos > neg and pos > 0:
                label = "positive"
            elif neg > pos and neg > 0:
                label = "negative"
            conf = min(0.9, 0.6 + 0.1 * abs(pos - neg))
            return {"label": label, "confidence": round(conf, 2)}

        if "reasons" in user_prompt and "severity" in user_prompt:
            return {
                "polarity": "negative",
                "severity": random.choice(["low", "medium"]),
                "reasons": ["Linguagem negativa", "Referência a taxas/limitações"],
                "quoted_spans": ["don’t even have", "high fees"],
                "brief": "O comentário expressa frustração e aponta custos/limitações.",
            }

        if "polished_reply" in user_prompt or "rewrite" in user_prompt:
            return {
                "polished_reply": (
                    "Obrigado pelo seu contacto. Lamentamos a experiência descrita. "
                    "Queremos ajudar: pode partilhar mais detalhes (local, data e o que aconteceu)? "
                    "Estamos disponíveis para resolver rapidamente."
                )
            }

        if "summary" in user_prompt or "key_points" in user_prompt:
            return {
                "summary": "Os comentários mencionam conveniência, aceitação variável e taxas; há elogios e queixas.",
                "key_points": [
                    "Conveniência e segurança do Apple Pay",
                    "Aceitação desigual entre países/lojas",
                    "Taxas elevadas impedem adoção",
                    "Elogios a iniciativas técnicas e laboratoriais",
                ],
            }

        return {"raw": "offline-fallback"}


# ----------------------------
# Helpers
# ----------------------------


def ensure_output_dir(base: Path) -> Path:
    out = base / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def sample_balanced(df: pd.DataFrame, label_col: str, per_label: int) -> pd.DataFrame:
    frames = []
    for label, g in df.groupby(label_col):
        frames.append(g.sample(n=min(per_label, len(g)), random_state=42))
    return pd.concat(frames, ignore_index=True) if frames else df.head(0)


def chunked(iterable: Iterable[Any], n: int) -> Iterable[List[Any]]:
    buf: List[Any] = []
    for x in iterable:
        buf.append(x)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


# ----------------------------
# Tasks
# ----------------------------


def task_summarize(
    df: pd.DataFrame,
    client: OpenAIClient,
    text_col: str,
    out_dir: Path,
    group_col: Optional[str] = None,
    auto_topic: bool = False,
    topic_labels: Optional[List[str]] = None,
    max_items_per_group: int = 600,
    chunk_size: int = 40,
    sample: Optional[int] = None,
):
    dfw = df.copy()
    if sample:
        dfw = dfw.sample(n=min(sample, len(dfw)), random_state=42).reset_index(drop=True)

    if auto_topic:
        labels = topic_labels or [
            "elogio",
            "reclamação",
            "sugestão",
            "comparação",
            "off-topic",
        ]
        topics: List[List[str]] = []
        print(f"[Info] A rotular automaticamente temas (labels={labels})...")
        for text in tqdm(dfw[text_col].astype(str).tolist(), desc="Auto-topic"):
            system = "Classifica o texto em 1–2 temas do conjunto dado. Responde só em JSON."
            user = (
                "Temas disponíveis: "
                + ", ".join(labels)
                + "\nTexto: "
                + text[:1000]
                + "\nResponde no formato {\"topics\":[\"...\"]}"
            )
            resp = client.chat_json(system, user, task_name="auto_topic")
            ts = resp.get("topics")
            if not isinstance(ts, list):
                ts = []
            # keep valid labels only
            ts = [t for t in ts if t in labels][:2]
            if not ts:
                # naive fallback: guess by words
                s = text.lower()
                if any(k in s for k in ["love", "great", "amazing", "helpful", "well done", "convenient", "secure"]):
                    ts = ["elogio"]
                elif any(k in s for k in ["bad", "hate", "doesn't", "dont", "drag", "fees", "problem", "issue"]):
                    ts = ["reclamação"]
                else:
                    ts = ["off-topic"]
            topics.append(ts)
        dfw["AutoTopic"] = [";".join(t) for t in topics]
        group_col = "AutoTopic"

    if not group_col or group_col not in dfw.columns:
        raise SystemExit(f"[Error] group-col não especificada ou inexistente. Colunas: {list(dfw.columns)}")

    out_json = {}
    md_lines = [f"# Resumos por {group_col}", ""]

    for gval, gdf in dfw.groupby(group_col):
        texts = gdf[text_col].astype(str).tolist()
        if len(texts) > max_items_per_group:
            texts = texts[:max_items_per_group]

        # Two-stage summarization: micro-summaries -> final
        micro_summaries: List[str] = []
        for chunk in tqdm(list(chunked(texts, chunk_size)), desc=f"{gval}: chunks", leave=False):
            user = (
                "Resumo em PT com bullet points dos seguintes comentários (sê conciso):\n- "
                + "\n- ".join(t[:400] for t in chunk)
                + "\nResponde JSON: {\"summary\":\"...\",\"key_points\":[""" 
            )
            user += "]}"
            resp = client.chat_json(
                system=(
                    "Resumidor de comentários. Extrai ideias principais, problemas e sugestões. "
                    "Usa português europeu e evita redundâncias."
                ),
                user=user,
                schema_hint="{summary: string, key_points: string[]}",
                task_name="summarize_chunk",
            )
            if isinstance(resp, dict):
                s = resp.get("summary") or ""
                kps = resp.get("key_points") or []
                if isinstance(kps, list):
                    s += "\n" + "; ".join([str(x) for x in kps])
                micro_summaries.append(s.strip())
        # Final synthesis
        user_final = (
            "A partir destes micro-resumos, gera um resumo executivo (3-5 bullets) e 1 frase final.\n- "
            + "\n- ".join(ms[:50] for ms in micro_summaries)
            + "\nResponde JSON: {\"summary\":\"...\",\"key_points\":["""
        )
        user_final += "]}"
        resp_final = client.chat_json(
            system="Editor que sintetiza resumos em PT-PT, claro e accionável.",
            user=user_final,
            schema_hint="{summary: string, key_points: string[]}",
            task_name="summarize_final",
        )
        summary = resp_final.get("summary", "")
        key_points = resp_final.get("key_points", [])
        out_json[str(gval)] = {"summary": summary, "key_points": key_points}

        md_lines.append(f"## {gval}")
        if key_points:
            for kp in key_points:
                md_lines.append(f"- {kp}")
        if summary:
            md_lines.append("")
            md_lines.append(summary)
        md_lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"summaries_by_{group_col}"
    (out_dir / f"{base}.json").write_text(json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{base}.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[OK] Gerado: {out_dir / (base + '.md')} e .json")


def task_classify(
    df: pd.DataFrame,
    client: OpenAIClient,
    text_col: str,
    out_dir: Path,
    labels: List[str],
    few_shot: int = 0,
    few_shot_col: Optional[str] = None,
    sample: Optional[int] = None,
):
    dfw = df.copy()
    if sample:
        dfw = dfw.sample(n=min(sample, len(dfw)), random_state=42).reset_index(drop=True)

    few_examples: List[Tuple[str, str]] = []
    if few_shot > 0 and few_shot_col and few_shot_col in dfw.columns:
        per_label = max(1, few_shot // max(1, len(set(labels))))
        try:
            ex_df = sample_balanced(dfw[[text_col, few_shot_col]].dropna(), few_shot_col, per_label)
            for _, r in ex_df.iterrows():
                t = str(r[text_col])
                lab = str(r[few_shot_col])
                if lab in labels:
                    few_examples.append((t, lab))
        except Exception:
            pass

    preds: List[str] = []
    confs: List[float] = []

    for text in tqdm(dfw[text_col].astype(str).tolist(), desc="Classify"):
        eg_str = "".join([f"Exemplo -> Texto: {t[:220]}\nRótulo: {l}\n" for t, l in few_examples])
        user = (
            "Classifica o texto num único rótulo do conjunto. "
            "Responde apenas em JSON no formato {\"label\":\"<label>\",\"confidence\":<0-1>}.\n"
        )
        if eg_str:
            user += "Alguns exemplos rotulados para contexto:\n" + eg_str + "\n"
        user += "Rótulos disponíveis: " + ", ".join(labels) + "\n"
        user += "Texto:\n" + text[:1200]

        resp = client.chat_json(
            system="Classificador textual estrito ao conjunto de rótulos.",
            user=user,
            schema_hint="{label: string, confidence: number}",
            task_name="zero_few_shot_classify",
        )
        lab = resp.get("label")
        if lab not in labels:
            # naive fallback
            s = text.lower()
            lab = labels[0]
            if "positive" in labels and any(k in s for k in ["love", "great", "amazing", "convenient"]):
                lab = "positive"
            if "negative" in labels and any(k in s for k in ["bad", "hate", "terrible", "fees", "drag"]):
                lab = "negative"
        conf = resp.get("confidence")
        try:
            conf = float(conf)
        except Exception:
            conf = 0.6
        preds.append(lab)
        confs.append(conf)

    out = dfw.copy()
    out["pred_label"] = preds
    out["pred_confidence"] = confs
    out_file = out_dir / "zero_few_shot_classification.csv"
    out.to_csv(out_file, index=False)
    print(f"[OK] Gerado: {out_file}")


def task_explain_sentiment(
    df: pd.DataFrame,
    client: OpenAIClient,
    text_col: str,
    out_dir: Path,
    label_col: Optional[str] = None,
    target_label: str = "negative",
    sample: Optional[int] = None,
):
    dfw = df.copy()
    if sample:
        dfw = dfw.sample(n=min(sample, len(dfw)), random_state=42).reset_index(drop=True)

    if label_col and label_col in dfw.columns:
        mask = dfw[label_col].astype(str).str.lower() == target_label.lower()
    else:
        # If we don't have labels, explain all and let LLM infer negativity
        mask = pd.Series([True] * len(dfw))

    rows = dfw[mask]

    results: List[Dict[str, Any]] = []
    for _, r in tqdm(rows.iterrows(), total=len(rows), desc="Explain"):
        text = str(r[text_col])
        user = (
            "Analisa o comentário e explica em poucas linhas PORQUE é negativo, "
            "indicando as passagens que suportam a avaliação. "
            "Responde JSON: {\"polarity\":\"negative|neutral|positive\",\"severity\":\"low|medium|high\",\"reasons\":["""
        )
        user += "],\"quoted_spans\":[""" + "],\"brief\":\"...\"}"
        user += "\nComentário:\n" + text[:1500]
        resp = client.chat_json(
            system="Analista de sentimento (PT-PT) que fornece explicações sucintas e accionáveis.",
            user=user,
            schema_hint="{polarity:string,severity:string,reasons:string[],quoted_spans:string[],brief:string}",
            task_name="explain_sentiment",
        )
        results.append(
            {
                "Comment": text,
                "polarity": resp.get("polarity"),
                "severity": resp.get("severity"),
                "reasons": "; ".join(resp.get("reasons", [])),
                "quoted_spans": "; ".join(resp.get("quoted_spans", [])),
                "brief": resp.get("brief"),
            }
        )

    out = pd.DataFrame(results)
    out_file = out_dir / "sentiment_explanations.csv"
    out.to_csv(out_file, index=False)
    print(f"[OK] Gerado: {out_file}")


def task_rewrite_replies(
    df: pd.DataFrame,
    client: OpenAIClient,
    text_col: str,
    out_dir: Path,
    reply_col: Optional[str] = None,
    locale: str = "pt-PT",
    tone: str = "cordial",
    sample: Optional[int] = None,
):
    dfw = df.copy()
    if sample:
        dfw = dfw.sample(n=min(sample, len(dfw)), random_state=42).reset_index(drop=True)

    has_reply = reply_col and reply_col in dfw.columns
    results = []

    for _, r in tqdm(dfw.iterrows(), total=len(dfw), desc="Rewrite"):
        comment = str(r[text_col])
        original = str(r[reply_col]) if has_reply else None
        if has_reply:
            user = (
                f"Reescreve a resposta de suporte no tom {tone}, {locale}, "
                f"clara, empática, curta (2-4 frases), mantendo o sentido.\nResposta:\n{original}\n"
                f"Contexto do comentário:\n{comment[:800]}\n"
                "Responde JSON: {\"polished_reply\":\"...\"}"
            )
        else:
            user = (
                f"Escreve uma resposta de suporte curta (2-4 frases), {tone}, {locale}, "
                f"referindo-se ao comentário e pedindo os próximos passos claros.\n"
                f"Comentário:\n{comment[:1000]}\n"
                "Responde JSON: {\"polished_reply\":\"...\"}"
            )
        resp = client.chat_json(
            system="Assistente de CX que redige respostas profissionais e empáticas (PT-PT).",
            user=user,
            schema_hint="{polished_reply:string}",
            task_name="rewrite_reply" if has_reply else "compose_reply",
        )
        results.append(
            {
                "Comment": comment,
                "OriginalReply": original if has_reply else "",
                "PolishedReply": resp.get("polished_reply", resp.get("reply", "")),
            }
        )

    out = pd.DataFrame(results)
    out_file = out_dir / "support_rewrites.csv"
    out.to_csv(out_file, index=False)
    print(f"[OK] Gerado: {out_file}")


# ----------------------------
# CLI
# ----------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="LLM-based analyses over Youtube comments dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("command", choices=["summarize", "classify", "explain-sentiment", "rewrite-replies"], help="Task to run")
    p.add_argument("--csv", default="FIA/YoutubeCommentsDataSet.csv", help="Path to CSV input")
    p.add_argument("--text-col", default="Comment", help="Text column name")
    p.add_argument("--output-dir", default="FIA/generative-llm/output", help="Output directory")
    p.add_argument("--openai-model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), help="OpenAI model name")
    p.add_argument("--offline", action="store_true", help="Force offline heuristics (no API calls)")
    p.add_argument("--sample", type=int, default=None, help="Sample N rows for quick runs")

    # summarize
    p.add_argument("--group-col", default=None, help="Column to group by for summarization")
    p.add_argument("--auto-topic", action="store_true", help="Use LLM to assign topics, then summarize by topic")
    p.add_argument("--topic-labels", default=None, help="Comma-separated topic labels for auto-topic mode")
    p.add_argument("--chunk-size", type=int, default=40, help="Comments per micro-summary chunk")
    p.add_argument("--max-items-per-group", type=int, default=600, help="Max comments per group to consider")

    # classify
    p.add_argument("--labels", default="positive,neutral,negative", help="Comma-separated labels for zero-shot classification")
    p.add_argument("--few-shot", type=int, default=0, help="Number of few-shot examples to include (balanced if possible)")
    p.add_argument("--few-shot-col", default=None, help="Column that contains labels for few-shot examples")

    # explain-sentiment
    p.add_argument("--label-col", default=None, help="Column containing labels to filter (e.g., Sentiment)")
    p.add_argument("--target-label", default="negative", help="Label to explain (when label-col provided)")

    # rewrite-replies
    p.add_argument("--reply-col", default=None, help="Column containing existing support replies to rewrite")
    p.add_argument("--locale", default="pt-PT", help="Locale for generated text")
    p.add_argument("--tone", default="cordial", help="Tone for replies")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[Error] CSV não encontrado: {csv_path}")
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cache = JsonlCache(Path("FIA/generative-llm/.cache.jsonl"))
    client = OpenAIClient(model=args.openai_model, cache=cache, offline=args.offline)

    df = load_csv(csv_path)
    if args.text_col not in df.columns:
        print(f"[Error] Coluna de texto '{args.text_col}' não existe. Colunas: {list(df.columns)}")
        return 2

    cmd = args.command
    if cmd == "summarize":
        topics = (
            [s.strip() for s in args.topic_labels.split(",") if s.strip()]
            if args.topic_labels
            else None
        )
        task_summarize(
            df,
            client,
            args.text_col,
            out_dir,
            group_col=args.group_col,
            auto_topic=args.auto_topic,
            topic_labels=topics,
            max_items_per_group=args.max_items_per_group,
            chunk_size=args.chunk_size,
            sample=args.sample,
        )
    elif cmd == "classify":
        labels = [s.strip() for s in args.labels.split(",") if s.strip()]
        task_classify(
            df,
            client,
            args.text_col,
            out_dir,
            labels=labels,
            few_shot=args.few_shot,
            few_shot_col=args.few_shot_col,
            sample=args.sample,
        )
    elif cmd == "explain-sentiment":
        task_explain_sentiment(
            df,
            client,
            args.text_col,
            out_dir,
            label_col=args.label_col,
            target_label=args.target_label,
            sample=args.sample,
        )
    elif cmd == "rewrite-replies":
        task_rewrite_replies(
            df,
            client,
            args.text_col,
            out_dir,
            reply_col=args.reply_col,
            locale=args.locale,
            tone=args.tone,
            sample=args.sample,
        )
    else:
        print(f"[Error] Comando desconhecido: {cmd}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

