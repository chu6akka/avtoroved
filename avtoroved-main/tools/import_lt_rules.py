"""
tools/import_lt_rules.py — импорт открытых правил LanguageTool в офлайн-базу.

Скачивает из репозитория LanguageTool (LGPL-2.1-or-later,
https://github.com/languagetool-org/languagetool) русские правила и
конвертирует в data/lt_rules_ru.json две категории:

  1. grammar.xml → «простые» правила: все токены паттерна — чистый текст
     или regex, БЕЗ postag/inflected/skip/exception/antipattern (такие
     требуют теггера LT и в офлайн-исполнителе не поддерживаются);
  2. replace.txt → пары «ошибочная фраза = правильная» (опечатки).

Исполняет их analyzer/lt_offline_rules.py без Java и интернета.
Запуск (нужен интернет): python tools/import_lt_rules.py [путь_вывода]

Атрибуция и лицензия исходных правил сохраняются в meta JSON-файла.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BASE = ("https://raw.githubusercontent.com/languagetool-org/languagetool/"
        "master/languagetool-language-modules/ru/src/main/resources/"
        "org/languagetool/rules/ru")

# Категории grammar.xml → тип ошибки программы.
CATEGORY_TO_TYPE = {
    "Грамматика": "Грамматическая",
    "Пунктуация": "Пунктуационная",
    "Типографика": "Пунктуационная",
    "Проверка орфографии": "Орфографическая",
    "Заглавные буквы": "Орфографическая",
    "Логические ошибки": "Лексическая",
    "Стиль": "Стилистическая",
    "Дополнительные правила": "Лексическая",
}


def _fetch(name: str) -> str:
    with urllib.request.urlopen(f"{BASE}/{name}", timeout=60) as r:
        return r.read().decode("utf-8")


def _token_simple(tok: ET.Element) -> bool:
    a = tok.attrib
    if a.get("postag") or a.get("inflected") == "yes":
        return False
    if a.get("skip") or a.get("negate_pos") or a.get("negate") == "yes":
        return False
    if a.get("min") or a.get("max"):
        return False
    if tok.find("exception") is not None:
        return False
    text = (tok.text or "").strip()
    if not text:
        return False
    # Неограниченные шаблоны (.* и т.п.) дают квадратичный бэктрекинг на
    # больших текстах — такие правила не импортируем.
    if a.get("regexp") == "yes" and (".*" in text or ".+" in text
                                     or text in (".", "..")):
        return False
    return True


def _flatten_message(msg: ET.Element | None) -> str:
    if msg is None:
        return ""
    parts = []
    for chunk in msg.itertext():
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _convert_rule(rule: ET.Element, rule_id: str, cat_name: str,
                  etype: str) -> dict | None:
    if rule.find("antipattern") is not None:
        return None
    pat = rule.find("pattern")
    if pat is None:
        return None
    tokens = list(pat.iter("token"))
    if not tokens or not all(_token_simple(t) for t in tokens):
        return None
    case_sensitive = (pat.attrib.get("case_sensitive") == "yes"
                      or rule.attrib.get("case_sensitive") == "yes")
    return {
        "id": rule_id,
        "name": rule.attrib.get("name", ""),
        "category": cat_name,
        "error_type": etype,
        "case_sensitive": case_sensitive,
        "tokens": [{"text": (t.text or "").strip(),
                    "regexp": t.attrib.get("regexp") == "yes"}
                   for t in tokens],
        "message": _flatten_message(rule.find("message"))
                   or (rule.findtext("short") or "").strip()
                   or rule.attrib.get("name", ""),
    }


def convert_grammar(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out: list[dict] = []
    for cat in root.findall(".//category"):
        cat_name = cat.attrib.get("name", "")
        etype = CATEGORY_TO_TYPE.get(cat_name, "Лексическая")
        for child in cat:
            if child.tag == "rule":
                rid = child.attrib.get("id") or child.attrib.get("name", "?")
                conv = _convert_rule(child, rid, cat_name, etype)
                if conv:
                    out.append(conv)
            elif child.tag == "rulegroup":
                # Правила внутри группы наследуют её id (нумеруем варианты).
                gid = child.attrib.get("id", "GROUP")
                gname = child.attrib.get("name", "")
                for i, rule in enumerate(child.findall("rule"), start=1):
                    conv = _convert_rule(rule, f"{gid}[{i}]", cat_name, etype)
                    if conv:
                        if not conv["name"]:
                            conv["name"] = gname
                        out.append(conv)
    return out


def convert_replace(txt: str) -> list[dict]:
    out: list[dict] = []
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, _, rest = line.partition("=")
        right, _, comment = rest.partition("\t")
        wrong, correct = left.strip(), right.strip()
        if not wrong or not correct:
            continue
        out.append({"wrong": wrong, "correct": correct,
                    "note": comment.strip() or "Замена по словарю LT"})
    return out


def main(out_path: str = "data/lt_rules_ru.json") -> None:
    grammar = _fetch("grammar.xml")
    replace = _fetch("replace.txt")
    rules = convert_grammar(grammar)
    replaces = convert_replace(replace)
    payload = {
        "meta": {
            "source": "LanguageTool (languagetool-org/languagetool), модуль ru",
            "license": "LGPL-2.1-or-later",
            "attribution": "https://github.com/languagetool-org/languagetool",
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "grammar_sha256": hashlib.sha256(grammar.encode()).hexdigest(),
            "replace_sha256": hashlib.sha256(replace.encode()).hexdigest(),
            "rules": len(rules),
            "replacements": len(replaces),
            "note": "Только правила без postag/exception/antipattern — "
                    "исполняются офлайн (analyzer/lt_offline_rules.py).",
        },
        "rules": rules,
        "replacements": replaces,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"Записано {out_path}: правил {len(rules)}, замен {len(replaces)}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
