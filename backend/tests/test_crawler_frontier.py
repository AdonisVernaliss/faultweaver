from faultweaver.assessments.frontier import CrawlFrontier


def test_frontier_deduplicates_canonical_urls_and_tracks_states() -> None:
    frontier = CrawlFrontier(max_depth=2, max_query_variants_per_path=2)
    first = frontier.discover("https://EXAMPLE.test:443/a#one", depth=0, kind="seed")
    duplicate = frontier.discover("https://example.test/a#two", depth=1, kind="navigation")

    assert first is not None
    assert duplicate is None
    queued = frontier.pop()
    assert queued is first
    assert queued.state == "queued"
    frontier.mark_requested(queued)
    assert queued.state == "requested"


def test_frontier_enforces_depth_and_query_variation_caps() -> None:
    frontier = CrawlFrontier(max_depth=1, max_query_variants_per_path=2)

    assert frontier.discover("https://example.test/a?q=1", depth=1, kind="navigation")
    assert frontier.discover("https://example.test/a?q=2", depth=1, kind="navigation")
    skipped_query = frontier.discover("https://example.test/a?q=3", depth=1, kind="navigation")
    skipped_depth = frontier.discover("https://example.test/deep", depth=2, kind="navigation")

    assert skipped_query is not None and skipped_query.state == "skipped"
    assert skipped_query.reason == "query variation limit"
    assert skipped_depth is not None and skipped_depth.state == "skipped"
    assert skipped_depth.reason == "depth limit"
