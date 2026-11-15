"""Generate/cache 64px icons, then regenerate both catalogues after pack updates.

    .venv/bin/python -I tools/gen_item_icons.py <pack.zip>
    .venv/bin/python -I tools/gen_renames.py <pack.zip> docs/renames.md
    .venv/bin/python -I tools/gen_wardrobe_items.py <pack.zip>
"""
import argparse
import json
from pathlib import Path
import resource
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from item_icons import Catalogue, DEFAULT_COSMETICS, IconIndex, load_cosmetics, render_icon
from gen_renames import grouped_renames


def generate(catalogue, cosmetics, index):
    wanted, failed, rendered, reused = {}, set(), 0, 0
    targets = []
    for group, rows in grouped_renames(catalogue).items():
        targets.extend((rows["sources"][names], f"{group}: {' / '.join(names)}", names[0]) for names in rows["order"])
    for cid, item in cosmetics.items():
        try:
            targets.append((catalogue.wardrobe_node(item), f"гардероб {cid}", None))
        except Exception as e:
            catalogue.errors.add(f"гардероб {cid}: {e}")
    output = index.docs / "assets/items"
    output.mkdir(parents=True, exist_ok=True)
    def checkpoint(files):
        temporary = index.cache.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(files, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(index.cache)

    for node, label, name in targets:
        prepared = None
        try:
            prepared = catalogue.prepare(node, name)
            if prepared is None:
                continue
            key, leaves = prepared
            if key in wanted or key in failed:
                continue
            filename = f"assets/items/{key[:12]}.webp"
            path = index.docs / filename
            valid = False
            if path.is_file():
                # Also recover complete icons left by an interrupted first run.
                try:
                    with Image.open(path) as existing:
                        valid = existing.format == "WEBP" and existing.size == (64, 64)
                        existing.load()
                except (OSError, ValueError):
                    pass
            if valid:
                reused += 1
            else:
                image, flat = render_icon(catalogue, leaves)
                temporary = path.with_suffix(".webp.tmp")
                image.save(temporary, "WEBP", lossless=flat, quality=85, method=6)
                temporary.replace(path)
                image.close()
                rendered += 1
                if rendered % 100 == 0:
                    print(f"Нарисовано {rendered} иконок…", flush=True)
            wanted[key] = filename
            if len(wanted) % 100 == 0:
                checkpoint(index.files | wanted)
        except Exception as e:
            if prepared:
                failed.add(prepared[0])
            catalogue.errors.add(f"{label}: {e}")
        finally:
            prepared = None
            catalogue.release()
    # Only remove generated, hash-named assets. Never touch other wiki images.
    current = set(wanted.values())
    removed = 0
    for path in output.glob("*.webp"):
        if len(path.stem) == 12 and all(c in "0123456789abcdef" for c in path.stem) and path.relative_to(index.docs).as_posix() not in current:
            path.unlink()
            removed += 1
    checkpoint(wanted)
    sizes = [(index.docs / filename).stat().st_size for filename in current]
    total, average = sum(sizes), sum(sizes) / max(1, len(sizes))
    print(f"Иконок: {len(sizes)}; новых: {rendered}; из кэша: {reused}; удалено устаревших: {removed}")
    print(f"Размер: всего {total:,} байт ({total / 1_000_000:.2f} МБ); средний {average:.0f} байт ({average / 1000:.2f} КБ)")
    if total > 3_000_000 or average > 3000:
        print("ВНИМАНИЕ: превышен бюджет 3 МБ / 3 КБ на иконку")
    catalogue.report()
    index.cache.with_name("item-icons-errors.txt").write_text(
        f"Пропущено с ошибкой: {len(catalogue.errors)}\n" + "\n".join(sorted(catalogue.errors)) + "\n",
        encoding="utf-8",
    )
    print(f"Пик памяти процесса: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.1f} МиБ; лимит адресного пространства: 768 МиБ")
    return wanted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--cosmetics", type=Path, default=DEFAULT_COSMETICS)
    args = parser.parse_args()
    with Catalogue(args.pack) as catalogue:
        generate(catalogue, load_cosmetics(args.cosmetics), IconIndex(catalogue))


if __name__ == "__main__":
    main()
