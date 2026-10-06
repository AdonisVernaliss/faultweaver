import itertools
import random
import time
from difflib import SequenceMatcher

from faultweaver.analysis.matching import ExactSequenceMatcher


def test_exact_matching_blocks_preserve_legacy_tie_breaking_exhaustively():
    words = [
        "".join(chars) for length in range(6) for chars in itertools.product("ab", repeat=length)
    ]
    for first, second in itertools.product(words, repeat=2):
        expected = SequenceMatcher(None, first, second, autojunk=False)
        actual = ExactSequenceMatcher(first, second)
        assert actual.get_matching_blocks() == expected.get_matching_blocks(), (first, second)
        assert actual.ratio() == expected.ratio()


def test_exact_matching_with_unicode_repetition_insertions_and_ranges():
    randomizer = random.Random(84)
    for _ in range(1000):
        first = "".join(randomizer.choices("ab <>雪é🙂", k=randomizer.randrange(1, 220)))
        second = first[:70] + "access denied" + first[100:]
        second = second if randomizer.randrange(2) else second[::-1]
        expected = SequenceMatcher(None, first, second, autojunk=False)
        actual = ExactSequenceMatcher(first, second)
        assert actual.get_matching_blocks() == expected.get_matching_blocks()
        bounds = (
            min(3, len(first)),
            min(80, len(first)),
            min(4, len(second)),
            min(90, len(second)),
        )
        assert actual.find_longest_match(*bounds) == expected.find_longest_match(*bounds)


def test_similar_html_no_longer_takes_tens_of_seconds():
    first = (
        "<html><body>"
        + "".join(
            f'<section class="row"><h2>Account {n}</h2>'
            "<p>Invoice for fictional tenant</p></section>"
            for n in range(600)
        )
        + "</body></html>"
    )
    second = (
        first.replace("Account 12<", "Account 13<")
        .replace("Account 90<", "Restricted 90<")
        .replace("</body>", "<aside>Read-only access</aside></body>")
    )
    start = time.perf_counter()
    actual = ExactSequenceMatcher(first, second).ratio()
    elapsed = time.perf_counter() - start
    # Recorded using the unchanged Python SequenceMatcher on this exact fixture.
    assert actual == 0.9995536840471154
    assert elapsed < 5, f"Synthetic 51 KB HTML comparison regressed to {elapsed:.2f}s"
