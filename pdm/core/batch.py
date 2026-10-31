"""Batch URL expansion and pattern parsing utilities."""

import re
from typing import List, Tuple
from pdm.core.security import validate_url


def expand_url_pattern(pattern: str) -> List[str]:
    """Expand wildcard range patterns in a URL.
    
    Supported patterns:
      [01-20] -> 01, 02, ..., 20 (preserves leading zeros)
      [1-100] -> 1, 2, ..., 100
      [a-z]   -> a, b, ..., z
    """
    pattern = pattern.strip()
    if not pattern:
        return []

    # Check for numeric pattern: [01-20]
    num_match = re.search(r"\[(\d+)-(\d+)\]", pattern)
    if num_match:
        start_str, end_str = num_match.group(1), num_match.group(2)
        start, end = int(start_str), int(end_str)
        if start > end or (end - start) > 1000:
            # Safety limit to avoid unbounded expansion
            return [pattern]

        width = len(start_str) if start_str.startswith("0") else 0
        results = []
        for i in range(start, end + 1):
            num_val = f"{i:0{width}d}" if width > 0 else str(i)
            expanded = pattern[:num_match.start()] + num_val + pattern[num_match.end():]
            results.append(expanded)
        return results

    # Check for alpha pattern: [a-z]
    alpha_match = re.search(r"\[([a-zA-Z])-([a-zA-Z])\]", pattern)
    if alpha_match:
        start_c, end_c = alpha_match.group(1), alpha_match.group(2)
        start_ord, end_ord = ord(start_c), ord(end_c)
        if start_ord <= end_ord and (end_ord - start_ord) <= 52:
            results = []
            for code in range(start_ord, end_ord + 1):
                expanded = pattern[:alpha_match.start()] + chr(code) + pattern[alpha_match.end():]
                results.append(expanded)
            return results

    return [pattern]


def parse_batch_input(text: str) -> Tuple[List[str], List[str]]:
    """Parse multi-line input text containing URLs and/or range patterns.
    
    Returns:
        (valid_urls, invalid_lines)
    """
    valid_urls = []
    invalid_lines = []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        expanded = expand_url_pattern(line)
        for url in expanded:
            ok, valid = validate_url(url)
            if ok:
                valid_urls.append(valid)
            else:
                invalid_lines.append(url)

    return valid_urls, invalid_lines
