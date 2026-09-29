"""The participants CSV import — the header contract, and the consent date.

WHY THE HEADERS GET THEIR OWN FILE
    The import is the one screen where a mistake is silent in the worst way: the file
    is accepted, the person appears, and something they agreed to — or the DATE they
    agreed it — is quietly missing. That is what happened: `_normalise_header` strips
    underscores before matching, so `"consent_date"` was looked up as `"consentdate"`
    and MISSED, and every alias containing an underscore was unreachable with it.
    `name_bn`, `occupation_before`, `outcome_type`, `outcome_text` and `quote_bn` were
    all silently dropped from a spreadsheet that used the documented column names.

    The first test below is the general one: it walks the alias table and proves every
    alias resolves through the normaliser. A hand-written test per column would have to
    be extended every time a column is added, which is how a check like this gets
    skipped instead of updated.
"""

from __future__ import annotations

import io

from app.constants import ConsentSource, Education
from app.extensions import db
from app.models import Participant
from app.services import import_service


def test_every_documented_alias_survives_header_normalisation():
    """The lookup table and the header normaliser must agree. All of it."""
    table = import_service.COLUMN_ALIASES
    normalised = import_service.COLUMN_ALIASES_NORMALISED

    missing = [
        key
        for key in table
        if normalised.get(import_service._normalise_header(key)) != table[key]
    ]
    assert not missing, (
        "these aliases can never match a real header: " + ", ".join(sorted(missing))
    )

    # The control: the normaliser is not simply returning everything unchanged.
    assert import_service._normalise_header(" Consent_Date ") == "consentdate"


def test_a_header_spelled_the_documented_way_matches():
    """`name_bn` and `consent_publication` are the names in the docs and the export."""
    mapping = {"name_bn": "name_bn", "consent_publication": "consent_publication"}
    for header, expected in mapping.items():
        assert (
            import_service.COLUMN_ALIASES_NORMALISED.get(
                import_service._normalise_header(header)
            )
            == expected
        )


def _csv(*rows: str, header: str | None = None) -> bytes:
    head = header or "name,education,batch,consent,consent_date"
    return ("\n".join([head, *rows]) + "\n").encode("utf-8")


def test_a_consent_date_column_is_honoured(session):
    """The bug that motivated this file: consent recorded, date dropped.

    Left unfixed, the person imports as consented-without-a-date, which is the one state
    that is invisible AND blocks publication (§5.3 rule 3, §5.6): nothing on the site,
    nothing in the list's default filter, and no message anywhere.
    """
    report = import_service.import_participants(
        _csv("আমদানি এক,HSC,1,yes,2026-03-01"), filename="probe.csv", commit=True
    )
    assert report["created"] == 1, report

    person = db.session.execute(
        db.select(Participant).where(Participant.name_bn == "আমদানি এক")
    ).scalars().first()
    assert person is not None
    assert person.consent_publication is True
    assert person.consent_date is not None, "the consent date was silently dropped"
    assert person.consent_date.isoformat() == "2026-03-01"
    assert person.consent_source is ConsentSource.WRITTEN_FORM
    # An import never publishes: a spreadsheet cannot carry that decision.
    assert person.is_published is False


def test_the_underscore_columns_all_arrive(session):
    """Every column whose alias contains an underscore, in one row."""
    header = (
        "name_bn,name_en,education,occupation_before,outcome_type,outcome_text,"
        "quote_bn,quote_consent,batch,consent_publication,consent_date"
    )
    row = (
        "আমদানি দুই,Probe Two,Diploma,শিক্ষার্থী,freelancing,"
        "ফ্রিল্যান্সিং করছেন,উদ্ধৃতি,yes,2,yes,2026-03-02"
    )
    report = import_service.import_participants(
        _csv(row, header=header), filename="probe.csv", commit=True
    )
    assert report["created"] == 1, report

    person = db.session.execute(
        db.select(Participant).where(Participant.name_bn == "আমদানি দুই")
    ).scalars().first()
    assert person.name_en == "Probe Two"
    assert person.education is Education.DIPLOMA
    assert person.occupation_before == "শিক্ষার্থী"
    assert person.outcome_text == "ফ্রিল্যান্সিং করছেন"
    assert person.quote_bn == "উদ্ধৃতি"
    assert person.quote_consented is True
    assert person.batch == 2
    assert person.consent_date.isoformat() == "2026-03-02"


def test_a_quotation_without_its_own_consent_is_rejected_not_dropped(session):
    """§5.3 rule 5, and a crash that took the whole file with it.

    The model refuses a row carrying a quotation without `quote_consented`, at FLUSH, as
    `PublishWithoutConsentError`. The import never set that column, so a spreadsheet with
    a `quote` column raised it — and because the route only catches `ImportFileError`,
    the screen answered 500 and NOTHING in the file was imported. The fix has two halves:
    the column is part of the contract, and a quote without it is a REJECTED ROW.
    """
    report = import_service.import_participants(
        _csv(
            "আমদানি পাঁচ,HSC,1,yes,2026-03-05,উদ্ধৃতি,no",
            header="name,education,batch,consent,consent_date,quote,quote_consent",
        ),
        filename="probe.csv",
        commit=True,
    )
    assert report["failed"] == 1, report
    assert report["created"] == 0
    problems = " ".join(report["rows"][0]["problems"])
    assert "quotation" in problems.lower()
    assert db.session.execute(db.select(Participant)).scalars().first() is None


def test_a_dry_run_stores_nothing(session):
    """The step before the commit. A dry run that wrote rows would be a trap."""
    report = import_service.import_participants(
        _csv("আমদানি তিন,HSC,1,yes,2026-03-03"), filename="probe.csv", commit=False
    )
    assert report["valid"] == 1
    assert db.session.execute(db.select(Participant)).scalars().first() is None


def test_a_consent_value_that_cannot_be_read_rejects_the_row(session):
    """Never guessed. "maybe" is a rejected row, not a "no"."""
    report = import_service.import_participants(
        _csv("আমদানি চার,HSC,1,maybe,"), filename="probe.csv", commit=True
    )
    assert report["failed"] == 1
    assert report["created"] == 0
    assert db.session.execute(db.select(Participant)).scalars().first() is None


def test_a_file_without_a_name_column_is_refused_with_the_headers_it_read(session):
    """A file that cannot be read at all is an operator's mistake, not a 500."""
    import pytest

    with pytest.raises(import_service.ImportFileError) as error:
        import_service.import_participants(
            io.BytesIO(b"alpha,beta\n1,2\n").getvalue(), filename="probe.csv", commit=False
        )
    assert "columns read" in str(error.value).lower()
