"""Week 7: offline evaluation of the feed strategies (a time-split replay).

Protocol (details: docs/evaluation-protocol.md):

1. pick a cut-off T (default: the moment by which 80 % of the likes had happened);
2. copy the database and delete from the copy every like, post (with its tags) and
   follow created at or after T: the snapshot is what the app knew at T;
3. evaluate every user with >= 3 likes before T and >= 1 like after T on a snapshot
   post they did not write;
4. ask the SAME service function as GET /feed (`FeedService.get_feed`) for the user's
   top 10 on the snapshot, with the clock fixed at T; `popularity` is an extra
   baseline that exists only here (likes before T, same candidates);
5. NDCG@10 per user against the posts they liked after T; paired bootstrap over users.

This module is pure Python + NumPy (no pandas, no matplotlib), so the API and the
tests run without the `eval` extra. The dashboard lives in app/evaluation/dashboard.py.
"""
import hashlib
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

import app.db.database as database
from app.db.feed_repository import SqliteFeedRepository
from app.feed.learned import LikeModel, load_model
from app.services.feed_service import FeedService, FeedStrategy

K = 10
CUTOFF_QUANTILE = 0.80
MIN_LIKES_BEFORE = 3
BOOTSTRAP_SAMPLES = 2_000
SQL_TIME = "%Y-%m-%d %H:%M:%S"

STRATEGIES = ("chronological", "popularity", "for_you", "learned")
BASELINES = ("chronological", "popularity", "for_you")
USER_GROUPS = (  # (label, min likes before T, max likes before T) -- the lab's groups
    ("new (<10 likes)", 0, 9),
    ("casual (10-49)", 10, 49),
    ("regular (50-199)", 50, 199),
    ("power (200+)", 200, 10**12),
)
# second slice: how old (at T) the posts are that the user liked after T, median over them.
# 3 years = the freshness half-life of the learned model.
FRESH_DAYS = 3 * 365
AGE_GROUPS = ("likes newer posts (median <3 y)", "likes older posts (median 3+ y)")


# ---------------------------------------------------------------- metric

def ndcg_at_k(ranked: list[int], relevant: set[int] | frozenset[int], k: int = K) -> float:
    """Binary-relevance NDCG@k: sum(rel_i / log2(i + 2)) / the same for a perfect top k."""
    if not relevant:
        return 0.0
    dcg = sum(1.0 / np.log2(i + 2) for i, post in enumerate(ranked[:k]) if post in relevant)
    ideal = sum(1.0 / np.log2(i + 2) for i in range(min(k, len(relevant))))
    return float(dcg / ideal)


def user_group(likes_before: int) -> str:
    for label, low, high in USER_GROUPS:
        if low <= likes_before <= high:
            return label
    raise ValueError(likes_before)


# ---------------------------------------------------------------- cut-off and snapshot

def to_sql_time(value: datetime) -> str:
    return value.strftime(SQL_TIME)


def parse_cutoff(text: str) -> str:
    """'2015-03-01' or '2015-03-01T12:00:00' -> '2015-03-01 12:00:00' (naive UTC, SQLite text)."""
    return to_sql_time(datetime.fromisoformat(text.replace("Z", "")).replace(tzinfo=None))


def default_cutoff(db_path: Path) -> str:
    """The created_at of the like at the 80 % position (likes in time order)."""
    with sqlite3.connect(db_path) as conn:
        times = [row[0] for row in conn.execute('SELECT created_at FROM "like" ORDER BY created_at')]
    if not times:
        raise ValueError("the database has no likes: seed it first")
    return times[min(len(times) - 1, int(CUTOFF_QUANTILE * len(times)))]


def make_snapshot(db_path: Path, snapshot_path: Path, cutoff: str) -> dict[str, int]:
    """Copy the database and delete everything created at or after `cutoff`. Returns what was deleted."""
    shutil.copyfile(db_path, snapshot_path)
    deleted = {}
    with sqlite3.connect(snapshot_path) as conn:
        late_posts = "SELECT id FROM post WHERE created_at >= :t"
        for name, sql in (
            ("likes", f'DELETE FROM "like" WHERE created_at >= :t OR post_id IN ({late_posts})'),
            ("follows", "DELETE FROM follow WHERE created_at >= :t"),
            ("post_tags", f"DELETE FROM post_tag WHERE post_id IN ({late_posts})"),
            ("posts", "DELETE FROM post WHERE created_at >= :t"),
        ):
            deleted[name] = conn.execute(sql, {"t": cutoff}).rowcount
        conn.commit()
    return deleted


