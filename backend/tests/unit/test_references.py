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


def test_long_korean_body_paragraph_is_not_merged_into_reference() -> None:
    refs = parse_references(
        "\n".join(
            [
                "Kim, S. (2024). A real study. Journal, 1(1), 1-2.",
                (
                    "\ubcf8 \uc5f0\uad6c\ub294 \ub2e4\uc74c\uacfc \uac19\uc740 "
                    "\ud55c\uacc4\ub97c \uc9c0\ub2cc\ub2e4. \uccab\uc9f8, "
                    "\ubcf8 \uc5f0\uad6c\ub294 \ub2e8\uc77c\uc9d1\ub2e8 "
                    "\uc804\ud6c4\uac80\uc0ac \uc124\uacc4\uc5d0 \uae30\ubc18\ud55c "
                    "\uc900\uc2e4\ud5d8\uc5f0\uad6c\ub85c \uc218\ud589\ub418\uc5c8\uae30 "
                    "\ub54c\ubb38\uc5d0, \ub0b4\uc801 \ud0c0\ub2f9\ub3c4\uc5d0 "
                    "\uc601\ud5a5\uc744 \ubbf8\uce60 \uc218 \uc788\ub294 "
                    "\uc694\uc778\uc744 \uc644\uc804\ud788 \ud1b5\uc81c\ud558\uc9c0 "
                    "\ubabb\ud558\uc600\ub2e4. \ubcf8 \uc5f0\uad6c\uc5d0\uc11c\ub294 "
                    "\uc9c8\uc801 \uc790\ub8cc\ub97c \ud568\uaed8 \uc218\uc9d1\ud558\uc5ec "
                    "\uc591\uc801 \uacb0\uacfc\ub97c \ubcf4\uc644\ud558\uace0\uc790 "
                    "\ud558\uc600\uc73c\ub098, \ud5a5\ud6c4 \uc5f0\uad6c\uc5d0\uc11c\ub294 "
                    "\ud1b5\uc81c\uc9d1\ub2e8\uc744 \ud3ec\ud568\ud55c \uc2e4\ud5d8\uc124\uacc4\ub97c "
                    "\ud1b5\ud574 \ud6a8\uacfc\ub97c \uc5c4\ubc00\ud558\uac8c "
                    "\uac80\uc99d\ud560 \ud544\uc694\uac00 \uc788\ub2e4."
                ),
                "Lee, J. (2023). Another study. Journal, 2(1), 3-4.",
            ]
        )
    )

    assert len(refs) == 2
    assert all("\ubcf8 \uc5f0\uad6c\ub294 \ub2e4\uc74c" not in ref.raw for ref in refs)
