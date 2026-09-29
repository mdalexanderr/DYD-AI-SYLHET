"""CSV export of participants. plan.md §11.3.

EXPORT THE FILTERED SET, NOT THE TABLE
    An operator exports what they are looking at. Exporting everything and letting
    them filter in Excel is how a list of withdrawn names ends up in an email.

WATERMARKED WITH WHO AND WHEN
    §11.3 asks for it, and the reason is the one that matters for a file containing
    people's names: a CSV with no provenance is a file that cannot be accounted for
    once it has left the admin, and this one is a government record about named
    individuals. The first row names the exporter, the timestamp and the filters.

WHAT IS NOT IN THE FILE
    §5.1's prohibited set — photographs, phone numbers, email addresses, NID or birth
    registration numbers, dates of birth, blood group, full address, guardian names
    and exam marks. None of them is a column, so none of them can be exported by
    accident, which is a stronger guarantee than a rule about which columns to tick.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Sequence

from flask import Response, current_app
from flask_login import current_user

from app.filters import bn_date

#: The same four facts §5 says may be published, plus the bookkeeping an operator
#: needs to reconcile a file against the database. Ordered as the list screen reads.
COLUMNS = (
    ("slug", "ঠিকানা"),
    ("name_bn", "নাম"),
    ("name_en", "Name (English)"),
    ("education", "শিক্ষাগত যোগ্যতা"),
    ("occupation_before", "প্রশিক্ষণের আগে"),
    ("outcome_type", "ফলাফল"),
    ("outcome_text", "ফলাফলের বিবরণ"),
    ("batch", "ব্যাচ"),
    ("consent_publication", "সম্মতি"),
    ("consent_date", "সম্মতির তারিখ"),
    ("is_published", "প্রকাশিত"),
)

YES = "হ্যাঁ"
NO = "না"


def participants_csv(
    participants: Sequence[Any], filters: dict[str, str] | None = None
) -> Response:
    """The filtered rows as a downloadable CSV, with its watermark.

    The watermark needs the request context — who exported it and when — which is why
    this returns a response object rather than a string: the two facts an audit of an
    exported file needs are only knowable here, and threading them back out to the
    route to be assembled into a header is how a file ends up without them.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    # ── The watermark ─────────────────────────────────────────────────────────
    from app.models.base import utcnow

    stamp = bn_date(utcnow(), style="short")
    exporter = getattr(current_user, "email", None) or "—"
    active = ", ".join(f"{key}={value}" for key, value in (filters or {}).items() if value)
    writer.writerow([f"রপ্তানি: {exporter} · {stamp} · ফিল্টার: {active or 'কোনোটি নয়'}"])
    writer.writerow([
        f"{current_app.config['APP_NAME']} — ব্যক্তিগত তথ্য, সাবধানে সংরক্ষণ করুন।"
    ])
    writer.writerow([])

    writer.writerow([label for _key, label in COLUMNS])
    for participant in participants:
        row = []
        for key, _label in COLUMNS:
            value = getattr(participant, key, None)
            if key == "consent_date":
                row.append(bn_date(value, style="short") if value else "")
            elif key in ("consent_publication", "is_published"):
                row.append(YES if value else NO)
            else:
                row.append("" if value is None else str(value))
        writer.writerow(row)

    filename = f"participants-{stamp.replace('/', '-')}.csv"
    # utf-8-sig, so Excel on Windows opens Bangla names correctly instead of as
    # mojibake — the same encoding the import accepts, in the other direction.
    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["COLUMNS", "participants_csv"]
