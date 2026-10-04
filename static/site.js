document.addEventListener('click', event => {
  document.querySelectorAll('.nav-menu[open]').forEach(menu => { if (!menu.contains(event.target) || event.target.closest('.nav-menu-panel a')) menu.removeAttribute('open'); });
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelectorAll('.nav-menu[open]').forEach(menu => { menu.removeAttribute('open'); menu.querySelector('summary').focus(); });
});
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-filter]').forEach(item => { item.classList.toggle('active', item === button); item.setAttribute('aria-pressed', item === button ? 'true' : 'false'); });
  document.querySelectorAll('[data-topic]').forEach(card => { card.hidden = button.dataset.filter !== 'all' && card.dataset.topic !== button.dataset.filter; });
}));
