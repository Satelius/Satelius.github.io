(() => {
  if (location.protocol === 'file:') return;
  try {
    if (sessionStorage.getItem('satelius-project-progress-access') === 'granted') return;
  } catch (_) {}
  location.replace('../../?redirect=tactile-rollouts-2026-10-05');
})();
