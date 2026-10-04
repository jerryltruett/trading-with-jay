(() => {
  const header = document.querySelector('.city-admin #header');
  if (!header) return;

  // Keep the sidebar below the sticky header when its links wrap.
  const updateHeaderHeight = () => {
    const height = Math.ceil(header.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--admin-header-height', `${height}px`);
  };
  updateHeaderHeight();
  if ('ResizeObserver' in window) {
    new ResizeObserver(updateHeaderHeight).observe(header);
  } else {
    window.addEventListener('resize', updateHeaderHeight);
  }
})();
