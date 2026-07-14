from app.utils import sanitize_filename


def test_sanitize_filename_blocks_traversal():
    assert sanitize_filename("../../evil?.mkv") == "evil_.mkv"
    assert "/" not in sanitize_filename("a/b.txt")


def test_empty_and_long_names():
    assert sanitize_filename("...") == "file"
    assert len(sanitize_filename("x" * 500 + ".txt").encode()) <= 240

