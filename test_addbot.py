import re

def search_decreasing_words(query, database_titles):
    words = [w for w in re.split(r"\s+", query) if w]
    if not words:
        return []

    max_words = len(words)
    for k in range(max_words, 0, -1):
        for i in range(len(words) - k + 1):
            candidate = " ".join(words[i:i + k]).strip()
            if len(candidate) < 2:
                continue

            matches = [t for t in database_titles if re.search(f".*{re.escape(candidate)}.*", t, re.IGNORECASE)]
            if matches:
                return matches
    return []

def test_addbot_search_algorithm():
    titles = ["Pokiri", "Game of Thrones", "Inception", "Landscape Image Movie Test"]

    # Test 1: Full match
    res1 = search_decreasing_words("where can I watch Pokiri movie 2006", titles)
    print("Test 1 Result:", res1)
    assert "Pokiri" in res1

    # Test 2: Long 400-word simulation with target embedded
    long_msg = "hello " * 200 + "Game of Thrones" + " world" * 150
    res2 = search_decreasing_words(long_msg, titles)
    print("Test 2 Result:", res2)
    assert "Game of Thrones" in res2

    # Test 3: No match -> returns empty list (bot remains silent)
    res3 = search_decreasing_words("xyz abc nonexisting string", titles)
    print("Test 3 Result:", res3)
    assert res3 == []

    print("\nALL ADDBOT SEARCH ALGORITHM TESTS PASSED! 🚀")

if __name__ == "__main__":
    test_addbot_search_algorithm()
