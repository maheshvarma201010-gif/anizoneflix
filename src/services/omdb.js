const BASE_URL = 'https://www.omdbapi.com';

export const omdbService = {
  getApiKey() {
    return window.CONFIG?.omdb_key || '';
  },

  async getMetadata(imdbId) {
    const response = await fetch(`${BASE_URL}/?apikey=${this.getApiKey()}&i=${imdbId}&plot=full`);
    return response.json();
  }
};
