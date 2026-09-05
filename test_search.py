from bot import build_search_page, search_cache

def test_pagination():
    mock_results = [
        {"id": i, "title": f"Arya Movie {i}", "year": "2004", "type": "movie", "source": "TMDb"}
        for i in range(1, 15)
    ]
    cache_id = "test1234"
    search_cache[cache_id] = mock_results

    # Page 1
    text1, markup1 = build_search_page(cache_id, mock_results, page=1, items_per_page=6)
    print("Page 1 Text:\n", text1)
    assert "Page 1/3" in text1
    assert "Total 14 Results" in text1
    assert len(markup1.inline_keyboard) == 7 # 6 items + 1 nav row

    # Page 2
    text2, markup2 = build_search_page(cache_id, mock_results, page=2, items_per_page=6)
    print("\nPage 2 Text:\n", text2)
    assert "Page 2/3" in text2

    # Page 3
    text3, markup3 = build_search_page(cache_id, mock_results, page=3, items_per_page=6)
    print("\nPage 3 Text:\n", text3)
    assert "Page 3/3" in text3

    print("\nALL SEARCH PAGINATION TESTS PASSED! 🚀")

if __name__ == "__main__":
    test_pagination()
