# Recurrence math: month-end clamping is the classic trap.
import datetime as dt

import pytest

from backend.schedule import (add_months, add_years, monthly_equivalent,
                              next_due_date, nth_occurrence, trial_ending_soon,
                              upcoming_dates)

D = dt.date


def test_jan31_plus_one_month_feb_28():
    assert add_months(D(2023, 1, 31), 1) == D(2023, 2, 28)


def test_jan31_plus_one_month_feb_29_leap_year():
    assert add_months(D(2024, 1, 31), 1) == D(2024, 2, 29)


def test_jan31_plus_three_months_apr30():
    assert add_months(D(2023, 1, 31), 3) == D(2023, 4, 30)


def test_aug31_plus_one_month_sep30():
    assert add_months(D(2023, 8, 31), 1) == D(2023, 9, 30)


def test_feb29_yearly_clamps_to_feb28():
    assert add_years(D(2024, 2, 29), 1) == D(2025, 2, 28)


def test_normal_month_unchanged():
    assert add_months(D(2023, 3, 15), 1) == D(2023, 4, 15)


def test_december_wraps_year():
    assert add_months(D(2023, 12, 15), 1) == D(2024, 1, 15)


def test_next_due_date_dispatch():
    assert next_due_date(D(2024, 1, 31), "monthly") == D(2024, 2, 29)
    assert next_due_date(D(2024, 2, 29), "yearly") == D(2025, 2, 28)
    assert next_due_date(D(2024, 1, 1), "custom", 14) == D(2024, 1, 15)


def test_next_due_date_custom_requires_days():
    with pytest.raises(ValueError):
        next_due_date(D(2024, 1, 1), "custom", None)
    with pytest.raises(ValueError):
        next_due_date(D(2024, 1, 1), "custom", 0)
    with pytest.raises(ValueError):
        next_due_date(D(2024, 1, 1), "weekly")


def test_monthly_equivalent_monthly():
    assert monthly_equivalent(9.99, "monthly") == pytest.approx(9.99)


def test_monthly_equivalent_yearly():
    assert monthly_equivalent(120.0, "yearly") == pytest.approx(10.0)


def test_monthly_equivalent_custom_weekly():
    # weekly charge of 10 -> 10 * 365.25/7 / 12 ≈ 43.4
    assert monthly_equivalent(10.0, "custom", 7) == pytest.approx(10.0 * 365.25 / 7 / 12)


def test_monthly_equivalent_custom_requires_days():
    with pytest.raises(ValueError):
        monthly_equivalent(5.0, "custom", None)


def test_trial_ending_soon_window():
    today = D(2024, 6, 1)
    assert trial_ending_soon(D(2024, 6, 4), today) is True   # exactly 3 days
    assert trial_ending_soon(D(2024, 6, 1), today) is True   # today
    assert trial_ending_soon(D(2024, 6, 5), today) is False  # 4 days out
    assert trial_ending_soon(D(2024, 5, 31), today) is False # already ended
    assert trial_ending_soon(None, today) is False


def test_upcoming_dates_rolls_forward_stale_date():
    # Stored next_due is in the past: must roll to the next future occurrence.
    today = D(2024, 6, 15)
    dates = upcoming_dates(D(2024, 1, 31), "monthly", None, 46, today, anchor_day=31)
    assert dates == [D(2024, 6, 30), D(2024, 7, 31)]  # Jul 31 is day 46 of horizon


def test_upcoming_dates_horizon_edge_inclusive():
    today = D(2024, 1, 1)
    dates = upcoming_dates(D(2024, 1, 15), "monthly", None, 60, today)
    assert dates == [D(2024, 1, 15), D(2024, 2, 15)]  # 15 Mar is day 74 > 60


def test_nth_occurrence_monthend_chain():
    # anchored: 2024-01-31 -> 2024-02-29 -> 2024-03-31 -> 2024-04-30
    assert nth_occurrence(D(2024, 1, 31), "monthly", 3, anchor_day=31) == D(2024, 4, 30)


def test_next_due_without_anchor_uses_current_day():
    # No anchor stored: single step still clamps to month end.
    assert next_due_date(D(2024, 1, 31), "monthly") == D(2024, 2, 29)
    # ...but repeated steps from the clamped date would drift without an anchor;
    # that is why the API stores anchor_day at creation time.
