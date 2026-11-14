"""AC-2: quote extraction, anchors, footnotes, code handling and the min-words filter."""
from __future__ import annotations

from _qp_extract import extract

Q = "the cache will hold stale schema entries for a while"


def one(report: str, **kw):
    items = extract(report, **kw)
    assert len(items) == 1, items
    return items[0]


def test_inline_straight_curly_and_cjk_quotes():
    text = (f'He said "{Q}" in passing.\n\n'
            f"She said “{Q} again” later.\n\n"
            "그는 「캐시는 최대 열 분 동안 이전 스키마를 유지한다」라고 썼다.\n")
    items = extract(text)
    assert [i.kind for i in items] == ["inline"] * 3
    assert items[0].quote == Q and items[1].quote == f"{Q} again"
    assert items[2].quote.startswith("캐시는 최대")
    assert [i.id for i in items] == [1, 2, 3]
    assert [i.report_line for i in items] == [1, 3, 5]


def test_blockquote_is_one_item_and_inner_quotes_are_not_extracted():
    text = '> The "safe mode" flag disables background workers\n> and "never" touches the HTTP API.\n'
    item = one(text)
    assert item.kind == "block"
    assert item.quote == 'The "safe mode" flag disables background workers\nand "never" touches the HTTP API.'
    assert item.report_line == 1


def test_blockquote_trailing_anchor_belongs_to_the_block():
    item = one("> Run the migration script before restarting the service. (src/guide.md:3)\n")
    assert item.kind == "block"
    assert item.quote == "Run the migration script before restarting the service."
    assert (item.claim.path, item.claim.line_start, item.claim.line_end) == ("src/guide.md", 3, 3)


def test_paren_anchor_forms():
    a = one(f'"{Q}" (src/guide.md:3)').claim
    assert (a.path, a.line_start, a.line_end, a.page) == ("src/guide.md", 3, 3, None)
    a = one(f'"{Q}" (src/guide.md:3-9)').claim
    assert (a.line_start, a.line_end) == (3, 9)
    a = one(f'"{Q}" (docs/paper.txt:p.4)').claim
    assert (a.path, a.page, a.line_start) == ("docs/paper.txt", 4, None)
    a = one(f'"{Q}" (src/guide.md)').claim
    assert (a.path, a.line_start) == ("src/guide.md", None)


def test_anchor_path_is_cleaned_with_the_shared_rule():
    a = one(f'"{Q}" (./src//guide.md:3)').claim
    assert a.path == "src/guide.md"
    a = one(f'"{Q}" (src\\guide.md:3)').claim
    assert a.path == "src/guide.md"


def test_markdown_link_with_line_range():
    a = one(f'"{Q}" ([guide](src/guide.md#L12-L20))').claim
    assert (a.path, a.line_start, a.line_end, a.style) == ("src/guide.md", 12, 20, "link")
    a = one(f'"{Q}" [guide](src/guide.md#L7)').claim
    assert (a.line_start, a.line_end) == (7, 7)


def test_web_links_and_non_paths_are_not_anchors():
    assert one(f'"{Q}" ([site](https://example.com/page.html#L3))').claim is None
    assert one(f'"{Q}" (see the note, e.g.)').claim is None
    assert one(f'"{Q}" (version 3.5)').claim is None


def test_footnote_reference_pairs_with_definition():
    text = f'The guide says "{Q}"[^a].\n\nAnd "{Q} too"[^2].\n\n[^a]: src/guide.md:3-4\n[^2]: [notes](src/notes.md#L9)\n'
    items = extract(text)
    assert len(items) == 2
    assert (items[0].claim.path, items[0].claim.line_start, items[0].claim.line_end) == ("src/guide.md", 3, 4)
    assert (items[1].claim.path, items[1].claim.line_start, items[1].claim.line_end) == ("src/notes.md", 9, 9)
    # definition lines are never quotes themselves
    assert all("[^" not in i.quote for i in items)


def test_footnote_without_definition_has_no_claim():
    assert one(f'"{Q}"[^9].').claim is None


def test_anchor_belongs_to_the_nearest_quote():
    text = f'"{Q}" and "{Q} twice" (src/b.md:2).'
    items = extract(text)
    assert items[0].claim is None
    assert items[1].claim.path == "src/b.md"


def test_code_spans_and_fences_are_ignored():
    text = ("Use `echo \"" + Q + "\"` carefully.\n\n"
            "```\nprint(\"" + Q + "\")\n```\n\n"
            "~~~\n\"" + Q + "\"\n~~~\n")
    assert extract(text) == []


def test_quote_after_a_closed_fence_is_found_again():
    text = "```\ncode\n```\n\nHe wrote \"" + Q + "\" afterwards.\n"
    assert one(text).quote == Q


def test_min_words_filter():
    text = 'The "safe mode" flag and "the HTTP API" and "' + Q + '".\n'
    assert [i.quote for i in extract(text)] == [Q]                       # default 4 words
    assert len(extract(text, min_words=3)) == 2
    assert len(extract(text, min_words=2)) == 3
    assert len(extract(text, min_words=7)) == 1


def test_min_words_counts_cjk_characters_twice_as_many():
    text = '그는 "짧은 말이다" 라고 했고 "캐시는 최대 열 분 동안 유지한다" 라고 했다.\n'
    items = extract(text)
    assert [i.quote for i in items] == ["캐시는 최대 열 분 동안 유지한다"]


def test_report_line_is_separate_from_source_line():
    item = one(f'intro\n\n"{Q}" (src/guide.md:42)\n')
    assert item.report_line == 3
    assert item.claim.line_start == 42


def test_quote_spanning_wrapped_lines_of_a_paragraph():
    item = one('He said "the cache will hold\nstale schema entries for a while" (src/guide.md:3).\n')
    assert item.quote == "the cache will hold\nstale schema entries for a while"
    assert item.report_line == 1


def test_list_items_do_not_pair_quotes_across_items():
    text = f'- one “{Q}” (a.md:1)\n- two says "odd quote here\n- three "{Q}" (c.md:3)\n'
    items = extract(text)
    assert [i.claim.path for i in items] == ["a.md", "c.md"]


def test_spans_point_at_the_quote_and_the_anchor_in_the_report():
    text = f'He said "{Q}" (src/guide.md:3).'
    item = one(text)
    assert text[item.span[0]:item.span[1]] == Q
    assert text[item.claim.span[0]:item.claim.span[1]] == "src/guide.md:3"


def test_no_quotes():
    assert extract("# Title\n\nPlain text with 'single quotes' only.\n") == []
