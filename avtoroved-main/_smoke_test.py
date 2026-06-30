# -*- coding: utf-8 -*-
"""Headless smoke-тест полного пайплайна анализа (без GUI)."""
import sys, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from analyzer.stanza_backend import StanzaBackend, WORD_RE
from analyzer.errors import ErrorAnalyzer, calculate_general_skill
from analyzer.metrics import calculate_metrics
from analyzer import thematic_engine as thematic_module
from analyzer import diagnostic_engine as diag_module

TEXT = (
    "Вчера мы с братаном пошли на каток, было ваще топово. Короче, я думаю, "
    "что нужно обязательно рассказать вам эту историю, потому что она реально "
    "забавная. Когда мы пришли домой, мама приготовила вкусный ужин и мы долго "
    "сидели на кухне. Мой младший братик всё время смеялся и показывал смешные "
    "мемы на телефоне. Надо сказать, что такие вечера запоминаются надолго. "
    "Следует отметить, что семья — это самое важное в жизни каждого человека. "
    "Я считаю, что нельзя забывать о близких людях, ведь они всегда поддержат "
    "тебя в трудную минуту. Таким образом, этот день стал по-настоящему "
    "счастливым, и мы решили, что будем чаще проводить время вместе. "
    "Конечно, жизнь бывает сложной, но рядом с родными любые трудности кажутся "
    "мелочью. Завтра обязательно позвоню бабушке и расскажу ей обо всём."
)

def main():
    print("== Загрузка Stanza ==")
    st = StanzaBackend()
    st.ensure_loaded(lambda m: print("  ", m))
    print("== Морфоанализ ==")
    tokens = st.analyze(TEXT)
    print("  токенов:", len(tokens))

    print("== Метрики ==")
    metrics = calculate_metrics(tokens, TEXT)
    print("  ключи:", list(metrics.keys()))
    print("  всего слов:", metrics.get("дополнительно", {}).get("Всего слов"))

    print("== Ошибки ==")
    ea = ErrorAnalyzer()
    er = ea.analyze(TEXT, tokens)
    print("  ошибок:", len(er.errors), "| уник:", er.total_unique_errors)

    print("== Тематика ==")
    te = thematic_module.get()
    lemmas = [t.lemma.lower() for t in tokens if WORD_RE.search(t.text) and t.pos not in ("PUNCT","NUM")]
    tr = te.analyze(lemmas)
    print("  top:", [(d.key, d.cosine) for d in tr.top_domains])

    print("== Диагностика ==")
    de = diag_module.get()
    dr = de.analyze(tokens, metrics, er, tr)
    print("  объём:", dr.word_count, "| достаточно:", dr.sufficient_volume)
    for name, f in [("пол", dr.gender), ("возраст", dr.age), ("образование", dr.education),
                    ("культура", dr.speech_culture), ("маскировка", dr.masquerade)]:
        if f:
            print(f"  {name}: {f.label} [{f.confidence}] score={f.score:.2f}")
            for e in f.evidence_for[:3]:
                print("      +", e)
    fw = dr.function_words
    if fw:
        print("  служебных слов:", fw.total_function, "| вариативность:", fw.diversity_index)
    print("\n== SMOKE TEST OK ==")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
