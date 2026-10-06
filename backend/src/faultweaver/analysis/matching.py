"""Exact non-junk SequenceMatcher blocks without its quadratic inner search."""

from difflib import Match, SequenceMatcher


class ExactSequenceMatcher(SequenceMatcher):
    """Keep difflib's block selection, tie order and ratio; accelerate substring search.

    A suffix automaton indexes the smaller current interval. Each state retains
    the first end position of its substring class, so equal-length matches can
    still choose the earliest a position, then the earliest b position. No junk
    heuristic, sampling, truncation or alternate similarity score is involved.
    The index is local to a search; no decrypted response cache is retained.
    """

    def __init__(self, first: str, second: str):
        super().__init__(None, first, second, autojunk=False)

    def find_longest_match(self, alo=0, ahi=None, blo=0, bhi=None):
        first = self.a[alo:ahi]
        second = self.b[blo:bhi]
        # A whole interval match is already maximal, including identical bodies.
        position = second.find(first)
        if position >= 0:
            return Match(alo, blo + position, len(first))
        position = first.find(second)
        if position >= 0:
            return Match(alo + position, blo, len(second))

        indexed_is_second = len(second) <= len(first)
        indexed, scanned = (second, first) if indexed_is_second else (first, second)
        transitions = [{}]
        lengths = [0]
        links = [-1]
        first_end = [-1]
        last = 0
        for end, character in enumerate(indexed):
            current = len(transitions)
            transitions.append({})
            lengths.append(lengths[last] + 1)
            links.append(0)
            first_end.append(end)
            previous = last
            while previous >= 0 and character not in transitions[previous]:
                transitions[previous][character] = current
                previous = links[previous]
            if previous >= 0:
                target = transitions[previous][character]
                if lengths[previous] + 1 == lengths[target]:
                    links[current] = target
                else:
                    clone = len(transitions)
                    transitions.append(transitions[target].copy())
                    lengths.append(lengths[previous] + 1)
                    links.append(links[target])
                    first_end.append(first_end[target])
                    while previous >= 0 and transitions[previous].get(character) == target:
                        transitions[previous][character] = clone
                        previous = links[previous]
                    links[target] = links[current] = clone
            last = current

        state = width = best_size = 0
        best_a, best_b = alo, blo
        for end, character in enumerate(scanned):
            while state and character not in transitions[state]:
                state = links[state]
                width = lengths[state]
            target = transitions[state].get(character)
            if target is None:
                state = width = 0
                continue
            state = target
            width += 1
            if width < best_size:
                continue
            indexed_start = first_end[state] - width + 1
            scanned_start = end - width + 1
            a, b = (
                (scanned_start, indexed_start)
                if indexed_is_second
                else (indexed_start, scanned_start)
            )
            a, b = a + alo, b + blo
            if width > best_size or (a, b) < (best_a, best_b):
                best_a, best_b, best_size = a, b, width
        return Match(best_a, best_b, best_size)
