// ==========================================
// INSTANT SEARCH OVERLAY MODULE (GLOBAL SCOPE)
// ==========================================
let searchDebounceTimeout = null;
const searchCache = {};

const openSearchOverlay = (query = "") => {
    const overlay = document.getElementById('search-overlay');
    const input = document.getElementById('overlay-search-input');
    const clearBtn = document.getElementById('overlay-search-clear');

    if (overlay && input) {
        overlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        // Immediate focus with small timeout to ensure virtual keyboards pop up instantly
        setTimeout(() => {
            input.focus();
            const val = input.value;
            input.value = '';
            input.value = val;
        }, 50);

        if (query) {
            input.value = query;
            if (clearBtn) clearBtn.classList.remove('hidden');
            performOverlaySearch(query);
        } else {
            if (!input.value) {
                const resultsContainer = document.getElementById('overlay-results-container');
                const searchStatus = document.getElementById('overlay-search-status');
                if (resultsContainer) resultsContainer.innerHTML = '';
                if (searchStatus) searchStatus.classList.add('hidden');
                if (clearBtn) clearBtn.classList.add('hidden');
            }
        }
    }
};

const closeSearchOverlay = () => {
    const overlay = document.getElementById('search-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
        document.body.style.overflow = '';
    }
};

const clearSearchInput = () => {
    const input = document.getElementById('overlay-search-input');
    const container = document.getElementById('overlay-results-container');
    const status = document.getElementById('overlay-search-status');
    const clearBtn = document.getElementById('overlay-search-clear');
    if (input) input.value = '';
    if (container) container.innerHTML = '';
    if (status) {
        status.textContent = '';
        status.classList.add('hidden');
    }
    if (clearBtn) clearBtn.classList.add('hidden');
};

