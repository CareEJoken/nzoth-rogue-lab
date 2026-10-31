"""Record reproducible Python reference games for the combo mulligan policy."""
import json
import random

from simulate import ROOT, game


def main():
    baseline = json.loads((ROOT / "browser-parity-cases.json").read_text(encoding="utf-8"))
    seeds = list(dict.fromkeys(case["seed"] for case in baseline))
    cases = []
    for second in (False, True):
        for seed in seeds:
            turn, trace, burned = game(random.Random(int(seed)), second=second,
                                       policy="combo", record=True)
            opening = trace[0]
            cases.append({
                "seed": seed, "mode": "combo", "second": second,
                "turn": turn, "burned": burned,
                "opening": opening["opening"], "rejected": opening["rejected"],
                "hand_after_mulligan": opening["kept_and_replaced"],
                "ends": [{"turn": event["turn"], "mana": event["mana"],
                          "hand": event["hand"], "ice": event["ice_discount"]}
                         for event in trace if event["event"] == "end"],
            })
    output = ROOT / "browser-combo-parity-cases.json"
    output.write_text(json.dumps(cases, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{output}: {len(cases)} cases")


if __name__ == "__main__":
    main()
