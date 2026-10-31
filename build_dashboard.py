"""Build a self-contained HTML file using the existing simulation snapshots."""
import json
from pathlib import Path

from simulate import DBF

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = [
    "guide_first_empty", "guide_second_empty", "guide_first_target", "guide_second_target",
    "cheap_first_empty", "cheap_second_empty", "natural_first_empty", "natural_second_empty",
]


def inline_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main():
    stats = {}
    for name in EXPERIMENTS:
        result = json.loads((ROOT / (name + ".json")).read_text(encoding="utf-8"))
        assert result["n"] == 200000
        stats[name] = {k: result[k] for k in ("n", "seed", "failed", "rows", "second", "mulligan", "enemy_target", "ablation")}
    cards = json.loads((ROOT / "cards_zhCN.json").read_text(encoding="utf-8"))
    by_id = {c["dbfId"]: c for c in cards}
    card_data = [{"name": by_id[dbf]["name"], "text": by_id[dbf].get("text", ""), "cost": by_id[dbf]["cost"]} for dbf in DBF]
    template = (ROOT / "dashboard.template.html").read_text(encoding="utf-8")
    result = template.replace("/*__ENGINE__*/", (ROOT / "browser-engine.js").read_text(encoding="utf-8"))
    result = result.replace("/*__STATS__*/null", inline_json(stats)).replace("/*__CARDS__*/null", inline_json(card_data))
    assert "/*__" not in result
    output = ROOT / "nzoth-lab.html"
    output.write_text(result, encoding="utf-8")
    print(f"{output} ({output.stat().st_size:,} bytes)")
    publish = ROOT / "docs"
    publish.mkdir(exist_ok=True)
    (publish / "index.html").write_text(result, encoding="utf-8")
    (publish / ".nojekyll").write_text("", encoding="utf-8")
    print(f"{publish / 'index.html'} (GitHub Pages entry)")


if __name__ == "__main__":
    main()