const performOverlaySearch = async (q) => {
    const container = document.getElementById('overlay-results-container');
    const status = document.getElementById('overlay-search-status');
    const loader = document.getElementById('overlay-search-loader');

    if (!container || !status || !loader) return;

    const trimmedQuery = q.trim();
    if (!trimmedQuery) {
        container.innerHTML = '';
        status.classList.add('hidden');
        loader.classList.add('hidden');
        return;
    }

    // 13. Cache Lookup for instant loading
    if (searchCache[trimmedQuery]) {
        renderSearchResults(searchCache[trimmedQuery], trimmedQuery);
        return;
    }

    loader.classList.remove('hidden');
    status.classList.add('hidden');

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(trimmedQuery)}&limit=48`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const res = await response.json();

        if (res.success) {
            // Save to client-side memory cache
            searchCache[trimmedQuery] = res.data;
            renderSearchResults(res.data, trimmedQuery);
        } else {
            throw new Error(res.message || "Failed to retrieve results");
        }
    } catch (e) {
        console.error('Error during live search:', e);
        status.textContent = 'Search failed';
        status.classList.remove('hidden');

        container.innerHTML = `
            <div class="col-span-full py-20 text-center animate-fade-in">
                <i class="fa-solid fa-triangle-exclamation text-5xl text-red-600 mb-6 opacity-80"></i>
                <h4 class="text-xl font-bold text-gray-400 uppercase tracking-tighter mb-4">Failed to Fetch Results</h4>
                <p class="text-gray-600 text-xs mb-8 uppercase tracking-widest">A network error occurred. Please check your connection and try again.</p>
                <button onclick="retrySearch()" class="btn-premium px-8 py-3.5 text-[10px] tracking-[0.15em] bg-red-600">
                    <i class="fa-solid fa-arrows-rotate mr-2"></i> RETRY SEARCH
                </button>
            </div>
        `;
    } finally {
        loader.classList.add('hidden');
    }
};

const renderSearchResults = (data, query) => {
    const container = document.getElementById('overlay-results-container');
    const status = document.getElementById('overlay-search-status');
    if (!container || !status) return;

    if (data && data.length > 0) {
        status.textContent = `Found ${data.length} titles`;
        status.classList.remove('hidden');

        let html = '';
        data.forEach(anime => {
            html += `
                <div class="anime-card group animate-fade-in no-select no-drag">
                    <a href="/anime/${anime.slug}" class="block">
                        <div class="poster-wrapper relative overflow-hidden rounded-xl bg-black/50 shadow-xl">
                            <img src="${anime.image}" alt="${anime.title}" loading="lazy" class="w-full h-auto max-h-[320px] object-contain transition-transform duration-700 group-hover:scale-105">
                            <div class="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-all duration-500 flex flex-col justify-end p-3 md:p-6">
                                <div class="btn-premium py-2.5 text-[9px] md:text-[10px] uppercase tracking-widest shadow-2xl mb-3 md:mb-4 text-center">Watch Now</div>
                                <div class="flex items-center gap-3 md:gap-4 text-[9px] md:text-[10px] text-gray-300 font-black tracking-widest">
                                    <span class="text-yellow-500"><i class="fa-solid fa-star mr-1"></i> ${anime.score || '8.5'}</span>
                                    <span>•</span>
                                    <span>${anime.year || '2024'}</span>
                                </div>
                            </div>
                            <div class="absolute top-3 right-3 glass px-3 py-1.5 rounded-xl text-[10px] font-black border-white/10 shadow-2xl backdrop-blur-sm">
                                <i class="fa-solid fa-star text-yellow-500 mr-1.5"></i> ${anime.score || '8.5'}
                            </div>
                        </div>
                        <div class="p-3 md:p-4 bg-gradient-to-b from-transparent to-black/20">
                            <h3 class="text-xs md:text-sm font-bold truncate text-white group-hover:text-red-500 transition-colors">${anime.title}</h3>
                            <div class="flex items-center justify-between mt-2">
                                <span class="text-[7px] md:text-[8px] text-gray-400 font-bold uppercase tracking-widest">${anime.category || 'Anime'}</span>
                                <span class="text-[7px] md:text-[8px] text-red-600 font-bold uppercase tracking-widest">${anime.status || 'Released'}</span>
                            </div>
                        </div>
                    </a>
                </div>
            `;
        });
        container.innerHTML = html;
    } else {
        status.textContent = 'No anime found';
        status.classList.remove('hidden');
        container.innerHTML = `
            <div class="col-span-full py-20 text-center animate-fade-in">
                <i class="fa-solid fa-magnifying-glass text-6xl text-gray-800 mb-8 opacity-40"></i>
                <h3 class="text-2xl font-black text-gray-400 mb-4 uppercase tracking-tighter">No anime found</h3>
                <p class="text-gray-600 font-bold uppercase tracking-widest text-[10px]">We couldn't find anything matching "${query}". Try another search term!</p>
            </div>
        `;
    }
};

const retrySearch = () => {
    const input = document.getElementById('overlay-search-input');
    if (input && input.value) {
        performOverlaySearch(input.value);
    }
};

// Export functions globally immediately
window.openSearchOverlay = openSearchOverlay;
window.closeSearchOverlay = closeSearchOverlay;
window.clearSearchInput = clearSearchInput;
window.retrySearch = retrySearch;

document.addEventListener('DOMContentLoaded', () => {
    console.log('ANIZONEFLIX Production Suite LIVE');

    // --- High-Level Anti-Copy & Anti-DevTools Protection ---
    const hardenProtections = () => {
        // 1. Disable Right Click
        document.addEventListener('contextmenu', e => e.preventDefault());

        // 2. Disable Key Shortcuts
        document.addEventListener('keydown', e => {
            if (
                // Disable F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U, Ctrl+S, Ctrl+C, Ctrl+V, Ctrl+P
                e.key === 'F12' ||
                (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
                (e.ctrlKey && (e.key === 'u' || e.key === 's' || e.key === 'c' || e.key === 'v' || e.key === 'p' || e.key === 'a' || e.key === 'x'))
            ) {
                e.preventDefault();
                return false;
            }
        });

        // 3. Disable Drag & Drop
        document.addEventListener('dragstart', e => e.preventDefault());
        document.addEventListener('drop', e => e.preventDefault());

        // 4. Force selection clear (Continuous)
        setInterval(() => {
            const active = document.activeElement;
            if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.hasAttribute('contenteditable'))) {
                return;
            }
            if (window.getSelection) {
                window.getSelection().removeAllRanges();
            } else if (document.selection) {
                document.selection.empty();
            }
        }, 100);

        // 5. Anti-DevTools Debugger Loop (Deterrent)
        // This makes the browser pause if DevTools is open
        (function() {
            try {
                (function block() {
                    if (window.devtools && window.devtools.isOpen) {
                        debugger;
                    }
                    setTimeout(block, 1000);
                })();
            } catch (e) {}
        })();

        // 6. Basic Detection for 1DM / Downloader Apps (User Agent / Specific Behaviors)
        const checkDownloader = () => {
            const ua = navigator.userAgent.toLowerCase();
            if (ua.includes('1dm') || ua.includes('idm') || ua.includes('adm') || ua.includes('downloader')) {
                // Potential downloader detected
                // We can't easily block them, but we can make it harder by obscuring links
                document.body.classList.add('downloader-detected');
            }
        };
        checkDownloader();
    };
    hardenProtections();

    // --- Interactive Elements: Ripple Effect ---
    const createRipple = (event) => {
        const button = event.currentTarget;
        const circle = document.createElement('span');
        const diameter = Math.max(button.clientWidth, button.clientHeight);
        const radius = diameter / 2;
        const rect = button.getBoundingClientRect();

        circle.style.width = circle.style.height = `${diameter}px`;
        circle.style.left = `${event.clientX - rect.left - radius}px`;
        circle.style.top = `${event.clientY - rect.top - radius}px`;
        circle.classList.add('ripple');

        const ripple = button.getElementsByClassName('ripple')[0];
        if (ripple) { ripple.remove(); }
        button.appendChild(circle);

        setTimeout(() => circle.remove(), 600);
    };

    document.querySelectorAll('.btn-premium, button').forEach(btn => {
        btn.addEventListener('click', createRipple);
    });

    // --- Mobile Menu Toggle ---
    window.toggleMenu = (show) => {
        const mobileMenu = document.getElementById('mobile-menu');
        if (mobileMenu) {
            if (show) {
                mobileMenu.classList.remove('hidden');
                mobileMenu.classList.add('animate-fade-in');
            } else {
                mobileMenu.classList.add('hidden');
            }
        }
    };

    // --- Lazy Loading Enhancement ---
    if ('IntersectionObserver' in window) {
        const imgObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: '50px' });
        document.querySelectorAll('img[loading="lazy"]').forEach(img => imgObserver.observe(img));
    }

    // --- Auto-scroll Rows Pause/Resume ---
    document.querySelectorAll('.ott-row, .swiper').forEach(row => {
        row.addEventListener('mouseenter', () => {
            if (row.swiper && row.swiper.autoplay) row.swiper.autoplay.stop();
        });
        row.addEventListener('mouseleave', () => {
            if (row.swiper && row.swiper.autoplay) row.swiper.autoplay.start();
        });
    });

    // --- Floating Search Button ---
    const floatingSearch = document.querySelector('.search-btn-floating');
    if (floatingSearch) {
        const triggerSearch = (e) => {
            e.preventDefault();
            if (typeof window.openSearchOverlay === 'function') {
                window.openSearchOverlay();
            }
        };
        floatingSearch.addEventListener('click', triggerSearch);
        floatingSearch.addEventListener('touchstart', triggerSearch, { passive: false });
    }

    // Register event listeners
    const overlayInput = document.getElementById('overlay-search-input');
    if (overlayInput) {
        overlayInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            const clearBtn = document.getElementById('overlay-search-clear');

            if (clearBtn) {
                if (val) {
                    clearBtn.classList.remove('hidden');
                } else {
                    clearBtn.classList.add('hidden');
                }
            }

            if (searchDebounceTimeout) {
                clearTimeout(searchDebounceTimeout);
            }

            if (!val) {
                const resultsContainer = document.getElementById('overlay-results-container');
                const searchStatus = document.getElementById('overlay-search-status');
                if (resultsContainer) resultsContainer.innerHTML = '';
                if (searchStatus) searchStatus.classList.add('hidden');
                return;
            }

            // 6. Debounce search requests (250–300ms) to prevent excessive API calls
            searchDebounceTimeout = setTimeout(() => {
                performOverlaySearch(val);
            }, 300);
        });

        // 10. Pressing Enter should perform the same search instantly (bypassing debounce)
        overlayInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = e.target.value.trim();
                if (searchDebounceTimeout) {
                    clearTimeout(searchDebounceTimeout);
                }
                if (val) {
                    performOverlaySearch(val);
                }
            }
        });
    }

    // Escape key to close search overlay
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSearchOverlay();
        }
    });

    // Close on overlay background click
    const searchOverlay = document.getElementById('search-overlay');
    if (searchOverlay) {
        searchOverlay.addEventListener('click', (e) => {
            if (e.target === searchOverlay) {
                closeSearchOverlay();
            }
        });
    }

    // Global intercept search links
    const handleSearchInterception = (e) => {
        const link = e.target.closest('a');
        if (link) {
            const href = link.getAttribute('href');
            if (href) {
                if (href === '/search') {
                    e.preventDefault();
                    openSearchOverlay();
                    // Close mobile menu if open
                    if (typeof window.toggleMenu === 'function') {
                        window.toggleMenu(false);
                    }
                } else if (href.startsWith('/search?q=')) {
                    e.preventDefault();
                    const query = decodeURIComponent(href.split('/search?q=')[1]);
                    openSearchOverlay(query);
                    // Close mobile menu if open
                    if (typeof window.toggleMenu === 'function') {
                        window.toggleMenu(false);
                    }
                }
            }
        }
    };

    document.addEventListener('click', handleSearchInterception);
    document.addEventListener('touchstart', (e) => {
        const link = e.target.closest('a');
        if (link) {
            const href = link.getAttribute('href');
            if (href && (href === '/search' || href.startsWith('/search?q='))) {
                handleSearchInterception(e);
            }
        }
    }, { passive: false });
});
