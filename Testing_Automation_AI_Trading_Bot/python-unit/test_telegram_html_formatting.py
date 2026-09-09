"""Regression tests for Telegram HTML formatting (2026-09-09).

Two bugs in ``TelegramAlerter.format_to_html``:

1. **The backslash-stripping step was a no-op.** Its character class was
   over-escaped -- ``r"\\\\([_*\\\\[\\\\]()~`>#+\\-=|{}.!])"`` -- so the class
   terminated early and matched none of the intended characters. Verified
   against the real function before the fix: ``\\_underscore\\_`` came back as
   ``\\<i>underscore\\</i>``, i.e. the backslashes survived *and* the italic
   tags were wrapped around them -- producing exactly the "broken backslash
   artifacts" the docstring claimed to prevent.

2. **No HTML escaping.** ``&``, ``<`` and ``>`` were passed through raw under
   ``parse_mode=HTML``. Telegram's parser rejects those, so a single ``&`` or
   ``<`` anywhere in a dynamic field -- a symbol, an exit reason, a P&L string
   -- returned HTTP 400 and the whole message silently degraded to plain text,
   logged only at debug level.

Real exit reasons contain both: ``"AI Exit Analyzer (PEAK_LOCK): Gave back
25.0% from high watermark (Peak +18.0 pts, current 163.5)"`` and P&L lines
routinely read ``"P&L"``.
"""

from __future__ import annotations

import pytest

from shared.alerts.telegram import TelegramAlerter

fmt = TelegramAlerter.format_to_html


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------

def test_ampersand_is_escaped():
    """'P&L' is in almost every alert this system sends."""
    assert fmt("P&L up") == "P&amp;L up"


def test_angle_brackets_are_escaped():
    assert fmt("5 < 10 and 12 > 3") == "5 &lt; 10 and 12 &gt; 3"


def test_a_real_exit_reason_survives_intact():
    out = fmt("AI Exit Analyzer (PEAK_LOCK): gave back 25% <peak 168>")
    assert "&lt;peak 168&gt;" in out
    assert "PEAK_LOCK" in out, "identifier must not be mangled"


def test_escaping_happens_before_tags_are_inserted():
    """Our own tags must never be escaped into visible text."""
    out = fmt("*BOLD*")
    assert out == "<b>BOLD</b>"
    assert "&lt;b&gt;" not in out


@pytest.mark.parametrize("payload", ["a & b", "x < y", "y > x", "a&b<c>d"])
def test_no_raw_special_characters_survive(payload):
    """Any raw &, < or > left in the output is a 400 from Telegram."""
    out = fmt(payload)
    without_tags = out.replace("<b>", "").replace("</b>", "") \
                      .replace("<i>", "").replace("</i>", "") \
                      .replace("<code>", "").replace("</code>", "") \
                      .replace("<blockquote>", "").replace("</blockquote>", "")
    assert "<" not in without_tags and ">" not in without_tags
    # '&' may only appear as the start of an entity we produced.
    for i, ch in enumerate(without_tags):
        if ch == "&":
            assert without_tags[i:i + 5] in ("&amp;", "&lt;s", "&gt;s") or \
                   without_tags[i:].startswith(("&amp;", "&lt;", "&gt;"))


# ---------------------------------------------------------------------------
# Backslash stripping -- the step that did nothing
# ---------------------------------------------------------------------------

def test_legacy_escaped_underscores_are_cleaned():
    r"""Was '\<i>underscore\</i>' -- backslashes kept AND tags applied."""
    assert fmt(r"\_underscore\_") == "<i>underscore</i>"


@pytest.mark.parametrize("payload,expected", [
    (r"a \* b", "a * b"),
    (r"\- dash", "- dash"),
    (r"\. dot", ". dot"),
    (r"\(paren\)", "(paren)"),
    (r"\!bang", "!bang"),
    (r"\#hash", "#hash"),
    (r"\|pipe", "|pipe"),
])
def test_markdownv2_escapes_are_stripped(payload, expected):
    assert fmt(payload) == expected


def test_no_stray_backslashes_remain():
    assert "\\" not in fmt(r"\_a\_ \* \- \. \!")


# ---------------------------------------------------------------------------
# Markdown -> HTML conversion still works
# ---------------------------------------------------------------------------

def test_bold_code_and_italic():
    assert fmt("*ENTRY* `NIFTY24500CE` _note_") == \
        "<b>ENTRY</b> <code>NIFTY24500CE</code> <i>note</i>"


def test_blockquote_still_detected_after_escaping():
    """'>' becomes '&gt;' before the quote scan, so the scan must expect that."""
    assert fmt("> quoted line") == "<blockquote>quoted line</blockquote>"


def test_multiline_blockquote_is_grouped():
    out = fmt("> line one\n> line two\nplain")
    assert out.startswith("<blockquote>line one\nline two</blockquote>")
    assert out.endswith("plain")


def test_plain_text_is_unchanged():
    assert fmt("Entry NIFTY 24500 CE at 153.05") == "Entry NIFTY 24500 CE at 153.05"
