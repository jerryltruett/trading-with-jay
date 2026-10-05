(() => {
  'use strict';

  const video = document.getElementById('studio-main-video');
  const button = document.getElementById('studio-fullscreen');
  const status = document.getElementById('studio-fullscreen-status');
  if (!video || !button) return;

  let pending = false;
  let requestTimer = null;
  let operation = 0;
  let nativeFullscreen = false;
  let controlsSnapshot = null;
  let fullscreenError = '';
  let observedStream = null;
  const observedTracks = new Set();

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || document.webkitCurrentFullScreenElement || null;
  }

  function isFullscreen() {
    return fullscreenElement() === video || nativeFullscreen || video.webkitDisplayingFullscreen === true || video.webkitPresentationMode === 'fullscreen';
  }

  function fullscreenMethod() {
    if (typeof video.requestFullscreen === 'function' && document.fullscreenEnabled !== false) return video.requestFullscreen;
    if (document.webkitFullscreenEnabled !== false) {
      if (typeof video.webkitRequestFullscreen === 'function') return video.webkitRequestFullscreen;
      if (typeof video.webkitRequestFullScreen === 'function') return video.webkitRequestFullScreen;
    }
    // WebKit can report false until metadata arrives; keep the waiting state then.
    if (video.webkitSupportsFullscreen !== false || !hasVideo()) {
      if (typeof video.webkitEnterFullscreen === 'function') return video.webkitEnterFullscreen;
      if (typeof video.webkitEnterFullScreen === 'function') return video.webkitEnterFullScreen;
    }
    return null;
  }

  function hasVideo() {
    if (video.error || video.readyState < 1 || !video.videoWidth || !video.videoHeight) return false;
    if (typeof video.srcObject?.getVideoTracks === 'function') {
      return video.srcObject.getVideoTracks().some((track) => track.readyState === 'live' && track.muted !== true);
    }
    return Boolean(video.currentSrc || video.getAttribute('src'));
  }

  function setStatus(text, error = false) {
    if (!status) return;
    status.textContent = text;
    status.hidden = !text;
    status.classList.toggle('is-error', error);
  }

  function saveControls() {
    if (controlsSnapshot) return;
    controlsSnapshot = {present: video.hasAttribute('controls'), value: video.getAttribute('controls')};
    video.controls = true;
  }

  function restoreControls() {
    if (!controlsSnapshot) return;
    if (controlsSnapshot.present) video.setAttribute('controls', controlsSnapshot.value);
    else video.removeAttribute('controls');
    controlsSnapshot = null;
  }

  function clearRequest() {
    clearTimeout(requestTimer);
    requestTimer = null;
    pending = false;
  }

  function observeMedia() {
    const stream = typeof video.srcObject?.getVideoTracks === 'function' ? video.srcObject : null;
    if (stream !== observedStream) {
      observedStream?.removeEventListener('addtrack', refresh);
      observedStream?.removeEventListener('removetrack', refresh);
      observedStream = stream;
      observedStream?.addEventListener('addtrack', refresh);
      observedStream?.addEventListener('removetrack', refresh);
    }
    const tracks = new Set(stream?.getVideoTracks() || []);
    for (const track of observedTracks) {
      if (tracks.has(track)) continue;
      for (const event of ['ended', 'mute', 'unmute']) track.removeEventListener(event, refresh);
      observedTracks.delete(track);
    }
    for (const track of tracks) {
      if (observedTracks.has(track)) continue;
      for (const event of ['ended', 'mute', 'unmute']) track.addEventListener(event, refresh);
      observedTracks.add(track);
    }
  }

  function refresh() {
    observeMedia();
    const active = isFullscreen();
    const supported = Boolean(fullscreenMethod());
    const ready = hasVideo();
    const label = active ? 'Exit full screen' : 'Full screen';
    button.textContent = label;
    button.setAttribute('aria-label', active ? 'Exit live video full screen' : 'Show live video in full screen');
    button.setAttribute('aria-pressed', String(active));
    button.title = active ? 'Exit full screen' : 'Show live video in full screen';
    button.disabled = pending || (!active && (!supported || !ready));
    if (fullscreenError) setStatus(fullscreenError, true);
    else if (pending) setStatus(active ? 'Leaving full screen…' : 'Opening full screen…');
    else if (!supported) setStatus('Full screen is unavailable in this browser or page.');
    else if (!ready && !active) setStatus('Full screen will be available when the video starts.');
    else setStatus('');
  }

  function syncFullscreen() {
    operation++;
    clearRequest();
    fullscreenError = '';
    if (isFullscreen()) saveControls();
    else restoreControls();
    refresh();
  }

  async function toggleFullscreen() {
    if (pending) return;
    fullscreenError = '';
    const active = isFullscreen();
    const enter = fullscreenMethod();
    if (!active && (!enter || !hasVideo())) { refresh(); return; }

    const currentOperation = ++operation;
    pending = true;
    refresh();
    // Legacy WebKit calls return no promise; their events complete the request.
    requestTimer = setTimeout(() => {
      if (currentOperation !== operation) return;
      clearRequest();
      if (!isFullscreen()) {
        restoreControls();
        if (!active) fullscreenError = 'Full screen did not open. Try again or use another browser.';
      } else if (active) {
        fullscreenError = 'Full screen could not close. Use Escape or the video’s exit control.';
      }
      refresh();
    }, 4000);

    try {
      let result;
      if (active) {
        if (fullscreenElement() === video) {
          const exit = document.exitFullscreen || document.webkitExitFullscreen || document.webkitCancelFullScreen;
          if (typeof exit !== 'function') throw new Error('Fullscreen exit is unavailable.');
          result = exit.call(document);
        } else {
          const exit = video.webkitExitFullscreen || video.webkitExitFullScreen;
          if (typeof exit !== 'function') throw new Error('Native fullscreen exit is unavailable.');
          result = exit.call(video);
        }
      } else {
        saveControls();
        // Request the video itself so chat, labels, and camera previews are excluded.
        result = enter.call(video);
      }
      if (result && typeof result.then === 'function') {
        await result;
        if (currentOperation !== operation) return;
        clearRequest();
        if (!isFullscreen()) restoreControls();
        refresh();
      }
    } catch (_) {
      if (currentOperation !== operation) return;
      clearRequest();
      if (!isFullscreen()) restoreControls();
      fullscreenError = active ? 'Full screen could not close. Use Escape or the video’s exit control.' : 'Full screen could not open. Try again or use another browser.';
      refresh();
    }
  }

  button.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', syncFullscreen);
  document.addEventListener('webkitfullscreenchange', syncFullscreen);
  const onFullscreenError = () => {
    operation++;
    clearRequest();
    if (!isFullscreen()) restoreControls();
    fullscreenError = 'Full screen could not open. Try again or use another browser.';
    refresh();
  };
  video.addEventListener('fullscreenerror', onFullscreenError);
  video.addEventListener('webkitfullscreenerror', onFullscreenError);
  video.addEventListener('webkitbeginfullscreen', () => { nativeFullscreen = true; syncFullscreen(); });
  video.addEventListener('webkitendfullscreen', () => { nativeFullscreen = false; syncFullscreen(); });
  video.addEventListener('webkitpresentationmodechanged', () => {
    nativeFullscreen = video.webkitPresentationMode === 'fullscreen';
    syncFullscreen();
  });
  for (const event of ['loadedmetadata', 'loadeddata', 'playing', 'emptied', 'error']) video.addEventListener(event, refresh);
  document.addEventListener('studio:mediachange', refresh);
  window.TradingStudioDisplay = {refresh};
  refresh();
})();
