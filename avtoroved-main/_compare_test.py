# -*- coding: utf-8 -*-
"""Проверка comparison_engine на реальном анализе двух текстов (без GUI)."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from analyzer.stanza_backend import StanzaBackend
from analyzer.metrics import calculate_metrics, compare_texts
from analyzer.errors import ErrorAnalyzer, calculate_general_skill
from analyzer import stratification_engine as strat_module
from analyzer import comparison_engine as ce

# Текст A и B — условно «один автор» (похожий стиль); C — иной автор/регистр.
A = ("Следует отметить, что развитие технологий существенно меняет общество. "
     "Когда мы анализируем эти процессы, необходимо учитывать множество факторов. "
     "Таким образом, грамотное управление изменениями становится ключевой задачей "
     "современного руководителя, который стремится к устойчивому результату.")
B = ("Необходимо подчеркнуть, что цифровизация преобразует привычные институты. "
     "Анализируя происходящее, мы обязаны принимать во внимание различные обстоятельства. "
     "Следовательно, продуманное руководство процессом оказывается важнейшей целью "
     "ответственного управленца, ориентированного на долгосрочный эффект.")
C = ("Короче, вчера такая жесть была, я вообще в шоке если честно. Пошли с пацанами "
     "гулять, а там движ нереальный, все орут, музыка долбит. Ну мы поугарали конечно, "
     "потом ещё в кафешку зашли, норм посидели. Завтра опять может куда-нибудь рванём.")


def build(st, ea, se, name, text):
    tokens = st.analyze(text)
    metrics = calculate_metrics(tokens, text)
    er = ea.analyze(text, tokens)
    if not er.general_skill_level:
        (er.general_skill_level, er.general_skill_desc,
         er.total_unique_errors) = calculate_general_skill(er.errors, er.total_words)
    sr = None
    try:
        sr = se.analyze(text)
    except Exception as e:
        print("  strat error:", e)
    return ce.build_bundle(name, text, tokens, metrics, er, sr), tokens


def run_pair(st, ea, se, name1, t1, name2, t2):
    b1, tok1 = build(st, ea, se, name1, t1)
    b2, tok2 = build(st, ea, se, name2, t2)
    aux = compare_texts(tok1, tok2, t1, t2)
    res = ce.compare(b1, b2, aux)

    print("\n" + "█" * 64)
    print(f"ПАРА: {name1}  ⟷  {name2}")
    print("█" * 64)
    print(f"Всего признаков: {res.total_features} | "
          f"совпадений: {len(res.matches)} | различий: {len(res.diffs)}")
    print(f"Высокоинформ.: совп {res.high_informative_matches} / "
          f"разл {res.high_informative_diffs} (порог {res.threshold})")
    print("По уровням:", res.level_summary)

    for lvl in ("НН", "НС", "НСВ"):
        print(f"\n── {lvl} ──")
        for f in res.by_level("match", lvl):
            print(f"  ✓ {f.name}: «{f.value1}» = «{f.value2}»"
                  + (f"  [{f.note}]" if f.note else ""))
        for f in res.by_level("diff", lvl):
            print(f"  ✗ {f.name}: «{f.value1}» ≠ «{f.value2}»"
                  + (f"  [{f.note}]" if f.note else ""))

    print("\nВспомогательные метрики:",
          {k: aux[k] for k in ("overall", "jaccard", "pos_similarity",
                               "bigram_similarity") if k in aux})
    print("ПОДСКАЗКА:", res.hint)
    print("  основание:", "; ".join(res.hint_basis) or "—")
    print("Окончательный вывод формулирует эксперт.")


def main():
    print("Загрузка Stanza...")
    st = StanzaBackend(); st.ensure_loaded(lambda m: None)
    ea = ErrorAnalyzer()
    se = strat_module.get()
    run_pair(st, ea, se, "A (книжный)", A, "B (книжный)", B)
    run_pair(st, ea, se, "A (книжный)", A, "C (разговорный)", C)
    print("\n== TEST OK ==")


if __name__ == "__main__":
    main()
