"""Week 7: the static evaluation dashboard (one self-contained HTML file).

Needs matplotlib (the `eval` extra). Charts are embedded as base64 PNG, there is no
JavaScript and no server: double-click reports/dashboard.html to open it.
"""
import base64
import html
import io

import matplotlib

matplotlib.use("Agg")  # no window, works on any machine
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

from app.evaluation.offline import (  # noqa: E402
    AGE_GROUPS,
    STRATEGIES,
    USER_GROUPS,
    Report,
    baseline_table_md,
)

# the same colour for the same strategy in every chart (Okabe-Ito, colour-blind safe)
COLORS = {"chronological": "#999999", "popularity": "#E69F00", "for_you": "#56B4E9", "learned": "#009E73"}


def _png(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _errors(intervals):
    return [[iv.mean - iv.low for iv in intervals], [iv.high - iv.mean for iv in intervals]]


def chart_strategies(report: Report) -> str:
    ivs = [report.overall[s] for s in STRATEGIES]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(STRATEGIES, [iv.mean for iv in ivs], yerr=_errors(ivs), capsize=6,
           color=[COLORS[s] for s in STRATEGIES])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("mean NDCG@10 (95 % CI)")
    ax.set_xlabel("feed strategy")
    ax.set_title(f"Which strategy puts later likes in the top 10? ({ivs[0].n} users)")
    return _png(fig)


def chart_delta(report: Report) -> str:
    labels = list(report.delta)
    ivs = [report.delta[k] for k in labels]
    limit = max(0.05, *(abs(v) for iv in ivs for v in (iv.low, iv.high)))
    cmap, norm = plt.get_cmap("RdBu"), TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(labels) + 1.4))
    y = list(range(len(labels)))[::-1]
    ax.barh(y, [iv.mean for iv in ivs], xerr=_errors(ivs), capsize=4,
            color=[cmap(norm(iv.mean)) for iv in ivs], edgecolor="#333333", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y, [f"{k} (n={iv.n})" for k, iv in zip(labels, ivs)])
    ax.set_xlim(-limit * 1.1, limit * 1.1)
    ax.set_xlabel(f"NDCG@10 of learned minus {report.best_baseline} (95 % CI)")
    ax.set_title(f"Where does learned beat the best baseline ({report.best_baseline})?")
    return _png(fig)


def chart_groups(report: Report) -> str:
    groups = [label for label, _, _ in USER_GROUPS if label in report.group_means]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.8 / len(STRATEGIES)
    for j, s in enumerate(STRATEGIES):
        ivs = [report.group_means[g][s] for g in groups]
        xs = [i + (j - (len(STRATEGIES) - 1) / 2) * width for i in range(len(groups))]
        ax.bar(xs, [iv.mean for iv in ivs], width, yerr=_errors(ivs), capsize=3, color=COLORS[s], label=s)
    ax.set_xticks(range(len(groups)), [f"{g}\nn={report.group_means[g][STRATEGIES[0]].n}" for g in groups])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("mean NDCG@10 (95 % CI)")
    ax.set_xlabel("user activity before the cut-off")
    ax.set_title("Which users does each strategy serve well?")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    return _png(fig)


def chart_freshness(report: Report) -> str:
    groups = [g for g in AGE_GROUPS if g in report.group_means]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    width = 0.8 / len(STRATEGIES)
    for j, s in enumerate(STRATEGIES):
        ivs = [report.group_means[g][s] for g in groups]
        xs = [i + (j - (len(STRATEGIES) - 1) / 2) * width for i in range(len(groups))]
        ax.bar(xs, [iv.mean for iv in ivs], width, yerr=_errors(ivs), capsize=3, color=COLORS[s], label=s)
    ax.set_xticks(range(len(groups)), [f"{g}\nn={report.group_means[g][STRATEGIES[0]].n}" for g in groups])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("mean NDCG@10 (95 % CI)")
    ax.set_xlabel("age at the cut-off of the posts the user liked later")
    ax.set_title("Does the winner change for users who like newer posts?")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    return _png(fig)


def _md_table_to_html(md: str) -> str:
    """Tiny converter for the pipe tables and headings of baseline_table.md (no dependency)."""
    out, rows = [], []

    def flush():
        if rows:
            head, *body = rows
            out.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table>")
            rows.clear()

    for line in md.splitlines():
        if line.startswith("|"):
            cells = [html.escape(c.strip()).replace("**", "") for c in line.strip("|").split("|")]
            if not all(set(c) <= set("-:") for c in cells):
                rows.append([c.replace("`", "") for c in cells])
            continue
        flush()
        if line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:]).replace('`', '')}</h2>")
        elif line.startswith("# "):
            continue
        elif line.strip():
            out.append(f"<p>{html.escape(line).replace('`', '')}</p>")
    flush()
    return "\n".join(out)


def dashboard_html(report: Report) -> str:
    charts = [
        ("1. Strategies", chart_strategies(report)),
        ("2. learned vs the best baseline, per slice", chart_delta(report)),
        ("3. By user activity", chart_groups(report)),
        ("4. By age of the liked posts", chart_freshness(report)),
    ]
    figures = "\n".join(
        f'<figure><figcaption>{html.escape(title)}</figcaption>'
        f'<img alt="{html.escape(title)}" src="data:image/png;base64,{data}"></figure>'
        for title, data in charts
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InstaKill offline evaluation</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; color: #222; background: #fff; }}
h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; font-size: 0.85rem; margin: 8px 0; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }} th {{ background: #f3f3f3; }}
figure {{ margin: 24px 0; }} figcaption {{ font-weight: 600; margin-bottom: 6px; }}
img {{ max-width: 100%; height: auto; }}
.note {{ color: #555; font-size: 0.9rem; }}
</style></head><body>
<h1>InstaKill: offline evaluation of the feed strategies</h1>
<p class="note">Static page generated by <code>python scripts/evaluate.py</code>. Not served by the API.
Protocol: <code>docs/evaluation-protocol.md</code>. Cut-off {html.escape(report.cutoff)}, {len(report.users)} users, seed {report.seed}.</p>
{figures}
{_md_table_to_html(baseline_table_md(report))}
</body></html>
"""
