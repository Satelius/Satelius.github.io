/* Standalone meeting presentation. Diagrams illustrate references, not robot measurements. */
(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const slides = Array.from(document.querySelectorAll(".slide"));
  const previousButton = document.getElementById("prev-slide");
  const nextButton = document.getElementById("next-slide");
  const countLabel = document.getElementById("slide-count");
  const deckProgress = document.getElementById("deck-progress");
  let currentSlide = 0;
  let navigationTarget = null;
  let navigationDeadline = 0;

  function showSlideState(index) {
    if (!slides.length) return;
    currentSlide = Math.max(0, Math.min(slides.length - 1, index));
    if (countLabel) countLabel.textContent = `${currentSlide + 1} / ${slides.length}`;
    if (deckProgress) {
      deckProgress.style.width = `${((currentSlide + 1) / slides.length) * 100}%`;
      deckProgress.setAttribute("aria-valuenow", String(currentSlide + 1));
      deckProgress.setAttribute("aria-valuemin", "1");
      deckProgress.setAttribute("aria-valuemax", String(slides.length));
      deckProgress.setAttribute("aria-valuetext", `第 ${currentSlide + 1} 节，共 ${slides.length} 节`);
    }
    if (previousButton) previousButton.disabled = currentSlide === 0;
    if (nextButton) nextButton.disabled = currentSlide === slides.length - 1;
    slides.forEach((slide, slideIndex) => {
      if (slideIndex === currentSlide) slide.setAttribute("aria-current", "step");
      else slide.removeAttribute("aria-current");
    });
  }

  function navigateTo(index, behavior) {
    if (!slides.length) return;
    const target = Math.max(0, Math.min(slides.length - 1, index));
    navigationTarget = target;
    navigationDeadline = performance.now() + 1500;
    showSlideState(target);
    slides[target].scrollIntoView({
      block: "start",
      behavior: behavior || (reducedMotion.matches ? "instant" : "smooth"),
    });
  }

  previousButton?.addEventListener("click", () => navigateTo(currentSlide - 1));
  nextButton?.addEventListener("click", () => navigateTo(currentSlide + 1));
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    const target = event.target;
    if (target instanceof Element && target.closest(
      'input, select, textarea, video, audio, button, [contenteditable]:not([contenteditable="false"]), [role="slider"]',
    )) return;
    if (event.key === "ArrowRight" || event.key === "PageDown") {
      event.preventDefault();
      navigateTo(currentSlide + 1);
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      navigateTo(currentSlide - 1);
    }
  });

  function observeCurrentSlide() {
    if (!slides.length) return;
    const viewportHeight = window.innerHeight;
    let bestIndex = currentSlide;
    let bestVisible = -1;
    slides.forEach((slide, index) => {
      const rectangle = slide.getBoundingClientRect();
      const visiblePixels = Math.max(0, Math.min(rectangle.bottom, viewportHeight) - Math.max(rectangle.top, 0));
      const visible = visiblePixels / Math.max(1, Math.min(rectangle.height, viewportHeight));
      if (visible > bestVisible) {
        bestVisible = visible;
        bestIndex = index;
      }
    });
    if (navigationTarget !== null && performance.now() < navigationDeadline) {
      if (bestIndex !== navigationTarget) return;
      navigationTarget = null;
    } else navigationTarget = null;
    showSlideState(bestIndex);
  }

  if ("IntersectionObserver" in window) {
    const slideObserver = new IntersectionObserver(observeCurrentSlide, {
      threshold: [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1],
    });
    slides.forEach((slide) => slideObserver.observe(slide));
  }
  let scrollFrame = 0;
  window.addEventListener("scroll", () => {
    if (scrollFrame) return;
    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      observeCurrentSlide();
    });
  }, { passive: true });
  window.addEventListener("resize", observeCurrentSlide, { passive: true });
  showSlideState(0);
  requestAnimationFrame(observeCurrentSlide);

  // Only this schematic uses animation frames. Video playback remains browser-native.
  const motionSlider = document.getElementById("motion-progress");
  const motionButton = document.getElementById("motion-play");
  const linearDot = document.getElementById("linear-dot");
  const smoothDot = document.getElementById("smooth-dot");
  const linearValue = document.getElementById("linear-value");
  const smoothValue = document.getElementById("smooth-value");
  let motionPlaying = false;
  let motionFrame = 0;
  let previousMotionTime = null;
  let motionDirection = 1;
  let motionProgress = Math.max(0, Math.min(1, Number(motionSlider?.value || 0) / 100));

  function renderMotion(progress) {
    motionProgress = Math.max(0, Math.min(1, progress));
    const t = motionProgress;
    const smooth = 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5;
    linearDot?.setAttribute("cx", String(60 + 560 * t));
    smoothDot?.setAttribute("cx", String(60 + 560 * smooth));
    if (linearValue) linearValue.textContent = `${Math.round(t * 100)}%`;
    if (smoothValue) smoothValue.textContent = `${Math.round(smooth * 100)}%`;
    if (motionSlider) {
      motionSlider.value = String(t * 100);
      motionSlider.setAttribute("aria-valuetext", `时间进度 ${Math.round(t * 100)}%`);
    }
  }

  function updateMotionButton() {
    if (!motionButton) return;
    motionButton.textContent = motionPlaying ? "暂停示意" : "播放示意";
    motionButton.setAttribute("aria-pressed", String(motionPlaying));
  }

  function pauseMotion() {
    motionPlaying = false;
    cancelAnimationFrame(motionFrame);
    motionFrame = 0;
    previousMotionTime = null;
    updateMotionButton();
  }

  function advanceMotion(timestamp) {
    if (!motionPlaying) return;
    if (previousMotionTime !== null) {
      const elapsed = Math.min(80, timestamp - previousMotionTime);
      let progress = motionProgress + motionDirection * elapsed / 2000;
      if (progress >= 1) {
        progress = 2 - progress;
        motionDirection = -1;
      } else if (progress <= 0) {
        progress = -progress;
        motionDirection = 1;
      }
      renderMotion(progress);
    }
    previousMotionTime = timestamp;
    motionFrame = requestAnimationFrame(advanceMotion);
  }

  motionButton?.addEventListener("click", () => {
    if (!motionSlider) return;
    if (motionPlaying) pauseMotion();
    else {
      // No autoplay: even with reduced-motion, movement requires this explicit request.
      motionPlaying = true;
      previousMotionTime = null;
      if (motionProgress >= 1) motionDirection = -1;
      else if (motionProgress <= 0) motionDirection = 1;
      updateMotionButton();
      motionFrame = requestAnimationFrame(advanceMotion);
    }
  });
  motionSlider?.addEventListener("input", () => {
    pauseMotion();
    renderMotion(Number(motionSlider.value) / 100);
  });
  reducedMotion.addEventListener("change", pauseMotion);
  renderMotion(motionProgress);
  updateMotionButton();

  const videos = [document.getElementById("video-off"), document.getElementById("video-on")]
    .filter((video) => video instanceof HTMLVideoElement);
  const playVideosButton = document.getElementById("play-videos");
  const restartVideosButton = document.getElementById("restart-videos");
  const videoRate = document.getElementById("video-rate");
  const internalSeeks = new Map();
  let playbackRequest = 0;
  let lastDriftCorrection = -Infinity;

  function isPlaying(video) {
    return !video.paused && !video.ended;
  }

  function updateVideoButton() {
    if (!playVideosButton) return;
    const playing = videos.some(isPlaying);
    playVideosButton.textContent = playing ? "同步暂停" : "同步播放";
    playVideosButton.setAttribute("aria-pressed", String(playing));
  }

  function pauseVideos() {
    playbackRequest += 1;
    videos.forEach((video) => video.pause());
    updateVideoButton();
  }

  function seekVideo(video, requestedTime) {
    if (!Number.isFinite(requestedTime)) return;
    const duration = Number.isFinite(video.duration) ? video.duration : requestedTime;
    const targetTime = Math.max(0, Math.min(duration, requestedTime));
    if (Math.abs(video.currentTime - targetTime) < 0.015) return;
    internalSeeks.set(video, targetTime);
    try {
      video.currentTime = targetTime;
    } catch (_error) {
      internalSeeks.delete(video);
    }
  }

  async function playVideos() {
    const request = ++playbackRequest;
    const allFinished = videos.length > 0 && videos.every((video) => (
      video.ended || (Number.isFinite(video.duration) && video.currentTime >= video.duration - 0.02)
    ));
    if (allFinished) videos.forEach((video) => seekVideo(video, 0));
    const results = await Promise.allSettled(videos.filter((video) => !video.ended || allFinished)
      .map((video) => video.play()));
    if (request !== playbackRequest) {
      videos.forEach((video) => video.pause());
      return;
    }
    if (results.some((result) => result.status === "rejected") && playVideosButton) {
      playVideosButton.title = "浏览器限制了播放时，请使用各视频自己的播放键。";
    }
    updateVideoButton();
  }

  playVideosButton?.addEventListener("click", () => {
    if (videos.some(isPlaying)) pauseVideos();
    else void playVideos();
  });
  restartVideosButton?.addEventListener("click", () => {
    pauseVideos();
    videos.forEach((video) => seekVideo(video, 0));
    void playVideos();
  });

  function applyVideoRate() {
    const rate = Number(videoRate?.value || 1);
    if (![0.25, 0.5, 1].includes(rate)) return;
    videos.forEach((video) => { video.playbackRate = rate; });
  }
  videoRate?.addEventListener("change", applyVideoRate);
  applyVideoRate();

  videos.forEach((video) => {
    video.playsInline = true;
    ["play", "pause", "ended", "loadedmetadata", "error"].forEach((eventName) => {
      video.addEventListener(eventName, updateVideoButton);
    });
    video.addEventListener("seeked", () => {
      const internalTarget = internalSeeks.get(video);
      internalSeeks.delete(video);
      if (internalTarget !== undefined && Math.abs(video.currentTime - internalTarget) < 0.06) return;
      // Explicit scrubbing is shared; corrections during ordinary playback are sparse.
      videos.filter((other) => other !== video).forEach((other) => seekVideo(other, video.currentTime));
    });
  });

  const clockVideo = document.getElementById("video-on") || videos[0];
  clockVideo?.addEventListener("timeupdate", () => {
    if (videos.length !== 2 || !videos.every(isPlaying) || videos.some((video) => video.seeking || video.readyState < 2)) return;
    const now = performance.now();
    if (now - lastDriftCorrection < 1000) return;
    const otherVideo = videos.find((video) => video !== clockVideo);
    if (!otherVideo || !Number.isFinite(otherVideo.duration)) return;
    // Keep the shorter OFF at its final frame while ON finishes its declared suffix.
    if (clockVideo.currentTime >= otherVideo.duration - 0.12) return;
    if (Math.abs(otherVideo.currentTime - clockVideo.currentTime) > 0.12) {
      lastDriftCorrection = now;
      seekVideo(otherVideo, clockVideo.currentTime);
    }
  });
  updateVideoButton();

  function pauseBackgroundActivity() {
    pauseMotion();
    pauseVideos();
  }
  window.addEventListener("blur", pauseBackgroundActivity);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseBackgroundActivity();
  });
})();
