(() => {
  if (location.protocol === 'file:') return;
  try {
    if (sessionStorage.getItem('satelius-project-progress-access') === 'granted') return;
  } catch (_) {}
  const base = new URL('.', document.currentScript.src);
  location.replace(new URL('../../?redirect=meta-smooth-success-2026-10-20', base));
})();
