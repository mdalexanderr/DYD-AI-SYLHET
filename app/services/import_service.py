"""CSV import of participants. plan.md §11.4.

BATCH 1'S RECORDS ARRIVE AS A SPREADSHEET, and that is the whole reason this exists.
§11.4 lists five steps — upload, map columns, dry run, commit, audit — and four
realities the file will contain: Bangla names from Excel on Windows, zero-width
joiners in conjunct names, duplicate names, and consent written as `ha`/`হ্যাঁ`/`yes`/`1`.

WHAT THIS DELIBERATELY DOES NOT DO
    **A saved column-mapping preset.** The columns are matched by header name against
    a table of aliases below, which covers what an operator actually has (the
    department's own spreadsheet) without a second screen, a second table and a
    second thing to get wrong. If a file arrives whose headers match nothing, the
    dry-run report says so and names the headers it found — which is the information
    the mapping screen would have asked for anyway.

    **A separate error-report download.** The dry run returns the row-by-row report
    to the screen, and a committed import stores its counts on an `imports` row.

WHY CONSENT IS PARSED AND NOT COERCED
    `ha` is not `True`. Consent is the one field where guessing is a legal problem,
    not a data problem: a row whose consent column says something unparseable is
    rejected and reported, and is NEVER imported as "no" — because "no" is a decision
    somebody made about a person, and a typo in a spreadsheet is not that decision.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date
from typing import Any

from app.constants import (
    ConsentSource,
    Education,
    ImportStatus,
    OutcomeType,
)
from app.extensions import db
from app.models import Import, Participant
from app.security import audit
from app.services import participant_service

#: Everything a Bangla CSV from Excel can be encoded in. `utf-8-sig` strips the BOM
#: Excel writes; `cp1252` is what a Windows machine produces when it "saves as CSV"
#: without choosing; `latin-1` is the last resort that cannot fail, so a file in an
#: unknown encoding is still readable as mojibake rather than as an error.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

#: Header aliases, lowercased and stripped of spaces/underscores before lookup. The
#: Bangla spellings are here because the department's own sheet is in Bangla.
COLUMN_ALIASES: dict[str, str] = {
    "name": "name_bn", "name_bn": "name_bn", "নাম": "name_bn", "fullname": "name_bn",
    "name_en": "name_en",
    "slug": "slug",
    "education": "education", "শিক্ষা": "education", "শিক্ষাগত যোগ্যতা": "education",
    "occupation_before": "occupation_before", "পূর্বপেশা": "occupation_before",
    "outcome": "outcome_type", "outcome_type": "outcome_type", "ফলাফল": "outcome_type",
    "outcome_text": "outcome_text", "ফলাফলের বিবরণ": "outcome_text",
    "quote": "quote_bn", "quote_bn": "quote_bn", "উদ্ধৃতি": "quote_bn",
    # A QUOTATION NEEDS ITS OWN PERMISSION (§5.3 rule 5), and the model refuses a row
    # that carries one without it — at flush, as `PublishWithoutConsentError`. Left out
    # of the contract, a spreadsheet with a `quote` column raised that error and took
    # the WHOLE import down with it, because the route only catches `ImportFileError`.
    "quote_consent": "quote_consented", "quote_consented": "quote_consented",
    "উদ্ধৃতির সম্মতি": "quote_consented",
    "batch": "batch", "ব্যাচ": "batch",
    "consent": "consent_publication", "consent_publication": "consent_publication",
    "সম্মতি": "consent_publication",
    "consent_date": "consent_date", "সম্মতির তারিখ": "consent_date",
}

#: §11.4 — consent as an operator writes it. Anything not here is a REJECTED row.
TRUE_WORDS = {"1", "true", "yes", "y", "ha", "haan", "হ্যাঁ", "হা", "হ্যা", "সত্য"}
FALSE_WORDS = {"0", "false", "no", "n", "na", "না", "নাই", "মিথ্যা"}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


class ImportFileError(ValueError):
    """The file cannot be read at all: no header row, unknown columns, empty.

    A distinct exception from a row that fails validation, because the two want
    different things from the operator: this one means fix the file, the other means
    fix a row. The screen shows this as a flash and the report as a table.
    """


def _normalise_header(header: str) -> str:
    """`" Name_BN "` and `"নাম "` both have to match. Spaces and case are noise."""
    return header.strip().strip('"').lower().replace(" ", "").replace("_", "")


#: THE SAME TABLE, KEYED THE WAY A HEADER ARRIVES.
#:
#: `_normalise_header` strips underscores — so `"consent_date"` became `"consentdate"`,
#: and every alias in the table above that contains one was UNREACHABLE. The cost was
#: not a crash but a silence: a spreadsheet with a `consent_date` column imported the
#: person, recorded consent, and DROPPED THE DATE, leaving a row that could not be
#: published and no message anywhere saying why (§5.3 rule 3). `name_bn`,
#: `occupation_before`, `outcome_type`, `outcome_text` and `quote_bn` were all
#: unreachable in the same way.
#:
#: Built from the table rather than written out again: a second hand-written copy is
#: how an alias added above ends up spelled differently here.
COLUMN_ALIASES_NORMALISED: dict[str, str] = {
    _normalise_header(key): value for key, value in COLUMN_ALIASES.items()
}


def _decode(raw: bytes) -> str:
    """Text, trying the encodings in order. Never raises — see `ENCODINGS`."""
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _sniff_delimiter(text: str) -> str:
    """Comma or semicolon, whichever the header row actually uses.

    A Bangla Excel install on a machine with a comma decimal separator writes
    semicolons, and a file parsed with the wrong delimiter has one column whose name
    is the entire header row — which is exactly the failure the dry run reports.
    """
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def _parse_date(raw: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return date.fromisoformat(raw.strip()) if fmt == "%Y-%m-%d" else None
        except ValueError:
            continue
    for fmt in DATE_FORMATS:
        try:
            from datetime import datetime

            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_consent(raw: str) -> bool | None:
    """True, False, or None for "unparseable". None is a REJECTED row, never a False."""
    word = raw.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    return None


def _parse_education(raw: str) -> Education | None:
    word = raw.strip().lower()
    if not word:
        return None
    for member in Education:
        if word == member.value.lower():
            return member
    # The plan's four levels, plus the two words an operator writes instead.
    if word in {"ssc", "এসএসসি", "মাধ্যমিক"}:
        return Education.HSC
    if word in {"graduation", "স্নাতক", "bsc"}:
        return Education.DEGREE
    if word in {"স্নাতকোত্তর", "msc", "masters"}:
        return Education.HONOURS
    return Education.OTHER


def _parse_outcome(raw: str) -> OutcomeType | None:
    word = raw.strip().lower()
    if not word:
        return None
    for member in OutcomeType:
        if word == member.value or word == member.name.lower():
            return member
    return OutcomeType.OTHER


def import_participants(raw: bytes, *, filename: str, commit: bool) -> dict[str, Any]:
    """Parse a CSV, then either report on it or write it.

    Returns a report the screen renders, and records an `imports` row either way — a
    dry run is an audited event too, because "who looked at this file before it was
    imported" is part of the record.
    """
    text = _decode(raw)
    if not text.strip():
        raise ImportFileError("The file is empty.")

    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header_row = next(reader)
    except StopIteration as exc:
        raise ImportFileError("The file has no rows.") from exc

    mapping: dict[int, str] = {}
    unknown: list[str] = []
    for index, header in enumerate(header_row):
        field = COLUMN_ALIASES_NORMALISED.get(_normalise_header(header))
        if field and field not in mapping.values():
            mapping[index] = field
        elif header.strip():
            unknown.append(header.strip())

    if "name_bn" not in mapping.values():
        raise ImportFileError(
            "No 'name' column was found. The columns read were: " + ", ".join(header_row[:12])
        )

    rows: list[dict[str, Any]] = []
    for line_number, raw_row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw_row):
            continue

        cells = {
            mapping[index]: (raw_row[index] if index < len(raw_row) else "")
            for index in mapping
        }
        rows.append({"line": line_number, "cells": cells, "raw": raw_row})

    existing_slugs = {
        slug for (slug,) in db.session.execute(db.select(Participant.slug)).all()
    }

    results: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    seen_names: dict[str, int] = {}

    for row in rows:
        cells = row["cells"]

        # (message, blocks_the_row) — the flag is carried WITH the message rather
        # than inferred later from its wording. The previous version decided a
        # problem was only a warning by searching the Bangla sentence for a phrase,
        # which meant rewording a message silently promoted a warning to a
        # rejection (or the reverse).
        problems: list[tuple[str, bool]] = []

        name_bn = (cells.get("name_bn") or "").strip()
        if not name_bn:
            problems.append(("The name is missing.", True))
        # Duplicate NAMES are reported, not merged: two people can share a name, and
        # the slug is what must be unique. Reporting lets an operator look.
        if name_bn:
            seen_names[name_bn] = seen_names.get(name_bn, 0) + 1
            if seen_names[name_bn] > 1:
                problems.append(("This name already appeared earlier in the file — check it is not a duplicate.", False))

        education = _parse_education(cells.get("education", ""))
        if education is None:
            problems.append(("Education is missing or was not recognised.", True))

        consent = _parse_consent(cells.get("consent_publication", ""))
        if consent is None:
            # THE ONE THAT MATTERS. An unparseable consent value rejects the row; it
            # never becomes "not consented", because that is a decision about a person.
            problems.append(("The consent value could not be read. Write yes or no.", True))

        consent_date = None
        if consent and (cells.get("consent_date") or "").strip():
            consent_date = _parse_date(cells["consent_date"])
            if consent_date is None:
                problems.append(("The consent date could not be read.", True))
        elif consent:
            # §5.3 rule 3: consent with no date is allowed and BLOCKS publication. It
            # is a warning, not a rejection — the paperwork exists.
            problems.append((
                "Consent is recorded without a date — the name will stay unpublished "
                "until it is filled in.",
                False,
            ))

        # A QUOTATION IS A SECOND PERMISSION, and the row is REFUSED rather than
        # quietly stripped of its quote: an operator who supplied a quotation has said
        # something about the person, and dropping it silently is the failure this whole
        # module is most careful about.
        quote_bn = (cells.get("quote_bn") or "").strip() or None
        quote_consented = _parse_consent(cells.get("quote_consented", "")) is True
        if quote_bn and not quote_consented:
            problems.append((
                "A quotation needs its own consent. Write yes in the quote_consent "
                "column, or leave the quote empty.",
                True,
            ))

        batch_raw = (cells.get("batch") or "").strip()
        batch = int(batch_raw) if batch_raw.isdigit() else 1

        slug = (cells.get("slug") or "").strip().lower() or participant_service.slugify(name_bn)
        if slug in existing_slugs:
            problems.append((f"The address '{slug}' is already in use.", True))

        blocking = [message for message, blocks in problems if blocks]

        results.append(
            {
                "line": row["line"],
                "name": name_bn or "—",
                "problems": [message for message, _blocks in problems],
                "blocking": blocking,
            }
        )

        if not blocking:
            prepared.append(
                {
                    "slug": slug,
                    "name_bn": name_bn,
                    "name_en": (cells.get("name_en") or "").strip() or None,
                    "education": education,
                    "occupation_before": (cells.get("occupation_before") or "").strip() or None,
                    "outcome_type": _parse_outcome(cells.get("outcome_type", "")),
                    "outcome_text": (cells.get("outcome_text") or "").strip() or None,
                    "quote_bn": quote_bn,
                    "quote_consented": quote_consented,
                    "batch": batch,
                    "consent": bool(consent),
                    "consent_date": consent_date,
                }
            )
            existing_slugs.add(slug)

    valid = len([row for row in results if not row["blocking"]])
    failed = len(results) - valid

    created = updated = 0
    if commit:
        for item in prepared:
            participant = Participant(
                slug=item["slug"],
                name_bn=item["name_bn"],
                name_en=item["name_en"],
                education=item["education"],
                occupation_before=item["occupation_before"],
                outcome_type=item["outcome_type"],
                outcome_text=item["outcome_text"],
                quote_bn=item["quote_bn"],
                quote_consented=item["quote_consented"],
                batch=item["batch"],
                consent_publication=item["consent"],
                consent_date=item["consent_date"],
                consent_source=ConsentSource.WRITTEN_FORM if item["consent"] else None,
                # NEVER published by an import. A spreadsheet cannot carry the
                # decision to make a person's name public; that is made one record at
                # a time on the detail screen, with the consent panel in front of you.
                is_published=False,
            )
            participant.refresh_search_blob()
            db.session.add(participant)
            created += 1

        db.session.add(
            Import(
                kind="participants",
                file_path=filename,
                file_hash=hashlib.sha256(raw).hexdigest(),
                total_rows=len(results),
                success_rows=created + updated,
                failed_rows=failed,
                is_dry_run=False,
                status=ImportStatus.COMMITTED,
                column_map={str(index): field for index, field in mapping.items()},
            )
        )
        audit.record(
            "import",
            entity_type="Participant",
            extra={"created": created, "failed": failed, "file": filename},
        )
        db.session.commit()
    else:
        db.session.add(
            Import(
                kind="participants",
                file_path=filename,
                file_hash=hashlib.sha256(raw).hexdigest(),
                total_rows=len(results),
                success_rows=valid,
                failed_rows=failed,
                is_dry_run=True,
                status=ImportStatus.DRY_RUN,
                column_map={str(index): field for index, field in mapping.items()},
            )
        )
        db.session.commit()

    return {
        "total": len(results),
        "valid": valid,
        "failed": failed,
        "created": created,
        "updated": updated,
        "rows": results[:200],
        "unknown_headers": unknown,
        "delimiter": delimiter,
        "committed": commit,
        "columns": sorted(set(mapping.values())),
    }


__all__ = ["COLUMN_ALIASES", "ImportFileError", "import_participants"]
