from datetime import UTC, datetime

from app.adapters.text import from_ms, join_sections, slug_title, text_to_html


def test_text_to_html_paragraphs_and_lists():
    got = text_to_html("What we offer\n- Learn\n- Grow\n\nBe <bold>")
    assert got == "<p>What we offer</p><ul><li>Learn</li><li>Grow</li></ul><p>Be &lt;bold&gt;</p>"


def test_text_to_html_line_breaks_inside_paragraph():
    assert text_to_html("Line one\nLine two") == "<p>Line one<br>Line two</p>"


def test_text_to_html_blank_is_none():
    assert text_to_html("  \n") is None
    assert text_to_html(None) is None


def test_from_ms_forms():
    want = datetime(2026, 7, 3, 1, 54, 0, 931000, tzinfo=UTC)
    assert from_ms(1783043640931) == want
    assert from_ms("1783043640931") == want
    assert from_ms("/Date(1783043640931)/") == want
    assert from_ms(None) is None
    assert from_ms("") is None


def test_join_sections_skips_blank():
    got = join_sections([("About", "<p>a</p>"), ("Empty", " "), (None, "<p>b</p>")])
    assert got == "<h3>About</h3><p>a</p>\n<p>b</p>"


def test_join_sections_all_blank_is_none():
    assert join_sections([("A", None), (None, "")]) is None


def test_slug_title():
    assert slug_title("Bengaluru-Management-Trainee-IND-560035") == (
        "Bengaluru Management Trainee IND 560035"
    )
    assert slug_title("Pune-SOLUTION-ARCHITECT-L1%28CONTRACT%29-IND-411005") == (
        "Pune SOLUTION ARCHITECT L1(CONTRACT) IND 411005"
    )
    assert slug_title("software-engineering-internship-trizetto-product-house") == (
        "Software engineering internship trizetto product house"
    )
