from app.citation.references import parse_references


def test_latin_apa_entry() -> None:
    section = "Kim, S., & Lee, J. (2024). A study of things. Journal of X, 1(2), 3-4."
    refs = parse_references(section)
    assert len(refs) == 1
    r = refs[0]
    assert r.year == 2024
    assert "Kim" in r.authors and "Lee" in r.authors


def test_numbered_entries() -> None:
    section = (
        "[1] A. Author, Title one, 2019.\n"
        "continued title and publisher line.\n"
        "[2] B. Writer, Title two, 2020.\n"
    )
    refs = parse_references(section)
    assert len(refs) == 2
    assert refs[0].number == 1
    assert "continued title" in refs[0].raw
    assert refs[1].number == 2
    assert refs[1].year == 2020


def test_korean_entry() -> None:
    section = (
        "\uae40\ub3d9\uc6b1(2024). "
        "\ud55c\uad6d\uc5b4 \ub17c\ubb38 \uc81c\ubaa9. "
        "\ud55c\uad6d\uad50\uc721\uacf5\ud559\uc5f0\uad6c, 40(1), 1-20."
    )
    refs = parse_references(section)
    assert len(refs) == 1
    assert refs[0].year == 2024
    assert "\uae40\ub3d9\uc6b1" in refs[0].authors


def test_empty_section() -> None:
    assert parse_references(None) == []
    assert parse_references("") == []


def test_body_section_heading_inside_reference_block_is_ignored() -> None:
    refs = parse_references(
        "\n".join(
            [
                "Kim, S. (2024). A real study. Journal, 1(1), 1-2.",
                "\ub2e4. \ud55c\uacc4\uc810",
                "Lee, J. (2023). Another study. Journal, 2(1), 3-4.",
            ]
        )
    )

    assert len(refs) == 2
    assert all("\ud55c\uacc4\uc810" not in ref.raw for ref in refs)


def test_wrapped_apa_reference_lines_are_merged() -> None:
    refs = parse_references(
        "\n".join(
            [
                "National Research Council. (2012). Education for life and work:",
                "Developing transferable knowledge and skills in the 21st century.",
                "National Academies Press. https://doi.org/10.17226/13398",
                "Kasneci, E., Sessler, K., & Kuchemann, S. (2023). ChatGPT for good?",
                "Learning and Individual Differences, 103, 102274.",
            ]
        )
    )

    assert len(refs) == 2
    assert refs[0].authors == ["National Research Council"]
    assert "Developing transferable" in refs[0].raw
    assert "National Academies Press" in refs[0].raw
    assert refs[1].authors == ["Kasneci", "Sessler", "Kuchemann"]


def test_body_fragment_with_year_does_not_start_reference() -> None:
    refs = parse_references(
        "\n".join(
            [
                "Kim, S. (2024). A real study. Journal, 1(1), 1-2.",
                "This body-like continuation mentions a 2020 classroom policy.",
                "Lee, J. (2023). Another study. Journal, 2(1), 3-4.",
            ]
        )
    )

    assert len(refs) == 2
    assert "2020 classroom policy" in refs[0].raw
