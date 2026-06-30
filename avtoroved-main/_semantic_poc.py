# -*- coding: utf-8 -*-
"""
PoC: сравнение определения семантических полей.

  СТАРЫЙ подход  — thematic_engine: TF-IDF + косинус к словарным центроидам.
  НОВЫЙ подход   — локальный LLM (Ollama), БЕЗ галлюцинаций:
                   * домен определяется по смыслу;
                   * термины-кандидаты выбираются ТОЛЬКО из реальных лемм текста
                     (Stanza), а не генерируются моделью «из головы»;
                   * пост-фильтр выбрасывает всё, чего в тексте не было.

Запуск:
    python _semantic_poc.py                 # на встроенных образцах
    python _semantic_poc.py path/to/file.txt
    set POC_MODEL=qwen2.5:7b && python _semantic_poc.py   # выбрать модель
"""
from __future__ import annotations
import io
import json
import os
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from analyzer.stanza_backend import StanzaBackend, WORD_RE
from analyzer import thematic_engine as thematic_module
from analyzer.thematic_engine import DOMAIN_META

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("POC_MODEL", "qwen2.5:3b")

# Содержательные части речи — кандидаты в доменные термины
CONTENT_POS = {"NOUN", "PROPN", "ADJ", "VERB", "ADV", "X"}
MAX_LEMMAS = 200   # ограничение списка для LLM на больших текстах

SAMPLES = {
    "Юр/право": (
        "Согласно статье 159 УК РФ, мошенничество, совершённое группой лиц по "
        "предварительному сговору, наказывается лишением свободы. Следователь "
        "вынес постановление о возбуждении уголовного дела, потерпевший подал "
        "ходатайство, а защитник заявил об отсутствии состава преступления."
    ),
    "IT": (
        "Мы развернули микросервис на Kubernetes, настроили CI/CD пайплайн и "
        "подключили базу данных PostgreSQL. После рефакторинга API запросы "
        "стали выполняться быстрее, кеширование на Redis снизило нагрузку на "
        "сервер, а логи мы собираем через систему мониторинга."
    ),
    "Бытовой": (
        "Вчера ходили с друзьями в кафе, было очень вкусно и весело. Потом "
        "гуляли в парке, кормили уток, фотографировались. Дома приготовила ужин, "
        "посмотрели фильм и легли спать пораньше, потому что устали за день."
    ),
}

DOMAIN_LIST_STR = "\n".join(f"  - {k}: {v['label']}" for k, v in DOMAIN_META.items())


# ── Старый подход ───────────────────────────────────────────────────────────
def analyze_tokens(stanza: StanzaBackend, text: str):
    tokens = stanza.analyze(text)
    lemmas = [t.lemma.lower() for t in tokens
              if WORD_RE.search(t.text) and t.pos not in ("PUNCT", "NUM")]
    return tokens, lemmas


def old_classify(lemmas):
    res = thematic_module.get().analyze(lemmas)
    return [(d.key, round(d.cosine, 3)) for d in res.top_domains], res


def content_lemmas(tokens):
    """Уникальные содержательные леммы (с сохранением порядка) — кандидаты."""
    seen, out = set(), []
    for t in tokens:
        lem = t.lemma.lower().strip()
        if (t.pos in CONTENT_POS and WORD_RE.search(t.text)
                and len(lem) >= 2 and lem not in seen):
            seen.add(lem)
            out.append(lem)
    return out[:MAX_LEMMAS]


# ── Новый подход (Ollama, constrained) ──────────────────────────────────────
def ollama_available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def llm_classify(text: str, lemmas: list[str], model: str = MODEL) -> dict:
    word_list = ", ".join(lemmas)
    prompt = (
        "Ты — эксперт-лингвист по семантическим полям. Определи тематику текста.\n"
        "Доступные домены (используй ТОЛЬКО эти ключи):\n"
        f"{DOMAIN_LIST_STR}\n\n"
        "СПИСОК СЛОВ из текста (выбирай термины СТРОГО из него, ничего не "
        f"придумывай и не изменяй написание):\n{word_list}\n\n"
        "Верни СТРОГО JSON:\n"
        '{\"domains\": [{\"key\": \"<ключ>\", \"score\": <0..1>}], '
        '\"terms\": {\"<ключ>\": [\"слово_из_списка\", ...]}}\n'
        "domains — до 3 доменов по убыванию. terms — для каждого домена слова "
        "ИЗ СПИСКА, характерные для него."
    )
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "format": "json", "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.loads(r.read().decode("utf-8"))
    try:
        return json.loads(resp.get("response", "{}"))
    except Exception:
        return {"_parse_error": resp.get("response", "")}


# ── Прогон ──────────────────────────────────────────────────────────────────
def run(samples: dict):
    print(f"Модель LLM: {MODEL}  |  Ollama: {OLLAMA_URL}")
    have_llm = ollama_available()
    if not have_llm:
        print("⚠ Ollama недоступен — LLM-часть пропущена.")

    print("== Загрузка Stanza ==")
    st = StanzaBackend()
    st.ensure_loaded(lambda m: None)

    for name, text in samples.items():
        print("\n" + "═" * 70)
        print(f"ТЕКСТ: {name}  ({len(text.split())} слов)")
        print("─" * 70)

        tokens, lemmas = analyze_tokens(st, text)
        old_top, old_res = old_classify(lemmas)
        print("СТАРЫЙ (TF-IDF):  ", old_top or "— ничего выше порога —")
        print(f"   слов сопоставлено со словарями: {old_res.matched_words}/{old_res.total_words}")

        if not have_llm:
            continue

        cand = content_lemmas(tokens)
        cand_set = set(cand)
        try:
            llm = llm_classify(text, cand)
        except Exception as e:
            print("НОВЫЙ (LLM):       ошибка запроса:", e)
            continue
        if "_parse_error" in llm:
            print("НОВЫЙ (LLM):       ошибка JSON:", llm["_parse_error"][:160])
            continue

        doms = [(d.get("key"), round(float(d.get("score", 0)), 2))
                for d in llm.get("domains", [])]
        print("НОВЫЙ (LLM):      ", doms)

        # Пост-фильтр: оставляем только слова, реально присутствующие в тексте
        kept_total, dropped_total = 0, []
        for k, ws in llm.get("terms", {}).items():
            kept = [w for w in ws if w.lower() in cand_set]
            dropped = [w for w in ws if w.lower() not in cand_set]
            kept_total += len(kept)
            dropped_total += dropped
            if kept:
                print(f"   термины [{k}]: {', '.join(kept)}")
        print(f"   ✓ принято кандидатов: {kept_total}   "
              f"✗ отброшено галлюцинаций: {len(dropped_total)}"
              + (f"  {dropped_total}" if dropped_total else ""))

    print("\n" + "═" * 70)
    print("Сравните: домены LLM vs TF-IDF и чистоту терминов-кандидатов "
          "(после фильтра галлюцинаций быть не должно).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], encoding="utf-8") as f:
            run({os.path.basename(sys.argv[1]): f.read()})
    else:
        run(SAMPLES)
