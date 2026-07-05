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
        floatingSearch.addEventListener('click', () => {
            window.location.href = '/search';
        });
    }
});
