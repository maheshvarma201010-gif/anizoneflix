const BASE_URL = 'https://api.tvmaze.com';

export const tvmazeService = {
  async searchShows(query) {
    const response = await fetch(`${BASE_URL}/search/shows?q=${encodeURIComponent(query)}`);
    return response.json();
  },

  async getShowDetails(id) {
    const response = await fetch(`${BASE_URL}/shows/${id}?embed[]=episodes&embed[]=cast`);
    return response.json();
  }
};