@contextmanager
def use_database(path: Path) -> Iterator[None]:
    """Point the app's repositories (app.db.database.DB_PATH) at `path` for a while."""
    previous = database.DB_PATH
    database.DB_PATH = Path(path)
    try:
        yield
    finally:
        database.DB_PATH = previous


# ---------------------------------------------------------------- who is evaluated, and on what

@dataclass(frozen=True)
class EvalUser:
    user_id: int
    likes_before: int
    relevant: frozenset[int]
    group: str
    age_group: str


def select_users(db_path: Path, snapshot_path: Path, cutoff: str) -> list[EvalUser]:
    with sqlite3.connect(snapshot_path) as snap:
        likes_before = dict(snap.execute('SELECT user_id, COUNT(*) FROM "like" GROUP BY user_id'))
        snapshot_posts = {pid: (author, created) for pid, author, created
                          in snap.execute("SELECT id, user_id, created_at FROM post")}
    with sqlite3.connect(db_path) as full:
        later = full.execute(
            'SELECT user_id, post_id FROM "like" WHERE created_at >= ? ORDER BY user_id, post_id',
            (cutoff,),
        ).fetchall()
    relevant: dict[int, set[int]] = {}
    for user_id, post_id in later:
        post = snapshot_posts.get(post_id)
        if post is not None and post[0] != user_id:  # existed at T, and not their own post
            relevant.setdefault(user_id, set()).add(post_id)

    t = datetime.strptime(cutoff, SQL_TIME)
    users = []
    for user_id in sorted(relevant):
        n_before = likes_before.get(user_id, 0)
        if n_before < MIN_LIKES_BEFORE:
            continue
        ages = sorted((t - datetime.strptime(snapshot_posts[p][1], SQL_TIME)).days for p in relevant[user_id])
        median_age = ages[len(ages) // 2]
        users.append(EvalUser(user_id, n_before, frozenset(relevant[user_id]), user_group(n_before),
                              AGE_GROUPS[0] if median_age < FRESH_DAYS else AGE_GROUPS[1]))
    return users


# ---------------------------------------------------------------- the four systems

def popularity_top_k(repository: SqliteFeedRepository, user_id: int, k: int = K) -> list[int]:
    """Evaluation-only baseline: most-liked snapshot posts first, same candidates as GET /feed."""
    counts = repository.post_like_counts()
    candidates = repository.list_candidate_posts(user_id)
    ranked = sorted(candidates, key=lambda p: (-counts.get(p.id, 0), p.id))
    return [p.id for p in ranked[:k]]


def make_service(now: datetime, model: LikeModel) -> FeedService:
    """The production service, as app/api/feed.py builds it, with the clock fixed at T."""
    return FeedService(SqliteFeedRepository(), clock=lambda: now, like_model=model)


def rank_all(users: list[EvalUser], service: FeedService, repository: SqliteFeedRepository
             ) -> dict[str, dict[int, list[int]]]:
    """strategy -> user_id -> top-10 post ids. Must run inside use_database(snapshot)."""
    out: dict[str, dict[int, list[int]]] = {s: {} for s in STRATEGIES}
    for u in users:
        out["popularity"][u.user_id] = popularity_top_k(repository, u.user_id)
        for strategy in ("chronological", "for_you", "learned"):
            result = service.get_feed(user_id=u.user_id, limit=K, strategy=FeedStrategy(strategy))
            out[strategy][u.user_id] = [p.post_id for p in result.posts]
    return out


# ---------------------------------------------------------------- statistics

@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float
    n: int

    @property
    def verdict(self) -> str:
        return "wins" if self.low > 0 else ("loses" if self.high < 0 else "unclear")


def bootstrap_means(values: np.ndarray, rng: np.random.Generator, samples: int = BOOTSTRAP_SAMPLES) -> np.ndarray:
    """values: (n_users, n_columns). The SAME resampled users for every column (paired)."""
    n = len(values)
    idx = rng.integers(0, n, size=(samples, n))
    return values[idx].mean(axis=1)  # (samples, n_columns)


def interval(point: float, resampled: np.ndarray, n: int) -> Interval:
    low, high = np.percentile(resampled, [2.5, 97.5])
    return Interval(float(point), float(low), float(high), n)


@dataclass
class Report:
    cutoff: str
    seed: int
    users: list[EvalUser]
    scores: dict[str, np.ndarray]                 # strategy -> NDCG@10 per user (users order)
    overall: dict[str, Interval] = field(default_factory=dict)
    best_baseline: str = ""
    delta: dict[str, Interval] = field(default_factory=dict)   # slice -> learned - best baseline
    group_means: dict[str, dict[str, Interval]] = field(default_factory=dict)  # slice -> strategy -> interval
    metadata: dict[str, str] = field(default_factory=dict)


def summarise(cutoff: str, seed: int, users: list[EvalUser], scores: dict[str, np.ndarray]) -> Report:
    report = Report(cutoff, seed, users, scores)
    rng = np.random.default_rng(seed)
    matrix = np.column_stack([scores[s] for s in STRATEGIES])
    boot = bootstrap_means(matrix, rng)
    for j, s in enumerate(STRATEGIES):
        report.overall[s] = interval(matrix[:, j].mean(), boot[:, j], len(users))
    report.best_baseline = max(BASELINES, key=lambda s: (report.overall[s].mean, s))
    b = STRATEGIES.index(report.best_baseline)
    learned = STRATEGIES.index("learned")
    diff = matrix[:, learned] - matrix[:, b]
    report.delta["all users"] = interval(diff.mean(), boot[:, learned] - boot[:, b], len(users))

    slices = [(label, [u.group == label for u in users]) for label, _, _ in USER_GROUPS]
    slices += [(label, [u.age_group == label for u in users]) for label in AGE_GROUPS]
    for label, mask in slices:
        mask = np.array(mask, dtype=bool)
        if not mask.any():
            continue
        sub = matrix[mask]
        sub_boot = bootstrap_means(sub, rng)
        report.group_means[label] = {
            s: interval(sub[:, j].mean(), sub_boot[:, j], int(mask.sum())) for j, s in enumerate(STRATEGIES)
        }
        report.delta[label] = interval((sub[:, learned] - sub[:, b]).mean(),
                                       sub_boot[:, learned] - sub_boot[:, b], int(mask.sum()))
    return report


# ---------------------------------------------------------------- metadata

def database_fingerprint(db_path: Path) -> str:
    """sha256 of the table contents in a fixed order (not of the file bytes, which SQLite may vary)."""
    digest = hashlib.sha256()
    with sqlite3.connect(db_path) as conn:
        for table, order in (("user", "id"), ("post", "id"), ("post_tag", "post_id, tag"),
                             ('"like"', "user_id, post_id"), ("follow", "follower_id, followee_id")):
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                digest.update(repr(tuple(row)).encode("utf-8"))
    return digest.hexdigest()[:16]


def code_commit(repo_root: Path) -> str:
    """Last commit that changed the evaluated code (app/, scripts/, models/), not the reports:
    committing the reports afterwards does not change it, so the table stays reproducible."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h", "--", "app", "scripts", "models"],
                             cwd=repo_root, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def training_overlap(db_path: Path, cutoff: str) -> dict[str, str]:
    """Limitation 1: where do the evaluation likes fall relative to the lab's time splits?
    The lab cut ITS likes at the 70 % (val) and 85 % (test) quantiles; the seeded database
    holds the same likes, so the same quantiles of our like times reproduce them."""
    with sqlite3.connect(db_path) as conn:
        times = [r[0] for r in conn.execute('SELECT created_at FROM "like" ORDER BY created_at')]
    lab_val = times[int(0.70 * (len(times) - 1))]
    lab_test = times[int(0.85 * (len(times) - 1))]
    after = [t for t in times if t >= cutoff]
    return {
        "lab train period ends (approx.)": lab_val,
        "lab val period ends (approx.)": lab_test,
        "evaluation likes in the lab's TRAIN period": str(sum(t < lab_val for t in after)),
        "evaluation likes in the lab's VAL period (used to tune the model)": str(sum(lab_val <= t < lab_test for t in after)),
        "evaluation likes in the lab's TEST period": str(sum(t >= lab_test for t in after)),
        "evaluation likes (all, before user filters)": str(len(after)),
    }


# ---------------------------------------------------------------- the whole run

def evaluate(db_path: Path, work_dir: Path, cutoff: str | None = None, seed: int = 42,
             model: LikeModel | None = None,
             progress: Callable[[str], None] = lambda _: None) -> Report:
    db_path = Path(db_path)
    cutoff = parse_cutoff(cutoff) if cutoff else default_cutoff(db_path)
    snapshot = Path(work_dir) / "snapshot.db"
    deleted = make_snapshot(db_path, snapshot, cutoff)
    users = select_users(db_path, snapshot, cutoff)
    if not users:
        raise ValueError(f"no user has >= {MIN_LIKES_BEFORE} likes before {cutoff} and 1 after it")
    progress(f"cut-off {cutoff}: {len(users)} users to evaluate")

    model = model or load_model()
    now = datetime.strptime(cutoff, SQL_TIME)
    with use_database(snapshot):
        ranked = rank_all(users, make_service(now, model), SqliteFeedRepository())
    scores = {s: np.array([ndcg_at_k(ranked[s][u.user_id], u.relevant) for u in users]) for s in STRATEGIES}

    report = summarise(cutoff, seed, users, scores)
    report.metadata = {
        "cut-off T": cutoff,
        "seed": str(seed),
        "bootstrap samples": str(BOOTSTRAP_SAMPLES),
        "users evaluated": str(len(users)),
        "database fingerprint": database_fingerprint(db_path),
        "code commit": code_commit(Path(__file__).resolve().parent.parent.parent),
        "removed from snapshot": ", ".join(f"{v} {k}" for k, v in deleted.items()),
        **training_overlap(db_path, cutoff),
    }
    return report


# ---------------------------------------------------------------- reports

def results_csv(report: Report) -> str:
    lines = ["user_id,strategy,ndcg_at_10,n_relevant,user_group"]
    for i, u in enumerate(report.users):
        for s in STRATEGIES:
            lines.append(f"{u.user_id},{s},{report.scores[s][i]:.6f},{len(u.relevant)},{u.group}")
    return "\n".join(lines) + "\n"


def fmt(iv: Interval) -> str:
    return f"{iv.mean:.4f} [{iv.low:.4f}, {iv.high:.4f}]"


def fmt_signed(iv: Interval) -> str:
    return f"{iv.mean:+.4f} [{iv.low:+.4f}, {iv.high:+.4f}]"


def baseline_table_md(report: Report) -> str:
    lines = [
        "# Offline evaluation: feed strategies",
        "",
        "Generated by `python scripts/evaluate.py`. Protocol: `docs/evaluation-protocol.md`.",
        "NDCG@10 per user, mean over users, 95 % paired bootstrap interval over users.",
        "",
        "## Strategies",
        "",
        "| strategy | mean NDCG@10 [95 % CI] | users |",
        "|---|---|---:|",
    ]
    for s in STRATEGIES:
        iv = report.overall[s]
        lines.append(f"| `{s}` | {fmt(iv)} | {iv.n} |")
    lines += [
        "",
        f"## `learned` minus the best baseline (`{report.best_baseline}`)",
        "",
        "| slice | users | difference [95 % CI] | verdict |",
        "|---|---:|---|---|",
    ]
    for label, iv in report.delta.items():
        lines.append(f"| {label} | {iv.n} | {fmt_signed(iv)} | **{iv.verdict}** |")
    lines += ["", "## Mean NDCG@10 per slice", "",
              "| slice | users | " + " | ".join(f"`{s}`" for s in STRATEGIES) + " |",
              "|---|---:|" + "---|" * len(STRATEGIES)]
    for label, by_strategy in report.group_means.items():
        n = next(iter(by_strategy.values())).n
        lines.append(f"| {label} | {n} | " + " | ".join(fmt(by_strategy[s]) for s in STRATEGIES) + " |")
    lines += ["", "## Run metadata", "", "| key | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in report.metadata.items()]
    return "\n".join(lines) + "\n"
