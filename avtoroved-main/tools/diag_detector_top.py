# -*- coding: utf-8 -*-
"""
ВРЕМЕННЫЙ диагностический скрипт (задача «снижение ложных срабатываний»).

Прогоняет все документы указанного (по умолчанию последнего) проекта из
protocol.db через детектор кандидатов ошибок — тот же путь, что и профиль
раздельного исследования (punct_checker.check_with_tokens поверх Stanza) —
и печатает ТОП-30 срабатывающих правил: rule_id, категория, число
срабатываний, 3 примера фрагментов.

Запуск:  python tools/diag_detector_top.py [project_id]
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol import db as protocol_db
from analyzer.stanza_backend import StanzaBackend
from analyzer import punct_checker


def main():
    pdb = protocol_db.ProtocolDB()
    projects = pdb.fetch_projects()
    if not projects:
        print("Нет проектов в protocol.db")
        return
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else projects[0]["id"]
    docs = pdb.fetch_documents(project_id)
    print(f"Проект #{project_id}, документов: {len(docs)}")

    backend = StanzaBackend()
    stats = defaultdict(lambda: {"count": 0, "category": "", "examples": []})
    total = 0

    for doc in docs:
        text = pdb.get_layer(doc["id"], protocol_db.LAYER_CLEANED) or ""
        if not text.strip():
            continue
        tokens = backend.analyze(text)
        errors = punct_checker.check_with_tokens(text, tokens) or []
        print(f"  {doc['filename']}: {len(errors)} срабатываний")
        total += len(errors)
        for e in errors:
            rid = e.rule_ref or f"{e.source}:{e.subtype}"
            s = stats[rid]
            s["count"] += 1
            s["category"] = e.error_type
            frag = (e.fragment or e.context or "").replace("\n", " ").strip()
            if frag and len(s["examples"]) < 3:
                s["examples"].append(frag[:90])

    print(f"\nВсего срабатываний: {total}\n")
    print("ТОП-30 правил:")
    print("-" * 100)
    top = sorted(stats.items(), key=lambda x: -x[1]["count"])[:30]
    for rid, s in top:
        print(f"{rid:24} | {s['category']:16} | {s['count']:4}")
        for ex in s["examples"]:
            print(f"{'':24} |   пример: {ex}")
    print("-" * 100)


if __name__ == "__main__":
    main()
