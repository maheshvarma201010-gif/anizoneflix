const BASE_URL = 'https://api.trakt.tv';

export const traktService = {
  getApiKey() {
    return window.CONFIG?.trakt_key || '';
  },

  async search(type, query) {
    const key = this.getApiKey();
    if (!key) return null;
    const tType = type === 'tv' ? 'show' : 'movie';
    try {
      const response = await fetch(`${BASE_URL}/search/${tType}?query=${encodeURIComponent(query)}`, {
        headers: {
          'Content-Type': 'application/json',
          'trakt-api-version': '2',
          'trakt-api-key': key
        }
      });
      if (response.ok) return await response.json();
    } catch (e) {
      console.error("Trakt API error:", e);
    }
    return null;
  },

  async getStats(type, traktId) {
    const key = this.getApiKey();
    if (!key) return null;
    const tType = type === 'tv' ? 'shows' : 'movies';
    try {
      const response = await fetch(`${BASE_URL}/${tType}/${traktId}/stats`, {
        headers: {
          'Content-Type': 'application/json',
          'trakt-api-version': '2',
          'trakt-api-key': key
        }
      });
      if (response.ok) return await response.json();
    } catch (e) {
      console.error("Trakt Stats API error:", e);
    }
    return null;
  },

  async getComments(type, traktId) {
    const key = this.getApiKey();
    if (!key) return null;
    const tType = type === 'tv' ? 'shows' : 'movies';
    try {
      const response = await fetch(`${BASE_URL}/${tType}/${traktId}/comments/trending`, {
        headers: {
          'Content-Type': 'application/json',
          'trakt-api-version': '2',
          'trakt-api-key': key
        }
      });
      if (response.ok) return await response.json();
    } catch (e) {
      console.error("Trakt Comments API error:", e);
    }
    return null;
  }
};
