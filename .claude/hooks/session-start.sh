#!/bin/bash
# Готовит удалённую сессию Claude Code к прогону pytest: системные библиотеки Qt
# и закреплённые Python-зависимости. Локальную машину разработчика не трогает.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# PyQt6 не импортируется без libEGL даже в режиме offscreen.
if ! ldconfig -p | grep -q 'libEGL\.so\.1'; then
  apt-get update -qq || true
  apt-get install -y -qq \
    libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 || true
fi

# Версии берутся только из манифестов репозитория, второго списка пинов нет.
# torch и stanza исключены намеренно: authoroved_core/nlp/stanza_adapter.py
# импортирует их лениво, внутри функции, поэтому весь набор тестов собирается
# и проходит без них, а установка стоила бы нескольких гигабайт диска сессии.
# Для реального анализа Stanza их ставят отдельно по README.
pins="$(mktemp)"
trap 'rm -f "$pins"' EXIT
grep -hvE '^[[:space:]]*(#|-r |torch[=<>]|stanza[=<>]|$)' \
  authoroved_core/requirements.txt authoroved_core/requirements-dev.txt > "$pins"
# Часть базовых пакетов приходит из системных пакетов Debian без метаданных
# RECORD, и обычная установка на них падает с "Cannot uninstall ... installed by
# debian". Повтор с --ignore-installed ставит закреплённую версию поверх, не
# пытаясь удалить системную копию.
if ! python -m pip install -q --disable-pip-version-check -r "$pins"; then
  echo "Обычная установка не прошла; повтор без удаления системных копий."
  python -m pip install -q --disable-pip-version-check --ignore-installed -r "$pins"
fi

# Хук бесполезен, если после него не собираются тесты, поэтому проверяем сразу.
python -c "import PyQt6, yaml, docx, argon2, cryptography, pytest" \
  || { echo "Зависимости установлены не полностью." >&2; exit 1; }

# Тесты интерфейса уже ставят это сами, но инструменты из authoroved_core/tools
# запускаются без дисплея и тоже требуют offscreen.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export QT_QPA_PLATFORM=offscreen' >> "$CLAUDE_ENV_FILE"
fi

echo "Зависимости установлены; torch и stanza пропущены намеренно."
