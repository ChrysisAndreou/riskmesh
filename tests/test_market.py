from riskmesh.market import ReplayPriceFeed


def test_replay_feed_is_deterministic_and_bounded() -> None:
    feed = ReplayPriceFeed.from_csv()
    first_price = feed.current.close

    feed.advance(3)
    assert feed.current.tick == 3
    assert len(feed.history()) == 4

    feed.reset()
    assert feed.current.close == first_price

    feed.advance(10_000)
    assert feed.exhausted
    assert feed.current.tick == len(feed.points) - 1
