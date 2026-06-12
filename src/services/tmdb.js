const BASE_URL = 'https://api.themoviedb.org/3';

export const tmdbService = {
  getApiKey() {
    return window.CONFIG?.tmdb_key || '';
  },

  async fetchTrending(type = 'movie', timeWindow = 'week') {
    const response = await fetch(`${BASE_URL}/trending/${type}/${timeWindow}?api_key=${this.getApiKey()}`);
    return response.json();
  },

  async searchMulti(query) {
    const response = await fetch(`${BASE_URL}/search/multi?api_key=${this.getApiKey()}&query=${encodeURIComponent(query)}`);
    return response.json();
  },

  async getDetails(type, id) {
    const response = await fetch(`${BASE_URL}/${type}/${id}?api_key=${this.getApiKey()}&append_to_response=videos,images,credits,similar`);
    return response.json();
  }
};
