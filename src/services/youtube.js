export const youtubeService = {
  getEmbedUrl(videoId) {
    return `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`;
  },
  getThumbnail(videoId) {
    return `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
  }
};
