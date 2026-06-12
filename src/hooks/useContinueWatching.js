export const useContinueWatching = {
  get() {
    const data = localStorage.getItem('continue_watching');
    return data ? JSON.parse(data) : [];
  },

  add(item) {
    let list = this.get();
    list = list.filter(i => i.id !== item.id);
    list.unshift({
      id: item.id,
      title: item.title,
      slug: item.slug,
      image: item.image,
      timestamp: new Date().getTime(),
      progress: item.progress || 0
    });
    localStorage.setItem('continue_watching', JSON.stringify(list.slice(0, 10)));
  }
};
