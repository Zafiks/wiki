"""Таблицы для страницы «Питомцы» из pets.yml сервера: кого можно приручить, какой бафф даёт, какие облики есть.
Еду для приручения НЕ выводит — это секрет, игроки ищут сами.

    python3 -I tools/gen_pets.py <plugins/VCore/pets.yml> docs/pets.md

Заменяет в pets.md всё между <!-- pets:auto:start --> и <!-- pets:auto:end -->.
"""
import re, sys

MOB_RU = {
    "CHICKEN": "Курица", "CAT": "Кошка", "HORSE": "Лошадь", "MULE": "Мул", "PIG": "Свинья", "COW": "Корова", "CAMEL": "Верблюд",
    "SHEEP": "Овца", "DONKEY": "Осёл", "PARROT": "Попугай", "ARMADILLO": "Броненосец", "PANDA": "Панда", "WOLF": "Волк",
    "BAT": "Летучая мышь", "BEE": "Пчела", "FOX": "Лиса", "GOAT": "Коза", "LLAMA": "Лама", "OCELOT": "Оцелот",
    "POLAR_BEAR": "Белый медведь", "RABBIT": "Кролик", "AXOLOTL": "Аксолотль", "DOLPHIN": "Дельфин", "FROG": "Лягушка",
    "TURTLE": "Черепаха", "ALLAY": "Тихоня", "MOOSHROOM": "Грибная корова", "SNIFFER": "Нюхач", "PHANTOM": "Фантом",
    "VEX": "Вредина", "SPIDER": "Паук", "CREEPER": "Крипер", "ENDERMITE": "Эндермит", "CREAKING": "Скрипун",
    "SILVERFISH": "Чешуйница", "HOGLIN": "Хоглин", "SLIME": "Слизень", "STRIDER": "Лавомерка", "ENDERMAN": "Эндермен",
    "ZOMBIE": "Зомби", "ENDER_DRAGON": "Эндер-дракон", "WITHER": "Иссушитель", "SKELETON": "Скелет", "STRAY": "Зимогор",
    "HUSK": "Кадавр", "CAVE_SPIDER": "Пещерный паук", "MAGMA_CUBE": "Магмовый куб", "BLAZE": "Ифрит", "BREEZE": "Вихрь",
    "PIGLIN": "Пиглин", "ZOMBIFIED_PIGLIN": "Зомбифицированный пиглин", "SNOW_GOLEM": "Снежный голем",
    "IRON_GOLEM": "Железный голем", "SKELETON_HORSE": "Лошадь-скелет", "ZOMBIE_HORSE": "Лошадь-зомби", "WARDEN": "Хранитель",
    "TRADER_LLAMA": "Лама торговца", "GLOW_SQUID": "Светящийся спрут", "SQUID": "Спрут", "TADPOLE": "Головастик",
    "SALMON": "Лосось", "COD": "Треска", "PUFFERFISH": "Иглобрюх", "TROPICAL_FISH": "Тропическая рыба", "WITCH": "Ведьма",
    "VILLAGER": "Житель", "PILLAGER": "Разбойник", "PIGLIN_BRUTE": "Пиглин-громила", "GHAST": "Гаст", "HAPPY_GHAST": "Счастливый гаст",
    "DROWNED": "Утопленник", "ZOGLIN": "Зоглин", "SHULKER": "Шалкер", "GUARDIAN": "Страж", "EVOKER": "Заклинатель",
    "VINDICATOR": "Поборник", "RAVAGER": "Разоритель", "WANDERING_TRADER": "Странствующий торговец", "BOGGED": "Болотник",
}


def section(lines, name):
    i = lines.index(name + ":")
    out = []
    for l in lines[i + 1:]:
        if re.match(r"^\S", l):
            break
        out.append(l)
    return out


def clean(s):
    return re.sub(r"<[^>]*>", "", s).strip("'\" ")


def main():
    yml, md = sys.argv[1:3]
    lines = open(yml, encoding="utf-8").read().split("\n")

    tame = [m.group(1) for l in section(lines, "taming") if (m := re.match(r"^    ([A-Z_]+):\s*$", l))]

    buffs = {}
    cur = None
    for l in section(lines, "buffs"):
        if m := re.match(r"^    ([A-Z_]+):\s*$", l):
            cur = m.group(1)
        elif cur and (m := re.match(r"^      name:\s*(.+)$", l)):
            buffs[cur] = clean(m.group(1))

    looks, cur = [], None
    for l in section(lines, "models"):
        if m := re.match(r"^  ([a-z0-9_]+):\s*$", l):
            cur = {"id": m.group(1), "types": []}
            looks.append(cur)
        elif cur and (m := re.match(r"^    (title|level|permission):\s*(.+)$", l)):
            cur[m.group(1)] = clean(m.group(2))
        elif cur and (m := re.match(r"^    - ([A-Z_]+)$", l)):
            cur["types"].append(m.group(1))
    by_type = {}
    for lk in looks:
        for t in lk["types"]:
            by_type.setdefault(t, []).append(lk)

    def look_txt(lk):
        s = lk.get("title", lk["id"])
        lvl = lk.get("level", "1")
        if lvl != "1":
            s += f" <small>ур. {lvl}</small>"
        if lk.get("permission"):
            s += " ★"
        return s

    rows = []
    for t in sorted(set(tame) | set(by_type), key=lambda x: MOB_RU.get(x, x)):
        if t not in tame:
            continue
        rows.append(f"| {MOB_RU.get(t, t.title())} | {buffs.get(t, '—')} | {', '.join(look_txt(l) for l in by_type.get(t, [])) or '—'} |")

    block = [
        "<!-- pets:auto:start — таблица генерируется tools/gen_pets.py из pets.yml, руками не править -->",
        f"Приручаются **{len(tame)}** видов. ★ — облик открывается донатом, «ур. N» — с какого уровня питомца доступен.", "",
        '<input class="nw-filter" type="search" placeholder="Найти моба или облик…" autocomplete="off">',
        '<p class="nw-filter-empty" hidden>Ничего не нашлось.</p>', "",
        "| Моб | Бафф хозяину | 3D-облики |", "|---|---|---|", *rows, "",
        "<!-- pets:auto:end -->",
    ]
    text = open(md, encoding="utf-8").read()
    new = re.sub(r"<!-- pets:auto:start.*?<!-- pets:auto:end -->", "\n".join(block), text, flags=re.S)
    if new == text and "pets:auto:start" not in text:
        raise SystemExit("в pets.md нет меток <!-- pets:auto:start --> / <!-- pets:auto:end -->")
    open(md, "w", encoding="utf-8").write(new)
    print(f"{md}: {len(rows)} мобов, {len(looks)} обликов")


if __name__ == "__main__":
    main()
