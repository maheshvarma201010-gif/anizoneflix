import re

def search_decreasing_words(query, database_titles):
    words = [w for w in re.split(r"\s+", query) if w]
    if not words:
        return []

    max_words = len(words)
    for k in range(max_words, 0, -1):
        for i in range(len(words) - k + 1):
            candidate = " ".join(words[i:i + k]).strip()
            if not candidate:
                continue

            if len(candidate) == 1 and candidate.lower() in ["a", "i"] and len(words) > 1:
                continue

            if len(candidate) == 1:
                matches = [t for t in database_titles if re.search(f"^{re.escape(candidate)}", t, re.IGNORECASE)]
                if not matches:
                    matches = [t for t in database_titles if re.search(f".*{re.escape(candidate)}.*", t, re.IGNORECASE)]
            else:
                matches = [t for t in database_titles if re.search(f".*{re.escape(candidate)}.*", t, re.IGNORECASE)]

            if matches:
                return matches
    return []

def test_addbot_search_algorithm():
    titles = ["Peddi", "Pokiri", "Bahubali", "Brahmastra", "Game of Thrones", "Inception"]

    # Test 1: Single letter "p" -> matches Peddi, Pokiri
    res1 = search_decreasing_words("p", titles)
    print("Test 1 ('p'):", res1)
    assert "Peddi" in res1 and "Pokiri" in res1

    # Test 2: Single letter "b" -> matches Bahubali, Brahmastra
    res2 = search_decreasing_words("b", titles)
    print("Test 2 ('b'):", res2)
    assert "Bahubali" in res2 and "Brahmastra" in res2

    # Test 3: Multi-word query
    res3 = search_decreasing_words("where can I find Bahubali movie", titles)
    print("Test 3 ('Bahubali'):", res3)
    assert "Bahubali" in res3

    # Test 4: No match -> empty list (silent)
    res4 = search_decreasing_words("xyz 123 nonexisting", titles)
    print("Test 4 (empty):", res4)
    assert res4 == []

    print("\nALL SINGLE-LETTER & MULTI-WORD SEARCH TESTS PASSED! 🚀")

if __name__ == "__main__":
    test_addbot_search_algorithm()
