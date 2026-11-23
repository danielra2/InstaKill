"""Week 7: the offline evaluation (fixture databases in tmp_path, never instakill.db)."""
import sqlite3

import numpy as np
import pytest

import app.db.database as database
from app.db.movielens import build_dataset, write_dataset
from app.evaluation import offline
from app.evaluation.offline import (
    baseline_table_md,
    evaluate,
    make_snapshot,
    ndcg_at_k,
    results_csv,
)
from app.services.feed_service import FeedService

CUTOFF = "1970-01-02 00:00:00"  # 86_400 seconds after the epoch


def fixture_ratings(seed=0):
    """30 users rating 40 movies over two days: plenty of likes before and after the cut-off."""
    rng = np.random.default_rng(seed)
    rows = []
    for user in range(1, 31):
        for movie in rng.choice(40, size=12, replace=False):
            rows.append({"userId": str(user), "movieId": str(movie + 1),
                         "rating": str(float(rng.choice([2.0, 4.0, 4.5, 5.0]))),
                         "timestamp": str(int(rng.integers(0, 2 * 86_400)))})
    movies = [{"movieId": str(m), "title": f"Movie {m}", "genres": ["Drama", "Comedy", "Action|Drama"][m % 3]}
              for m in range(1, 41)]
    return rows, movies


@pytest.fixture
def fixture_db(tmp_path, monkeypatch):
    path = tmp_path / "fixture.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    data = build_dataset(*fixture_ratings())
    known = {(a, b) for a, b, _ in data.follows}
    for follow in ((1, 2, "1970-01-01 01:00:00"), (2, 3, "1970-01-02 12:00:00")):  # one before T, one after
        if follow[:2] not in known:
            data.follows.append(follow)
    write_dataset(data)
    return path


# ---- the metric ----

def test_ndcg_no_relevant_post_in_the_top_10():
    assert ndcg_at_k([1, 2, 3], {99}) == 0.0
    assert ndcg_at_k([1, 2, 3], set()) == 0.0


def test_ndcg_all_relevant_first_is_perfect():
    assert ndcg_at_k([5, 6, 1, 2], {5, 6}) == pytest.approx(1.0)
    assert ndcg_at_k(list(range(10)), set(range(15))) == pytest.approx(1.0)  # more relevant than 10


def test_ndcg_one_relevant_post_at_position_3():
    # position 3 = index 2: 1/log2(4) = 0.5; ideal = 1/log2(2) = 1
    assert ndcg_at_k([7, 8, 9, 10], {9}) == pytest.approx(0.5)


def test_ndcg_only_counts_the_top_10():
    assert ndcg_at_k(list(range(20)), {15}) == 0.0


# ---- no leakage ----

def test_snapshot_has_nothing_at_or_after_the_cutoff(fixture_db, tmp_path):
    snapshot = tmp_path / "snap.db"
    make_snapshot(fixture_db, snapshot, CUTOFF)
    with sqlite3.connect(snapshot) as conn:
        for table in ('"like"', "post", "follow"):
            late = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE created_at >= ?", (CUTOFF,)).fetchone()[0]
            assert late == 0, table
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0, f"{table} is empty"
        orphans = conn.execute('SELECT COUNT(*) FROM "like" WHERE post_id NOT IN (SELECT id FROM post)').fetchone()[0]
        assert orphans == 0
        assert conn.execute("SELECT COUNT(*) FROM post_tag WHERE post_id NOT IN (SELECT id FROM post)").fetchone()[0] == 0
    with sqlite3.connect(fixture_db) as conn:  # the working database is untouched
        assert conn.execute('SELECT COUNT(*) FROM "like" WHERE created_at >= ?', (CUTOFF,)).fetchone()[0] > 0


def test_relevant_posts_existed_at_the_cutoff_and_were_liked_after(fixture_db, tmp_path):
    report = evaluate(fixture_db, tmp_path, cutoff="1970-01-02")
    with sqlite3.connect(fixture_db) as conn:
        for u in report.users:
            assert u.likes_before >= 3
            for post_id in u.relevant:
                created = conn.execute("SELECT created_at FROM post WHERE id = ?", (post_id,)).fetchone()[0]
                liked = conn.execute('SELECT created_at FROM "like" WHERE user_id = ? AND post_id = ?',
                                     (u.user_id, post_id)).fetchone()[0]
                assert created < CUTOFF <= liked


# ---- determinism ----

def test_two_runs_give_identical_reports(fixture_db, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = evaluate(fixture_db, tmp_path / "a", cutoff="1970-01-02", seed=7)
    second = evaluate(fixture_db, tmp_path / "b", cutoff="1970-01-02", seed=7)
    assert len(first.users) >= 5
    assert results_csv(first) == results_csv(second)
    assert baseline_table_md(first) == baseline_table_md(second)


def test_script_writes_byte_identical_files(fixture_db, tmp_path):
    from tests.scripts_evaluate import main

    out1, out2 = tmp_path / "r1", tmp_path / "r2"
    for out in (out1, out2):
        assert main(["--db", str(fixture_db), "--cutoff", "1970-01-02", "--out", str(out), "--no-dashboard"]) == 0
    for name in ("eval_results.csv", "baseline_table.md"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    header = (out1 / "eval_results.csv").read_text().splitlines()[0]
    assert header == "user_id,strategy,ndcg_at_10,n_relevant,user_group"


# ---- the product is evaluated, not a copy ----

def test_uses_the_same_service_function_as_get_feed(fixture_db, tmp_path, monkeypatch):
    calls = []
    real = FeedService.get_feed

    def counting(self, user_id, limit, strategy):
        calls.append((user_id, limit, strategy.value))
        return real(self, user_id=user_id, limit=limit, strategy=strategy)

    monkeypatch.setattr(FeedService, "get_feed", counting)
    report = evaluate(fixture_db, tmp_path, cutoff="1970-01-02")
    n = len(report.users)
    assert len(calls) == 3 * n  # chronological, for_you, learned for every user
    assert {s for _, _, s in calls} == {"chronological", "for_you", "learned"}
    assert all(limit == offline.K for _, limit, _ in calls)


def test_api_builds_the_service_the_same_way():
    from app.api import feed

    assert feed.get_feed_service().get_feed.__func__ is FeedService.get_feed
