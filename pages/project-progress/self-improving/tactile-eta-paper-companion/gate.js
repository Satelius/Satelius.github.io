(() => {
  if (location.protocol === 'file:') return;
  try {
    if (sessionStorage.getItem('satelius-project-progress-access') === 'granted') return;
  } catch (_) {}
  const base = new URL('.', document.currentScript.src);
  const destination = document.currentScript.dataset.redirect || (location.pathname.startsWith(new URL('overview/', base).pathname)
    ? 'tactile-eta-reproduction'
    : 'tactile-eta-paper-companion');
  location.replace(new URL('../../?redirect=' + encodeURIComponent(destination), base));
})();
