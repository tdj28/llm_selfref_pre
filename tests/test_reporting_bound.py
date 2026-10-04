import math

import pytest

from scripts.verify_reporting_bound import bound, paired_t, rounded_counts, verify


def test_published_summary_bound():
    result = bound()
    assert result["candidate_count_pairs"] == 64
    assert result["minimizing_counts"] == [356, 167]
    assert result["minimizing_overlap"] == 0
    assert result["minimum_paired_t"] == pytest.approx(8.627841893823861)
    assert result["minimum_paired_t"] > result["reported_t"]


def test_minimum_overlap_minimizes_t():
    for n in range(2, 14):
        for a in range(1, n + 1):
            for b in range(a):
                overlaps = range(max(0, a + b - n), min(a, b) + 1)
                statistics = [paired_t(n, a, b, overlap) for overlap in overlaps]
                assert statistics[0] == min(statistics)


def test_matches_explicit_sample_variance():
    values = [1, 1, 0, 0, -1]
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    assert paired_t(5, 3, 2, 1) == pytest.approx(mean / math.sqrt(variance / 5))


def test_invalid_margins_and_overlap():
    with pytest.raises(ValueError):
        rounded_counts(1, "0.44")
    with pytest.raises(ValueError):
        paired_t(10, 3, 4, 0)
    with pytest.raises(ValueError):
        paired_t(10, 8, 7, 0)


def test_display_is_bound_to_manuscript():
    verify()
