document.addEventListener('DOMContentLoaded', () => {
    console.log('ANIZONEFLIX Production Suite LIVE');

    // --- Anti-Copy Protection ---
    const disableProtections = () => {
        document.addEventListener('contextmenu', e => e.preventDefault());
        document.addEventListener('keydown', e => {
            if (
                e.ctrlKey && (
                    e.key === 'c' ||
                    e.key === 'v' ||
                    e.key === 'u' ||
                    e.key === 's' ||
                    e.key === 'a' ||
                    e.key === 'x'
                ) ||
                (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
                e.key === 'F12'
            ) {
                e.preventDefault();
                return false;
            }
        });
        document.addEventListener('dragstart', e => e.preventDefault());
        document.addEventListener('drop', e => e.preventDefault());
        document.addEventListener('selectstart', e => e.preventDefault());
    };
    disableProtections();

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
