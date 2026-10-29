"""Tests for src/rag/sources_footer.py: hiding the SOURCES: line from the stream, and
turning it into the list of files the UI shows. Pure text in, text out - no fakes needed."""
from src.rag.sources_footer import SourcesFooter, resolve_sources


def run(pieces):
    """Feed the pieces one by one. Returns (everything that would be shown, footer text, shown per piece)."""
    footer = SourcesFooter()
    per_piece = [footer.feed(p) for p in pieces]
    rest, footer_text = footer.finish()
    return "".join(per_piece) + rest, footer_text, per_piece


def one_char_at_a_time(text):
    return run(list(text))[:2]


# ---------- SourcesFooter -------------------------------------------------------

def test_footer_is_hidden_and_captured():
    shown, footer, _ = run(["Returns take 30 days.", "\n\n", "SOURCES:", " returns_policy.txt"])
    assert shown == "Returns take 30 days."
    assert footer.strip() == "returns_policy.txt"


def test_the_marker_can_be_split_across_pieces():
    shown, footer, per_piece = run(["Done.", "\n", "SO", "UR", "CES", ":", " a.txt, ", "b.txt"])
    assert shown == "Done."
    assert footer.strip() == "a.txt, b.txt"
    assert "SO" not in "".join(per_piece)   # not even the start of the marker was ever shown


def test_same_result_however_the_text_is_cut_into_pieces():
    text = "The pack holds **40 L**:\n\n- light\n- waterproof\n\nSOURCES: product_catalog.txt, returns_policy.txt\n"
    expected = one_char_at_a_time(text)
    assert expected[0] == "The pack holds **40 L**:\n\n- light\n- waterproof"
    for size in (1, 2, 3, 5, 8, 13, len(text)):
        pieces = [text[i:i + size] for i in range(0, len(text), size)]
        assert run(pieces)[:2] == expected


def test_no_footer_means_nothing_is_lost():
    text = "Just an answer.\n\n- one\n- two\n"
    assert one_char_at_a_time(text) == (text, None)


def test_text_that_only_looks_like_the_start_of_a_footer_is_released_at_the_end():
    shown, footer, _ = run(["Almost.", "\n", "SOU"])
    assert shown == "Almost.\nSOU" and footer is None


def test_the_word_in_the_middle_of_a_line_is_not_a_footer():
    text = "Our SOURCES: are listed on the site."
    assert one_char_at_a_time(text) == (text, None)


def test_a_held_back_newline_is_released_when_the_next_piece_shows_it_was_just_text():
    _, _, per_piece = run(["Line one.", "\n", "Line two."])
    assert "".join(per_piece) == "Line one.\nLine two."


def test_anything_written_after_the_footer_is_kept_out_of_the_answer():
    shown, footer, _ = run(["Answer.\nSOURCES: a.txt\nHope that helps!"])
    assert shown == "Answer." and "a.txt" in footer


# ---------- resolve_sources -----------------------------------------------------

RETRIEVED = ["product_catalog.txt", "returns_policy.txt", "shipping_policy.txt"]


def test_only_the_listed_files_are_shown_in_retrieval_order():
    assert resolve_sources(" shipping_policy.txt, product_catalog.txt\n", RETRIEVED) == ["product_catalog.txt", "shipping_policy.txt"]


def test_formatting_around_the_names_does_not_matter():
    assert resolve_sources(" `returns_policy.txt`.", RETRIEVED) == ["returns_policy.txt"]
    assert resolve_sources("\n- returns_policy.txt\n- shipping_policy.txt", RETRIEVED) == ["returns_policy.txt", "shipping_policy.txt"]


def test_a_made_up_file_never_reaches_the_ui():
    assert resolve_sources(" returns_policy.txt, secret_notes.txt", RETRIEVED) == ["returns_policy.txt"]


def test_a_footer_naming_nothing_we_retrieved_falls_back_to_everything_retrieved():
    assert resolve_sources(" secret_notes.txt", RETRIEVED) == RETRIEVED
    assert resolve_sources("   ", RETRIEVED) == RETRIEVED


def test_no_footer_at_all_falls_back_to_everything_retrieved():
    assert resolve_sources(None, RETRIEVED) == RETRIEVED


def test_none_means_no_sources():
    assert resolve_sources(" none", RETRIEVED) == []
    assert resolve_sources(" None.\n", RETRIEVED) == []
