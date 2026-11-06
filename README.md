# Вики NightWorld

Сайт-справка для игроков: как зайти, привязка, команды, питомцы, гардероб, объединения, болезни, донат и т.д.
Сделан на [MkDocs Material](https://squidfunk.github.io/mkdocs-material/): страницы — обычные `.md` в `docs/`,
меню — в `mkdocs.yml` (раздел `nav`). Есть поиск, тёмная/светлая тема, работает с телефона.

## Посмотреть у себя

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/mkdocs serve
```

Откройте http://127.0.0.1:8000 — страницы обновляются сами при сохранении файлов.

## Выложить бесплатно

### Вариант 1. GitHub Pages (рекомендую)

Бесплатно, без рекламы, HTTPS, свой домен, обновляется сам при каждом изменении.

1. Создайте на GitHub публичный репозиторий, например `nightworld-wiki`.
2. Залейте туда содержимое этой папки (вместе со скрытой папкой `.github`):
   ```bash
   cd wiki
   git init -b main
   git add .
   git commit -m "Вики NightWorld"
   git remote add origin https://github.com/<логин>/nightworld-wiki.git
   git push -u origin main
   ```
3. В репозитории: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. Через минуту-две сайт появится по адресу `https://<логин>.github.io/nightworld-wiki/`
   (вкладка **Actions** показывает ход сборки).

Сейчас `site_url` в `mkdocs.yml` = `https://zafiks.github.io/wiki/`. Для другого адреса поменяйте его.

> **Важно:** загрузка через браузер пропускает скрытую папку `.github`. Тогда создайте файл сборки на GitHub вручную:
> **Add file → Create new file**, имя `.github/workflows/deploy.yml`, содержимое — из этой папки.
> Он должен лежать в корне репозитория; сама вики может быть и в корне, и в папке `wiki/`.

**Свой адрес `wiki.nightworld.ovh`:**

1. В DNS домена добавьте запись `CNAME`: `wiki` → `<логин>.github.io`.
2. Создайте файл `docs/CNAME` с одной строкой `wiki.nightworld.ovh`, а в `mkdocs.yml` поставьте `site_url: https://wiki.nightworld.ovh/`.
3. Settings → Pages → Custom domain: `wiki.nightworld.ovh`, поставьте галочку **Enforce HTTPS**.

Править можно прямо на сайте GitHub (карандаш у файла) — после сохранения сайт пересоберётся сам.

### Вариант 2. Cloudflare Pages

Тоже бесплатно, быстрые серверы (в том числе для игроков из России). Workers & Pages → Create → Pages →
подключить тот же GitHub-репозиторий. Настройки сборки:
build command `pip install -r requirements.txt && mkdocs build`, output directory `site`.
Адрес будет `<проект>.pages.dev`, свой домен подключается там же.

### Вариант 3. Без GitHub

Соберите сайт командой `.venv/bin/mkdocs build` — получится папка `site/` с готовым статическим сайтом.
Её можно перетащить на [Netlify Drop](https://app.netlify.com/drop) (бесплатно, адрес `*.netlify.app`)
или положить на любой веб-сервер (например, рядом с донат-сайтом на VPS).

## Что обновлять руками

- `docs/rules.md` — краткая выжимка правил; полный свод в Discord — сверьте или вставьте целиком.
- Ссылки Discord / Telegram — в `mkdocs.yml` (`extra.social`) и на страницах (`grep -rn "discord.gg\|t.me" docs`).
  Сейчас: Discord `discord.gg/yp9KT8t6zQ`, канал `t.me/nightworld_ovh`, бот привязки `@NightWorld_2fa_bot`.
- Цены доната — `docs/donate.md`.

## Что генерируется из файлов сервера

После новой версии ресурс-пака или изменения питомцев запустите:

```bash
# предметы по названию — из ресурс-пака
python3 -I tools/gen_renames.py ../resourcepack/nightworld-rp-vNN.zip docs/renames.md
# таблица питомцев (бафф, 3D-облики) — из pets.yml; еду для приручения скрипт не выводит
python3 -I tools/gen_pets.py ~/Documents/folia/server/plugins/VCore/pets.yml docs/pets.md
```
