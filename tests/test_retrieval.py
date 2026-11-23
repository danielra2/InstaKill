import numpy as np
import pytest

from app.search.retrieval import cosine_similarity, top_k


def test_cosine_similarity_known_values():
    query = np.array([1.0, 0.0])
    matrix = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [1.0, 1.0]])

    scores = cosine_similarity(query, matrix)

    np.testing.assert_allclose(scores, [1.0, 0.0, -1.0, 1 / np.sqrt(2)])


def test_cosine_similarity_zero_vector_scores_zero():
    scores = cosine_similarity(np.array([1.0, 0.0]), np.array([[0.0, 0.0]]))
    assert scores.tolist() == [0.0]


def test_cosine_similarity_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        cosine_similarity(np.array([1.0, 0.0, 0.0]), np.array([[1.0, 0.0]]))


def test_top_k_orders_by_descending_score():
    query = np.array([1.0, 0.0])
    matrix = np.array([[0.0, 1.0], [1.0, 0.0], [1.0, 1.0]])

    result = top_k(query, matrix, post_ids=[10, 20, 30], k=3)

    assert [post_id for post_id, _ in result] == [20, 30, 10]


def test_top_k_breaks_ties_by_ascending_post_id():
    query = np.array([1.0, 0.0])
    matrix = np.array([[2.0, 0.0], [1.0, 0.0], [5.0, 0.0]])  # all score 1.0

    result = top_k(query, matrix, post_ids=[9, 3, 7], k=3)

    assert [post_id for post_id, _ in result] == [3, 7, 9]


def test_top_k_limits_results_and_handles_k_larger_than_corpus():
    query = np.array([1.0, 0.0])
    matrix = np.array([[1.0, 0.0], [0.0, 1.0]])

    assert len(top_k(query, matrix, [1, 2], k=1)) == 1
    assert len(top_k(query, matrix, [1, 2], k=10)) == 2


def test_top_k_rejects_bad_k():
    with pytest.raises(ValueError):
        top_k(np.array([1.0]), np.array([[1.0]]), [1], k=0)
