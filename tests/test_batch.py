"""Unit tests for batch and pattern URL expansion."""

from pdm.core.batch import expand_url_pattern, parse_batch_input


def test_expand_numeric_pattern():
    # Leading zeros
    urls = expand_url_pattern("https://example.com/part_[01-05].zip")
    assert len(urls) == 5
    assert urls[0] == "https://example.com/part_01.zip"
    assert urls[4] == "https://example.com/part_05.zip"

    # Non-zero padded
    urls = expand_url_pattern("https://example.com/file_[8-11].bin")
    assert len(urls) == 4
    assert urls[0] == "https://example.com/file_8.bin"
    assert urls[3] == "https://example.com/file_11.bin"


def test_expand_alpha_pattern():
    urls = expand_url_pattern("https://example.com/section_[a-d].pdf")
    assert len(urls) == 4
    assert urls[0] == "https://example.com/section_a.pdf"
    assert urls[3] == "https://example.com/section_d.pdf"


def test_parse_batch_input():
    raw_text = """
    https://example.com/file1.zip
    https://example.com/chunk_[01-03].iso
    invalid-url-line
    https://example.com/video.mp4
    """
    valid, invalid = parse_batch_input(raw_text)
    assert len(valid) == 5  # file1 + 3 chunks + video
    assert len(invalid) == 1
    assert "invalid-url-line" in invalid[0]
