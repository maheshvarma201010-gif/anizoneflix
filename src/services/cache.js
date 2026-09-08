export const cacheService = {
  get(key) {
    const item = localStorage.getItem(key);
    if (!item) return null;
    const { value, expiry } = JSON.parse(item);
    if (new Date().getTime() > expiry) {
      localStorage.removeItem(key);
      return null;
    }
    return value;
  },

  set(key, value, ttl = 3600000) { // Default 1 hour
    const expiry = new Date().getTime() + ttl;
    localStorage.setItem(key, JSON.stringify({ value, expiry }));
  }
};
