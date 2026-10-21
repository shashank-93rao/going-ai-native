"""A weak oracle: it only proves the module imports and constructs. Used to show survivors."""

from tokenbucket import TokenBucket


def test_constructs():
    assert TokenBucket(3, 1.0) is not None
