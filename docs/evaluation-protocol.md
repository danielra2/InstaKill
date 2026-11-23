# Offline evaluation protocol (Week 7)

Code: `app/evaluation/offline.py` (protocol), `app/evaluation/dashboard.py` (charts),
`scripts/evaluate.py` (command line). Output: `reports/`.
Numbers below are from the committed `reports/baseline_table.md` (MovieLens
`ml-latest-small` seeded with `python scripts/seed_movielens.py`, no `--shift-to-now`).

## Question

On our own data, which feed strategy (`chronological`, `popularity`, `for_you`, `learned`)
puts the posts a user is going to like into their top 10, by how much, for which users,
and how sure are we?

## Cut-off and snapshot

We replay the past. The cut-off `T` is, by default, the `created_at` of the like at the
80 % position when all likes are sorted by time (2016-02-04 21:34:53 on the seeded
database); `--cutoff` overrides it. The script copies the database to a temporary file
and deletes from the copy every like, post (with its tags and every like on it) and
follow created at or after `T`. The working `instakill.db` is never modified. Follows
need no re-derivation: the seeder dates a follow at the moment of the 3rd like that
created it, so every follow kept (`created_at < T`) was derived only from likes before
`T`, and every follow that needed a later like is deleted. Users are kept: a user row
carries no behaviour.

## Users

Every user with at least 3 likes before `T` and at least 1 like after `T` on a post that
exists in the snapshot and that they did not write. On the seeded database that is
**25 users**: MovieLens users rate in short bursts, so few are active on both sides of
the cut-off. This small number is the main reason the intervals are wide.

## Candidates

Exactly what `GET /feed` uses: every snapshot post except the user's own posts and the
posts they liked before `T`. Each strategy ranks the whole candidate set (about 7,800 posts).

## The systems

`chronological`, `for_you` and `learned` are produced by `FeedService.get_feed`, the
same function the `GET /feed` endpoint calls, with the repository pointed at the
snapshot and the clock fixed at `T`. Nothing is re-implemented, and the `for_you`
weights, the model and the signal code are unchanged. `popularity` exists only in the
evaluation script (it is not added to the API): the candidates sorted by the number of
likes they had before `T`, ties by ascending `post_id`.

## Relevance

The relevant posts of a user are the snapshot posts they liked after `T`
(binary relevance; every later like counts, not only the next one).

## Metric

NDCG@10 per user: `DCG = sum(rel_i / log2(i + 2))` over the 10 returned positions
(`i = 0..9`), divided by the DCG of a perfect top 10 (all relevant posts first, at most
10 of them). One number per user between 0 and 1; we report the mean over users.

These numbers are **not comparable to the labs**: in Lab 5/7 each moment hides one like
among 99 random items, so guessing gives about 0.05 and popularity about 0.38. Here a
strategy ranks the whole catalogue (about 7,800 candidates) against all of the user's
later likes, which is a much harder question, so all scores are lower.

## Intervals

95 % paired bootstrap over users: 2,000 resamples of the users with replacement
(fixed seed, `--seed`, default 42). The same resampled users are used for every
strategy, so the interval of `learned` minus the best baseline accounts for the users
both are evaluated on. Per slice, the bootstrap is repeated inside the slice. Verdict:
`wins` if the whole interval is above 0, `loses` if it is below 0, otherwise `unclear`.
The best baseline is the baseline with the highest mean overall (`popularity` here).

## Slices

1. User activity before `T`, the lab's groups: `new (<10 likes)`, `casual (10-49)`,
   `regular (50-199)`, `power (200+)`.
2. Our own: the median age, at `T`, of the posts the user liked after `T`:
   `likes newer posts (median <3 y)` vs `likes older posts (median 3+ y)`
   (3 years is the freshness half-life of the learned model).

## Result (seeded database, seed 42)

`learned` has the highest mean NDCG@10 (0.149 vs 0.107 for `popularity`), but the
difference `+0.041 [-0.030, +0.126]` includes 0, so overall the verdict is **unclear**.
It **wins** only for casual users (`+0.058 [+0.005, +0.117]`, 9 users) and is
**worse, but unclear**, for the 2 new users (`-0.158`). `chronological` scores 0 for
everybody: the newest posts at `T` are rarely the ones these users go on to like.

## Known limitations

1. **The model may have seen the future.** `like_model.npz` was trained in Lab 5 on
   MovieLens likes before the lab's `val` cut-off (about 2013-03-16), and its
   hyper-parameters were chosen on the lab's `val` period (up to about 2016-07-10).
   Our database holds the same ratings. Of the 9,716 likes after `T`, **0** fall in
   the training period, but **2,428** (25 %) fall in the period used to choose the
   model, and 7,288 in the lab's test period. So `learned` did not learn from our
   answers, but it was selected for doing well on a quarter of them: its score is
   probably slightly optimistic. A clean check would retrain with the lab's cut-off
   moved before our `T`.
2. **The population is not InstaKill's.** MovieLens is old movies rated years later:
   at `T`, 20 of the 25 users liked posts that were already 3+ years old (median), and
   only 5 liked mostly newer posts. A social network is the opposite: most posts are
   days old. In the "newer posts" slice `learned` is ahead of `popularity`
   (`+0.15`, interval `[-0.05, +0.50]`, 5 users, unclear), which suggests that a
   strategy that uses freshness (`learned`, or `for_you`, whose 24-hour half-life is
   useless on years-old posts) would do better on a fresh feed, but 5 users cannot
   show it. We would need real InstaKill likes, or the seeder's `--shift-to-now`, to
   say more.
3. **Few users.** With 25 users the intervals are wide; most slices have under 10 users.
4. **Ties and floating point.** Ties are broken by `post_id`, so the run is
   deterministic on one machine; another CPU could in principle order two scores that
   differ in the 15th digit differently.

## Reproduce

```bash
pip install -e ".[dev,eval]"
python scripts/seed_movielens.py        # ml-latest-small.zip in the repo folder
python scripts/evaluate.py              # writes reports/
git diff --stat reports/                # baseline_table.md and eval_results.csv: no change
```

The run metadata in the table records the cut-off, seed, number of users, a
fingerprint of the database contents and the last commit that changed the code
(`app/`, `scripts/`, `models/`), so committing the reports does not change it.
