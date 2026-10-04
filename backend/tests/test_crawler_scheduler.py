from faultweaver.assessments.scheduler import RateLimiter


def test_rate_limiter_spaces_request_starts_with_injected_clock() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=sleep)
    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert sleeps == [0.5, 0.5]
