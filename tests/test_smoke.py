"""Package installation smoke test."""


def test_package_imports() -> None:
    import wikipedia_interest

    assert wikipedia_interest is not None
