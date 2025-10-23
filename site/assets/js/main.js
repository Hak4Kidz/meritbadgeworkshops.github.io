// Mobile navigation toggle and a11y helpers
(function() {
  const toggle = document.querySelector('[data-nav-toggle]');
  const panel = document.querySelector('[data-nav-panel]');
  if (!toggle || !panel) return;

  const openNav = () => {
    panel.classList.add('open');
    toggle.setAttribute('aria-expanded', 'true');
    document.addEventListener('click', onDocClick, { capture: true });
    document.addEventListener('keydown', onKeydown);
  };
  const closeNav = () => {
    panel.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', onDocClick, { capture: true });
    document.removeEventListener('keydown', onKeydown);
  };
  const onDocClick = (e) => {
    if (!panel.contains(e.target) && !toggle.contains(e.target)) {
      closeNav();
    }
  };
  const onKeydown = (e) => {
    if (e.key === 'Escape') closeNav();
  };

  toggle.addEventListener('click', () => {
    const isOpen = panel.classList.contains('open');
    isOpen ? closeNav() : openNav();
  });
})();
