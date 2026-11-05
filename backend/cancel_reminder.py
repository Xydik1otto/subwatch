# Cancel reminders за N днів до списання.
#
# "Plan to cancel" зберігає жорстку дату (cancel_deadline), але тримати її
# актуальною вручну — виснажливо: після mark-paid списокання відкочується
# на цикл вперед і дедлайн "старає". Тут дедлайн виводиться автоматично:
# next_due_date - days_before, і перераховується при кожному mark-paid.
from __future__ import annotations

import datetime as dt


def deadline_for(next_due: dt.date, days_before: int) -> dt.date:
    """Дедлайн скасування: за `days_before` днів ДО списання.

    days_before >= 1 (скасувати треба ДО списання, а не в день списання —
    тоді сервіс уже списав гроші).
    """
    if days_before < 1:
        raise ValueError("days_before must be >= 1")
    return next_due - dt.timedelta(days=days_before)


def due_reminders(rows, today: dt.date, days: int) -> list[dict]:
    """Заплановані скасування, чий дедлайн настає протягом `days` днів.

    rows: sqlite3.Row-подібні рядки з cancel_planned/cancel_deadline.
    Списання в минулому (прострочений дедлайн) НЕ включаються — їх видно
    окремо у /api/to-cancel. Сортування: спочатку найближчий дедлайн.
    """
    out = []
    for r in rows:
        if not r["cancel_planned"] or not r["cancel_deadline"]:
            continue
        deadline = dt.date.fromisoformat(r["cancel_deadline"])
        left = (deadline - today).days
        if 0 <= left <= days:
            out.append({
                "id": r["id"],
                "name": r["name"],
                "amount": r["amount"],
                "currency": r["currency"],
                "cancel_deadline": r["cancel_deadline"],
                "next_due_date": r["next_due_date"],
                "days_left": left,
            })
    out.sort(key=lambda d: (d["days_left"], d["name"].lower()))
    return out
