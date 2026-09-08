const BASE_URL = 'https://webservice.fanart.tv/v3';
const FANART_API_KEY = 'YOUR_FANART_API_KEY';

export const fanartService = {
  async getImages(type, id) {
    const response = await fetch(`${BASE_URL}/${type}/${id}?api_key=${FANART_API_KEY}`);
    return response.json();
  }
};
