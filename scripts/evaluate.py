"""Offline evaluation of the feed strategies (Week 7).

Usage:
    python scripts/evaluate.py [--db instakill.db] [--cutoff 2016-02-01] [--seed 42] [--out reports/]

Writes reports/eval_results.csv, reports/baseline_table.md and reports/dashboard.html.
The first two are byte-identical for the same database and arguments.
Needs the eval extra for the dashboard: pip install -e ".[eval]"
"""
import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.evaluation.offline import baseline_table_md, evaluate, results_csv  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=ROOT / "instakill.db")
    parser.add_argument("--cutoff", help="ISO date/time T (default: when 80 %% of the likes had happened)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    parser.add_argument("--no-dashboard", action="store_true", help="skip the HTML (no matplotlib needed)")
    args = parser.parse_args(argv)

    if not args.db.exists():
        parser.error(f"{args.db} not found: run python scripts/seed_movielens.py first")
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:  # Windows may still hold the snapshot open
        report = evaluate(args.db, Path(work), cutoff=args.cutoff, seed=args.seed, progress=print)

    # newline="\n": the same bytes on Windows and Linux
    (args.out / "eval_results.csv").write_text(results_csv(report), encoding="utf-8", newline="\n")
    (args.out / "baseline_table.md").write_text(baseline_table_md(report), encoding="utf-8", newline="\n")
    written = ["eval_results.csv", "baseline_table.md"]
    if not args.no_dashboard:
        from app.evaluation.dashboard import dashboard_html

        (args.out / "dashboard.html").write_text(dashboard_html(report), encoding="utf-8", newline="\n")
        written.append("dashboard.html")

    print(f"best baseline: {report.best_baseline}")
    for name, iv in report.delta.items():
        print(f"  learned - {report.best_baseline} [{name}]: {iv.mean:+.4f} [{iv.low:+.4f}, {iv.high:+.4f}] -> {iv.verdict}")
    print("wrote " + ", ".join(str(args.out / w) for w in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
