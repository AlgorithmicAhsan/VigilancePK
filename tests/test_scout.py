from src.scout import NewsScraper, clean_text, is_urdu


def test_clean_text_strips_tags_and_decodes_entities():
    raw = '<p>Protest in <b>Lahore</b> &amp; Karachi</p><img src="x.jpg">'
    assert clean_text(raw) == "Protest in Lahore & Karachi"


def test_clean_text_leaves_encoded_markup_as_plain_text():
    # Decoded after stripping, so it survives as text the UI will escape.
    assert clean_text("&lt;script&gt;alert(1)&lt;/script&gt;") == "<script>alert(1)</script>"


def test_clean_text_handles_missing_values():
    assert clean_text(None) == ""
    assert clean_text("  a \n\t b  ") == "a b"


def test_is_urdu():
    assert is_urdu("لاہور میں احتجاج")
    assert not is_urdu("Protest in Lahore")
    assert not is_urdu("")
    assert not is_urdu(None)


def _article(title, language="english"):
    return {"title": title, "summary": "", "language": language}


def test_filter_uses_whole_words():
    scraper = NewsScraper()
    scraper.data = [
        _article("Scores of protesters killed in Quetta"),
        _article("Court matched the FIR to the CCTV record"),
        _article("Pakistan win the cricket match"),
        _article("کرکٹ میچ", language="urdu"),
    ]
    scraper.filter_articles()
    kept = [a["title"] for a in scraper.filtered_data]
    assert kept == [
        "Scores of protesters killed in Quetta",
        "Court matched the FIR to the CCTV record",
        "کرکٹ میچ",  # Urdu is never keyword-filtered
    ]


def test_one_failing_feed_does_not_stop_the_others(monkeypatch):
    import types
    from src import scout

    def fake_parse(url, agent=None):
        if "broken" in url:
            raise OSError("timed out")
        entry = {"title": f"Story from {url}", "summary": "", "link": url + "/1", "published": "Mon, 20 Oct 2026 10:00:00 +0500"}
        return types.SimpleNamespace(bozo=False, entries=[entry])

    monkeypatch.setattr(scout.feedparser, "parse", fake_parse)
    scraper = NewsScraper()
    scraper.sources = {"A": "https://a.example", "Broken": "https://broken.example", "C": "https://c.example"}
    scraper.fetch_feeds()
    assert [a["source"] for a in scraper.data] == ["A", "C"]  # source order kept
    assert scraper.data[0]["published"] == "2026-10-20T05:00:00+00:00"  # stored in UTC
