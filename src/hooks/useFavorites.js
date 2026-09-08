export const useFavorites = {
  get() {
    const data = localStorage.getItem('favorites');
    return data ? JSON.parse(data) : [];
  },

  toggle(item) {
    let list = this.get();
    const index = list.findIndex(i => i.id === item.id);
    if (index > -1) {
      list.splice(index, 1);
    } else {
      list.unshift({
        id: item.id,
        title: item.title,
        slug: item.slug,
        image: item.image
      });
    }
    localStorage.setItem('favorites', JSON.stringify(list));
    return index === -1; // returns true if added
  },

  isFavorite(id) {
    return this.get().some(i => i.id === id);
  }
};
