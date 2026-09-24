#!/usr/bin/env python3
"""Render the design harness (the kitchen sink) — plan.md step 1.7.

    python tools/render-design.py [--open]

Reads  design-src/kitchen-sink-src.html   (Jinja, contains the real macros)
Writes design-src/kitchen-sink.html       (static, opened in a browser)

WHY THIS EXISTS
    §7.7 requires every component to be visible in all its real states. A component
    macro that has only ever been read is not a component — the interesting cases
    are the empty table, the withdrawn consent badge, the suppressed statistic and
    the form with six errors, and none of those appear on a happy-path page.

    Rendering through the REAL macros, rather than hand-written HTML, is what makes
    this a test: if a macro is broken the harness fails to render, and if a token
    is wrong the harness shows it.

WHY IT IS NOT A FLASK COMMAND
    The harness must render before the app exists (this is phase 1) and without a
    request context. It injects the same two globals the app factory will inject —
    `static_url` and `asset_url` — so the macros themselves are identical in both
    places. If a macro needs a third global, this file and the app factory must
    both be updated, and that is the point: the difference will show up here first.

Bangla fixtures are written as literal Bangla numerals rather than formatted from
ints, for the same reason the macros take display strings: number formatting is a
view concern (`bn_num`, §9.2) and duplicating it here would create a second
implementation free to drift from the real one.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

try:
    from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined
except ImportError:
    print("render-design: Jinja2 is missing. Run inside the venv:\n"
          "  .venv\\Scripts\\python.exe tools\\render-design.py", file=sys.stderr)
    raise SystemExit(1) from None

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIRS = [ROOT / "app/templates", ROOT / "design-src"]
SOURCE = "kitchen-sink-src.html"
OUTPUT = ROOT / "design-src/kitchen-sink.html"

# ---------------------------------------------------------------------------
# FIXTURES
#
# Real content wherever the plan gives it: the six module names and the programme
# facts come from plan.md §3.1, so the harness cannot flatter a component with
# placeholder text that happens to fit. Bangla names are real Bangla names,
# including a conjunct (বিষ্ণুপ্রসাদ) and a zero-width joiner case, because those
# are the ones that break a layout (§19.3).
# ---------------------------------------------------------------------------

NAV = [
    {"href": "/", "label": "হোম", "slug": "home"},
    {"href": "/course", "label": "কোর্স", "slug": "course"},
    {"href": "/batch-1", "label": "ব্যাচ ১", "slug": "batch-1"},
    {"href": "/gallery", "label": "গ্যালারি", "slug": "gallery"},
    {"href": "/about", "label": "আমাদের সম্পর্কে", "slug": "about"},
    {"href": "/contact", "label": "যোগাযোগ", "slug": "contact"},
]

MODULES = [
    {"title_bn": "প্রম্পট ইঞ্জিনিয়ারিং", "hours": "৪০", "description_bn": "কার্যকর প্রম্পট লেখা ও পরিমার্জন।"},
    {"title_bn": "এআই কনটেন্ট ক্রিয়েশন", "hours": "৫০", "description_bn": "লেখা, ছবি ও ভিডিও কনটেন্ট তৈরি।"},
    {"title_bn": "জেনারেটিভ এআই টুলস", "hours": "৫০", "description_bn": "প্রচলিত জেনারেটিভ মডেল ও তাদের ব্যবহার।"},
    {"title_bn": "এআই প্রোডাক্টিভিটি", "hours": "৪০", "description_bn": "দৈনন্দিন কাজে এআই সহায়ক ব্যবহার।"},
    {"title_bn": "ডেটা অ্যানালাইসিস", "hours": "৫০", "description_bn": "ডেটা বিশ্লেষণ ও ভিজুয়ালাইজেশন।"},
    {"title_bn": "এআই ফ্রিল্যান্সিং", "hours": "৭০", "description_bn": "অনলাইন মার্কেটপ্লেসে এআই সেবা বিক্রি।"},
]

# A conjunct name, a zero-width-joiner name, a 4-word name, and a mixed pair.
PARTICIPANTS = [
    {"name_bn": "রূপা আক্তার", "name_en": "Rupa Akter",
     "href": "/batch-1/rupa-akter",
     "meta": ["এইচএসসি", "এর আগে: শিক্ষার্থী"],
     "outcome_text": "বর্তমানে অনলাইন মার্কেটপ্লেসে কাজ করছেন।",
     "outcome_label": "ফ্রিল্যান্সিং"},
    {"name_bn": "বিষ্ণুপ্রসাদ দাশ", "name_en": None,
     "href": "/batch-1/bishnuprasad-das",
     "meta": ["স্নাতক", "এর আগে: কৃষি"],     "outcome_text": "স্থানীয় একটি প্রতিষ্ঠানে প্রশিক্ষক হিসেবে যোগ দিয়েছেন।",
     "outcome_label": "শিক্ষকতা"},
    {"name_bn": "সাইফুল ইসলাম চৌধুরী", "name_en": None,
     "href": "/batch-1/saiful-islam-chowdhury",
     "meta": ["ডিপ্লোমা"],
     "outcome_text": None,
     "outcome_label": "কর্মসংস্থান"},
    {"name_bn": "নুসরাত জাহান", "name_en": "Nusrat Jahan",
     "href": "/batch-1/nusrat-jahan",
     "meta": ["সম্মান", "এর আগে: গৃহিণী"],
     "outcome_text": "নিজের একটি ছোট ব্যবসা শুরু করেছেন।",
     "outcome_label": "ব্যবসা"},
    {"name_bn": "মোঃ আব্দুল করিম", "name_en": None,
     "href": "/batch-1/abdul-karim",
     "meta": ["এইচএসসি"],
     "outcome_text": None,
     "outcome_label": "আরও পড়াশোনা"},
    {"name_bn": "তানজিলা আক্তার", "name_en": None,
     "href": "/batch-1/tanjila-akter",
     "meta": ["স্নাতক", "এর আগে: শিক্ষার্থী"],
     "outcome_text": "ফ্রিল্যান্স প্ল্যাটফর্মে এআই কনটেন্ট ডিজাইনার হিসেবে কাজ করছেন।",
     "outcome_label": "ফ্রিল্যান্সিং"},
]

# A stat set that deliberately contains a suppressed cell (§5.4, S6):
# 'শিক্ষকতা' is derived from 2 records, under the 5-record floor, so it is None.
STATS = [
    {"label": "মোট প্রশিক্ষণার্থী", "value": "১২৪", "unit": None, "note": None},
    {"label": "সম্মতি দিয়েছেন", "value": "১১৮", "unit": None, "note": None},
    {"label": "কোর্সের মেয়াদ", "value": "৩০০", "unit": "ঘণ্টা", "note": "প্রতিদিন ৬ ঘণ্টা"},
    {"label": "সমাপ্তকারী", "value": None, "unit": None,
     "note": "৫টির কম রেকর্ড থেকে গণনা করা, তাই প্রকাশ করা হয়নি"},
]

STAT_ROWS = [
    ["কর্মসংস্থান", "৪১", "৩৫%"],
    ["ফ্রিল্যান্সিং", "৩৮", "৩২%"],
    ["আরও পড়াশোনা", "২০", "১৭%"],
    ["ব্যবসা", "১২", "১০%"],
    ["শিক্ষকতা", None, None],   # suppressed
]

FACTS = [
    {"label": "কোর্সের নাম", "value": "জেনারেটিভ এআই দক্ষতা উন্নয়ন"},
    {"label": "মেয়াদ", "value": "৩০০ ঘণ্টা / ৫০ দিন"},
    {"label": "দৈনিক সময়", "value": "৬ ঘণ্টা"},
    {"label": "যোগ্যতা", "value": "এইচএসসি বা সমমূল্য, বয়স ১৮–৩৫"},
    {"label": "খরচ", "value": "সম্পূর্ণ বিনামূল্যে"},
    {"label": "সনদ", "value": "সরকারি প্রশিক্ষণ সনদ"},
]

FAQS = [
    {"question_bn": "কোর্সে ভর্তি হতে কী যোগ্যতা লাগবে?",
     "answer_bn": "ন্যূনতম এইচএসসি বা সমমূল্য পাশ এবং বয়স ১৮ থেকে ৩৫ বছরের মধ্যে হতে হবে।"},
    {"question_bn": "কোর্স কি বিনামূল্যে?",
     "answer_bn": "হ্যাঁ। প্রশিক্ষণ সম্পূর্ণ বিনামূল্যে, সাথে দৈনিক ভাতা ও দুপুরের খাবার দেওয়া হয়।"},
    {"question_bn": "কোর্স শেষে সনদ পাওয়া যাবে কি?",
     "answer_bn": "সফলভাবে সম্পন্নকারীদের সরকারি সনদ প্রদান করা হয়।"},
]

TIMELINE = [
    {"date_bn": "১০ জানুয়ারি ২০২৬", "title_bn": "আবেদন আহ্বান", "body_bn": "অনলাইনে আবেদন গ্রহণ শুরু।"},
    {"date_bn": "২ ফেব্রুয়ারি ২০২৬", "title_bn": "নির্বাচন সম্পন্ন", "body_bn": "যোগ্য প্রার্থীদের বাছাই ও নিশ্চিতকরণ।"},
    {"date_bn": "১ মার্চ ২০২৬", "title_bn": "প্রশিক্ষণ শুরু", "body_bn": "ব্যাচ ১-এর ক্লাস শুরু।"},
    {"date_bn": "৩০ এপ্রিল ২০২৬", "title_bn": "প্রশিক্ষণ সমাপ্ত", "body_bn": "চূড়ান্ত মূল্যায়ন ও সনদ প্রদান।"},
]

INSTITUTION = {
    "name_bn": "সিলেট বিইউটিটিসি",
    "name_en": "Sylhet BUTTC",
    "role_bn": "প্রশিক্ষণ প্রতিষ্ঠান",
    "address_bn": "সিলেট, বাংলাদেশ",
    "contact_phone": "+880 821 000000",
    "contact_email": "info@example.gov.bd",
    "description_bn": "সিলেট বিভাগে প্রশিক্ষণ বাস্তবায়নকারী প্রতিষ্ঠান।",
    "logo_url": None,
}

GALLERY = [
    {"kind": "image", "url": "about:blank", "alt_bn": "প্রশিক্ষণ কক্ষে ক্লাস চলছে",
     "caption_bn": "ব্যাচ ১ — দ্বিতীয় সপ্তাহ", "width": 1600, "height": 1200},
    {"kind": "image", "url": "about:blank", "alt_bn": "কম্পিউটার ল্যাবে কাজ করছেন প্রশিক্ষণার্থীরা",
     "caption_bn": None, "width": 1600, "height": 1200},
    {"kind": "video_link", "external_url": "", "alt_bn": "প্রশিক্ষণ কার্যক্রমের ভিডিও",
     "caption_bn": None},
]

CONTACT_ERRORS = {
    "name": "নাম আবশ্যক",
    "email": "ইমেইল ঠিকানাটি সঠিক নয়",
    "message": "বার্তা আবশ্যক",
}


def build_env() -> Environment:
    """The same two globals the app factory injects in Phase 2."""
    env = Environment(
        loader=ChoiceLoader([FileSystemLoader(str(d)) for d in TEMPLATE_DIRS]),
        autoescape=True,
        # StrictUndefined is deliberate: a typo'd variable must fail the harness
        # loudly rather than render an empty string that looks like a design
        # decision. This is the harness's main value as a test.
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # The harness sits at design-src/, so static assets resolve one level up.
    env.globals["static_url"] = lambda p: f"../app/static/{p}"
    env.globals["asset_url"] = lambda p: f"../app/static/{p}?v=dev"
    env.globals["csrf_token"] = lambda: "design-harness-csrf-placeholder"
    return env


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Render the design kitchen sink.")
    parser.add_argument("--open", action="store_true", help="open it in a browser")
    args = parser.parse_args(argv)

    env = build_env()
    context = {
        "nav": NAV,
        "modules": MODULES,
        "participants": PARTICIPANTS,
        "stats": STATS,
        "stat_rows": STAT_ROWS,
        "stat_cols": ["ফলাফল", "সংখ্যা", "শতকরা"],
        "facts": FACTS,
        "faqs": FAQS,
        "timeline_items": TIMELINE,
        "institution": INSTITUTION,
        "gallery": GALLERY,
        "contact_errors": CONTACT_ERRORS,
    }

    print("render-design:")
    try:
        html = env.get_template(SOURCE).render(**context)
    except Exception as exc:  # noqa: BLE001 — the harness's job is to report clearly
        print(f"  FAILED to render {SOURCE}", file=sys.stderr)
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        # A Jinja template error carries the offending line; surface it plainly.
        for attr in ("lineno", "filename", "name"):
            if hasattr(exc, attr):
                print(f"  {attr}: {getattr(exc, attr)}", file=sys.stderr)
        return 1

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"  {SOURCE} -> {OUTPUT.relative_to(ROOT)}  ({len(html.encode()):,} bytes)")

    # A harness that renders but forgot a component is worse than one that fails,
    # so report which of the 29 actually appeared in the output.
    expected = [
        "site_header", "site_footer", "breadcrumb", "hero", "section_heading",
        "document_rule", "stat_strip", "stat_table", "fact_list", "module_grid",
        "participant_card", "participant_grid", "filter_bar", "pagination",
        "gallery_strip", "media_feature", "quote_block", "timeline",
        "institution_card", "faq_accordion", "cta_band", "rich_text",
        "empty_state", "contact_form", "consent_badge", "toast", "modal",
        "data_table", "kpi_card",
    ]
    missing = [n for n in expected if f"kb-{n}" not in html]
    print(f"  components exercised: {len(expected) - len(missing)}/{len(expected)}")
    if missing:
        print(f"  NOT EXERCISED: {', '.join(missing)}", file=sys.stderr)
        return 2

    if args.open:
        webbrowser.open(OUTPUT.as_uri())
        print(
            "\n  NOTE: opening over file:// hides every icon.\n"
            "        Chrome blocks cross-document <use href=\"...sprite.svg#id\"> on\n"
            "        file:// origins, so the sprite silently fails and icon-only\n"
            "        controls render blank. Verified, not assumed.\n"
            "        Serve it instead:\n"
            "            npm run design:serve\n"
            "        then open http://localhost:8099/design-src/kitchen-sink.html"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
