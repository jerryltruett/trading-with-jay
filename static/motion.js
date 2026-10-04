(() => {
  const scene = document.querySelector('[data-motion-scene]') || document.querySelector('.city-page');
  if (!scene) return;
  const cross = document.querySelector('.pointer-cross');
  const toggle = scene.querySelector('[data-motion-toggle]');
  if (!cross || !toggle) return;
  const first = cross.querySelector('.cross-one');
  const second = cross.querySelector('.cross-two');
  const point = cross.querySelector('circle');
  let motionEnabled = true;
  let target = {x: .66, y: .5};
  let current = {...target};
  let frame = 0;
  let running = true;
  const paint = () => {
    const width = cross.clientWidth;
    const height = cross.clientHeight;
    if (!width || !height) return;
    const x = current.x * width;
    const y = current.y * height;
    const slope = .55;
    cross.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    first.setAttribute('d', 'M 0 ' + (y - slope * x) + ' L ' + width + ' ' + (y + slope * (width - x)));
    second.setAttribute('d', 'M 0 ' + (y + slope * x) + ' L ' + width + ' ' + (y - slope * (width - x)));
    point.setAttribute('cx', x); point.setAttribute('cy', y);
    scene.style.setProperty('--pointer-x', ((current.x - .5) * 14).toFixed(2) + 'px');
    scene.style.setProperty('--pointer-y', ((current.y - .5) * 10).toFixed(2) + 'px');
    scene.style.setProperty('--type-turn', ((current.x - .5) * 12).toFixed(2) + 'deg');
  };
  const step = () => {
    frame = 0;
    if (!running || document.hidden) return;
    const difference = Math.abs(target.x - current.x) + Math.abs(target.y - current.y);
    current.x += (target.x - current.x) * .085;
    current.y += (target.y - current.y) * .085;
    paint();
    if (difference > .0002) frame = requestAnimationFrame(step);
  };
  const requestPaint = () => { if (!frame && running) frame = requestAnimationFrame(step); };
  const setMotion = enabled => {
    motionEnabled = enabled;
    scene.classList.toggle('motion-enabled', enabled);
    toggle.textContent = enabled ? 'Motion: on' : 'Motion: off';
    toggle.setAttribute('aria-pressed', String(enabled));
    if (!enabled) { cancelAnimationFrame(frame); frame = 0; target = {x:.66,y:.5}; current = {...target}; paint(); }
  };
  toggle.addEventListener('click', () => setMotion(!motionEnabled));
  document.addEventListener('pointermove', event => {
    if (!motionEnabled || event.pointerType === 'touch') return;
    const bounds = cross.getBoundingClientRect();
    target = {x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)), y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))};
    requestPaint();
  });
  document.addEventListener('pointerleave', () => { if (!motionEnabled) return; target = {x:.66,y:.5}; requestPaint(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else requestPaint(); });
  window.addEventListener('resize', paint);
  window.addEventListener('pagehide', () => { running = false; cancelAnimationFrame(frame); });
  setMotion(motionEnabled); paint();
})();
