(() => {
  'use strict';
  const slides = [...document.querySelectorAll('.slide')];
  const controls = document.querySelector('.controls');
  const previous = document.getElementById('previous');
  const next = document.getElementById('next');
  const overview = document.getElementById('overview');
  const fullscreen = document.getElementById('fullscreen');
  let current = 0;
  let allVisible = false;

  function hashIndex() {
    const match = /^#slide-(\d+)$/.exec(location.hash);
    return match ? Math.max(0, Math.min(slides.length - 1, Number(match[1]) - 1)) : 0;
  }

  function render(index, updateHash = true) {
    current = Math.max(0, Math.min(slides.length - 1, index));
    slides.forEach((slide, position) => {
      slide.classList.toggle('active', position === current);
      slide.setAttribute('aria-hidden', String(!allVisible && position !== current));
    });
    previous.disabled = current === 0;
    next.disabled = current === slides.length - 1;
    document.getElementById('page-count').textContent = `${current + 1} / ${slides.length}`;
    document.getElementById('progress').style.width = `${((current + 1) / slides.length) * 100}%`;
    document.title = `${current + 1}/${slides.length} · 机器人何时需要重新看懂场景？`;
    if (updateHash && location.hash !== `#slide-${current + 1}`) {
      history.replaceState(null, '', `#slide-${current + 1}`);
    }
    if (allVisible) slides[current].scrollIntoView({ behavior: 'auto', block: 'start' });
    else {
      window.scrollTo(0, 0);
      document.querySelector('.deck').scrollTop = 0;
    }
  }

  previous.addEventListener('click', () => render(current - 1));
  next.addEventListener('click', () => render(current + 1));
  overview.addEventListener('click', () => {
    allVisible = !allVisible;
    document.body.classList.toggle('overview', allVisible);
    overview.setAttribute('aria-pressed', String(allVisible));
    overview.textContent = allVisible ? '逐页' : '总览';
    render(current);
  });
  document.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
    const destination = { ArrowRight: current + 1, PageDown: current + 1, ArrowLeft: current - 1, PageUp: current - 1, Home: 0, End: slides.length - 1 }[event.key];
    if (destination !== undefined) {
      event.preventDefault();
      render(destination);
    }
  });
  fullscreen.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      fullscreen.textContent = '请用浏览器全屏';
    }
  });
  if (!document.documentElement.requestFullscreen) fullscreen.hidden = true;
  document.addEventListener('fullscreenchange', () => {
    fullscreen.textContent = document.fullscreenElement ? '退出全屏' : '全屏';
  });
  document.getElementById('print').addEventListener('click', () => window.print());
  window.addEventListener('hashchange', () => render(hashIndex(), false));
  window.addEventListener('beforeprint', () => slides.forEach(slide => slide.removeAttribute('aria-hidden')));
  window.addEventListener('afterprint', () => render(current, false));
  document.body.classList.add('enhanced');
  controls.hidden = false;
  render(hashIndex(), false);
})();
