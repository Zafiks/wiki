#!/bin/bash
# Выложить вики: проверить сборку, закоммитить все правки и отправить в GitHub (Zafiks/wiki).
# Дальше GitHub Actions (.github/workflows/deploy.yml) сам соберёт сайт и выложит его на https://wiki.nightworld.ovh
# примерно за минуту.
#
#   ./publish.sh "что поменялось"
#
# Сборку проверяет mkdocs из PATH или из переменной MKDOCS (pip install -r requirements.txt);
# без него проверка пропускается — ошибку тогда покажет GitHub, а сайт останется прежним.
set -euo pipefail
cd "$(dirname "$0")"
MSG="${1:-Обновление вики}"
MKDOCS="${MKDOCS:-mkdocs}"

if command -v "$MKDOCS" >/dev/null 2>&1; then
  out="$(mktemp -d)"
  NO_MKDOCS_2_WARNING=1 "$MKDOCS" build --strict -q -d "$out"
  rm -rf "$out"
  echo "Сборка в порядке."
else
  echo "mkdocs не найден — сборку проверит GitHub."
fi

git pull --rebase --autostash -q
git add -A
if git diff --cached --quiet; then
  echo "Нечего выкладывать: правок нет."
  exit 0
fi
git commit -q -m "$MSG"
git push -q
echo "Отправлено: $(git log -1 --format='%h %s'). Сайт обновится примерно через минуту: https://wiki.nightworld.ovh"
