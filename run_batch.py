"""Run independent reproducible experiments, with up to four local workers."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = [
    ("guide_first_empty", 200000, []),
    ("guide_second_empty", 200000, ["--second"]),
    ("guide_first_target", 200000, ["--enemy"]),
    ("guide_second_target", 200000, ["--second", "--enemy"]),
    ("combo_first_empty", 200000, ["--policy", "combo"]),
    ("combo_second_empty", 200000, ["--policy", "combo", "--second"]),
    ("cheap_first_empty", 200000, ["--policy", "cheap"]),
    ("cheap_second_empty", 200000, ["--policy", "cheap", "--second"]),
    ("weighted_first_empty", 100000, ["--weighted"]),
    ("weighted_second_empty", 100000, ["--weighted", "--second"]),
    ("depth3_first_empty", 50000, ["--depth", "3"]),
    ("depth3_second_empty", 50000, ["--depth", "3", "--second"]),
    ("natural_first_empty", 200000, ["--natural-only"]),
    ("natural_second_empty", 200000, ["--natural-only", "--second"]),
]


def main():
    pending = list(EXPERIMENTS)
    running = []
    completed = []
    start = time.perf_counter()
    while pending or running:
        while pending and len(running) < 4:
            name, n, args = pending.pop(0)
            output = (ROOT / (name + ".log")).open("w", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "simulate.py"), "--n", str(n),
                   "--out", name + ".json", *args]
            process = subprocess.Popen(cmd, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            running.append((name, process, output))
            print("START " + name, flush=True)
        for job in running[:]:
            name, process, output = job
            status = process.poll()
            if status is not None:
                output.close()
                running.remove(job)
                if status:
                    for _, p, stream in running:
                        p.terminate()
                        p.wait()
                        stream.close()
                    raise RuntimeError("Experiment failed: " + name)
                completed.append(name)
                print("DONE " + name, flush=True)
        time.sleep(1)
    summary = {"experiments": completed, "games": sum(n for _, n, _ in EXPERIMENTS),
               "elapsed_seconds": time.perf_counter() - start}
    (ROOT / "batch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
