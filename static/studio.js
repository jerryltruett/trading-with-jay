(() => {
  'use strict';
  const root = document.querySelector('#live-studio');
  if (!root) return;
  const authenticated = root.dataset.authenticated === 'true';
  const canHost = root.dataset.canHost === 'true';
  const $ = (id) => document.getElementById(id);
  const mainVideo = $('studio-main-video');
  const cameraVideo = $('studio-camera-video');
  const cameraButton = $('studio-camera');
  const screenButton = $('studio-screen');
  const screenChangeButton = $('studio-screen-change');
  const shareOptions = $('studio-share-options');
  const shareMonitorButton = $('studio-share-monitor');
  const shareWindowButton = $('studio-share-window');
  const shareCancelButton = $('studio-share-cancel');
  const screenSharingSupported = Boolean(window.isSecureContext && navigator.mediaDevices?.getDisplayMedia);
  const screenSupportMessage = !window.isSecureContext
    ? 'Screen sharing needs a secure HTTPS address or a localhost preview.'
    : 'Screen sharing is not supported in this browser. iPhone and Android browsers do not currently support it. You can stream your camera here, or share a screen from a supported desktop browser.';
  const microphoneButton = $('studio-mic');
  const startButton = $('studio-start');
  const stopButton = $('studio-stop');
  const watchButton = $('studio-watch');
  const leaveButton = $('studio-leave');
  const playButton = $('studio-play');
  const titleInput = $('studio-title-input');
  const saveTitleButton = $('studio-save-title');
  const chatInput = $('studio-chat-input');
  const chatSend = $('studio-chat-send');
  const peers = new Map();
  const pendingIce = new Map();
  const chatIds = new Set();
  function viewerId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
    else for (let index = 0; index < bytes.length; index++) bytes[index] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  let viewerPeer = viewerId();
  let iceServers = [];
  try { iceServers = JSON.parse($('studio-ice-servers')?.textContent || '[]'); } catch (_) { /* Local connections can use an empty ICE configuration. */ }
  let room = {active: false, session_id: null, is_host: false};
  let cameraStream = null;
  let screenStream = null;
  let isBroadcasting = false;
  let isWatching = false;
  let signalCursor = 0;
  let chatCursor = 0;
  let sessionForChat = null;
  let chatGeneration = 0;
  let chatSending = false;
  let signalGeneration = 0;
  let closing = false;
  let signalTimer = null;
  let signalPolling = null;
  let busy = false;
  let remoteStream = null;
  let mediaGeneration = 0;
  let screenOperations = 0;
  let sourceSwitch = null;

  function csrf() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || document.cookie.split('; ').find((part) => part.startsWith('csrftoken='))?.slice(10) || '';
  }
  async function api(path, body, keepalive = false) {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {'Accept': 'application/json'} : {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: body === undefined ? undefined : JSON.stringify(body),
      keepalive,
    });
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('The room could not load. Please refresh and try again.'); }
    if (!response.ok) {
      const error = new Error(data.error || 'That action could not be completed.');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function message(text, error = false) {
    const node = $('studio-message');
    node.textContent = text;
    node.hidden = !text;
    node.classList.toggle('is-error', error);
  }
  function mediaError(error, type) {
    if (!window.isSecureContext || !navigator.mediaDevices) return 'Camera and screen sharing need HTTPS, or a localhost preview. Open this site using a secure address.';
    if (error.name === 'NotAllowedError') return `${type} access was not enabled. Choose the control again when you want to grant access.`;
    if (error.name === 'NotFoundError') return 'No available camera or microphone was found. Check your devices and try again.';
    if (error.name === 'NotReadableError') return 'Another app may be using your camera or microphone. Close it and try again.';
    return error.message || `${type} could not start. Please try again.`;
  }
  function screenError(error) {
    if (!screenSharingSupported) return screenSupportMessage;
    if (error.name === 'NotAllowedError') return 'Screen sharing was cancelled or permission was not granted. Your current video stays unchanged.';
    if (error.name === 'NotFoundError') return 'No shareable screen or app window was found. Open the app you want to share and try again.';
    if (error.name === 'NotReadableError') return 'Your browser could not capture that screen or app window. Check your system’s screen recording permissions and try again.';
    if (error.name === 'InvalidStateError') return 'Choose a sharing option again while this window is active.';
    return error.message || 'Screen sharing could not start. Please try again.';
  }
  function setShareOptions(open, focus = false) {
    if (!shareOptions) return;
    shareOptions.hidden = !open;
    screenButton?.setAttribute('aria-expanded', String(open));
    screenChangeButton?.setAttribute('aria-expanded', String(open));
    if (focus) (open ? (screenSharingSupported ? shareMonitorButton : shareCancelButton) : (screenStream ? screenChangeButton : screenButton))?.focus();
  }
  function currentVideoTrack() {
    return screenStream?.getVideoTracks().find((track) => track.readyState === 'live') || cameraStream?.getVideoTracks().find((track) => track.readyState === 'live') || null;
  }
  function currentAudioTrack() { return cameraStream?.getAudioTracks().find((track) => track.readyState === 'live') || null; }
  function updatePreview() {
    if (isWatching) return;
    mainVideo.muted = true;
    mainVideo.srcObject = screenStream || cameraStream;
    cameraVideo.srcObject = cameraStream;
    cameraVideo.hidden = !(screenStream && cameraStream);
    if (mainVideo.srcObject) mainVideo.play().catch(() => {});
    if (!cameraVideo.hidden) cameraVideo.play().catch(() => {});
  }
  function updateControls() {
    const controlsBusy = busy || screenOperations > 0;
    const hasVideo = Boolean(currentVideoTrack());
    if (cameraButton) {
      cameraButton.textContent = cameraStream ? 'Release camera & mic' : 'Enable camera & mic';
      cameraButton.disabled = controlsBusy || isBroadcasting || isWatching;
    }
    if (screenButton) {
      screenButton.textContent = screenStream ? 'Stop sharing screen' : 'Share screen';
      screenButton.disabled = controlsBusy || isWatching;
    }
    if (screenChangeButton) {
      screenChangeButton.hidden = !screenStream;
      screenChangeButton.disabled = controlsBusy || isWatching;
    }
    for (const button of [shareMonitorButton, shareWindowButton]) if (button) button.disabled = controlsBusy || isWatching || !screenSharingSupported;
    if (shareCancelButton) shareCancelButton.disabled = controlsBusy;
    if ($('studio-screen-support')) {
      $('studio-screen-support').hidden = screenSharingSupported;
      $('studio-screen-support').textContent = screenSharingSupported ? '' : screenSupportMessage;
    }
    if (microphoneButton) {
      const audio = currentAudioTrack();
      microphoneButton.disabled = !audio;
      microphoneButton.textContent = audio?.enabled ? 'Mute microphone' : 'Unmute microphone';
      microphoneButton.setAttribute('aria-pressed', String(Boolean(audio && !audio.enabled)));
    }
    if (startButton) startButton.disabled = controlsBusy || !hasVideo || isBroadcasting || room.active;
    if (stopButton) stopButton.disabled = controlsBusy || !(isBroadcasting || (room.active && room.is_host));
    if (saveTitleButton) saveTitleButton.disabled = controlsBusy || !(isBroadcasting || (room.active && room.is_host));
    if (watchButton) watchButton.disabled = controlsBusy || !room.active || isWatching || isBroadcasting;
    if (leaveButton) leaveButton.hidden = !isWatching;
    if (watchButton) watchButton.hidden = isWatching;
    if ($('studio-viewer-controls')) $('studio-viewer-controls').hidden = canHost && (!room.active || room.is_host);
    if (chatInput) chatInput.disabled = !room.active;
    if (chatSend) chatSend.disabled = !room.active || chatSending;
    const status = $('studio-room-status');
    status.textContent = room.active ? 'Live now' : 'Room offline';
    status.classList.toggle('is-live', Boolean(room.active));
    $('studio-session-title').textContent = room.title || 'Trading with Jay — live session';
    $('studio-host-name').textContent = `Hosted by ${room.host_name || 'Jay'}`;
    const showingVideo = isWatching ? Boolean(remoteStream) : hasVideo;
    $('studio-state-layer').hidden = showingVideo;
    $('studio-video-label').hidden = !showingVideo;
    $('studio-video-label').textContent = isBroadcasting || isWatching ? 'Live session' : 'Private preview · not broadcasting';
    if (!showingVideo) {
      $('studio-stage-kicker').textContent = room.active ? 'Live session' : 'The live room';
      $('studio-stage-title').textContent = isWatching ? 'Connecting to the session…' : room.active ? 'The session is live.' : 'The room is offline.';
      $('studio-stage-copy').textContent = isWatching ? 'Waiting for the host’s camera or screen.' : room.active ? authenticated ? 'Select Watch live to join the broadcast.' : 'Join the community to watch the live session.' : 'The next live session will appear here.';
    }
    if ($('studio-viewer-hint')) $('studio-viewer-hint').textContent = isWatching ? 'You’re connected as a viewer. Your camera and microphone are off.' : room.active ? 'Your camera and microphone are not needed to watch.' : 'There isn’t an active broadcast yet.';
    if ($('studio-chat-help')) $('studio-chat-help').textContent = room.active ? 'Keep it helpful and respectful. Messages are visible to members in this session.' : 'Chat opens during a live session. Keep it helpful and respectful.';
    document.dispatchEvent(new Event('studio:mediachange'));
  }
  function stopTracks(stream) { stream?.getTracks().forEach((track) => track.stop()); }
  function closePeers() {
    signalGeneration++;
    peers.forEach((peer) => { peer.onicecandidate = null; peer.ontrack = null; peer.onconnectionstatechange = null; peer.close(); });
    peers.clear();
    pendingIce.clear();
    signalCursor = 0;
    clearTimeout(signalTimer);
    signalTimer = null;
  }
  function releaseMedia() {
    mediaGeneration++;
    setShareOptions(false);
    if (screenStream) screenStream.getVideoTracks().forEach((track) => { track.onended = null; });
    stopTracks(screenStream);
    stopTracks(cameraStream);
    screenStream = null;
    cameraStream = null;
    remoteStream = null;
    mainVideo.srcObject = null;
    cameraVideo.srcObject = null;
    cameraVideo.hidden = true;
  }
  function signalContext() {
    return {generation: signalGeneration, sessionId: room.session_id, peerId: isBroadcasting ? 'host' : viewerPeer, isHost: isBroadcasting};
  }
  function signalIsCurrent(context) {
    return !closing && context.generation === signalGeneration && room.active && String(context.sessionId) === String(room.session_id) && context.isHost === isBroadcasting && (context.isHost || (isWatching && context.peerId === viewerPeer));
  }
  function currentPeer(context, remotePeer, peer) { return signalIsCurrent(context) && peers.get(remotePeer) === peer; }
  function sendSignal(recipient, kind, payload = {}, keepalive = false, context = signalContext()) {
    if (!keepalive && !signalIsCurrent(context)) return Promise.resolve({});
    return api('/api/signals/', {session_id: context.sessionId, sender: context.peerId, recipient, kind, payload}, keepalive);
  }
  function makePeer(remotePeer, context) {
    const peer = new RTCPeerConnection({iceServers});
    peers.set(remotePeer, peer);
    peer.onicecandidate = (event) => {
      if (event.candidate && currentPeer(context, remotePeer, peer)) sendSignal(remotePeer, 'ice', event.candidate.toJSON(), false, context).catch((error) => { if (currentPeer(context, remotePeer, peer)) message(error.message, true); });
    };
    peer.onconnectionstatechange = () => {
      if (!currentPeer(context, remotePeer, peer)) return;
      if (peer.connectionState === 'failed') {
        if (isWatching) message('The video connection could not be established. Leave the session and try again. Cross-network sessions require the site’s relay configuration.', true);
        else message('A viewer’s video connection could not be established.', true);
      }
    };
    if (!isBroadcasting) {
      peer.ontrack = (event) => {
        if (!currentPeer(context, remotePeer, peer)) return;
        if (!remoteStream) remoteStream = new MediaStream();
        const tracks = event.streams[0]?.getTracks() || [event.track];
        for (const track of tracks) if (!remoteStream.getTracks().some((existing) => existing.id === track.id)) remoteStream.addTrack(track);
        mainVideo.srcObject = remoteStream;
        mainVideo.muted = false;
        mainVideo.play().then(() => { if (playButton && currentPeer(context, remotePeer, peer)) playButton.hidden = true; }).catch(() => { if (playButton && currentPeer(context, remotePeer, peer)) playButton.hidden = false; });
        updateControls();
      };
    }
    return peer;
  }
  async function flushIce(remotePeer, peer, context) {
    for (const candidate of pendingIce.get(remotePeer) || []) { if (!currentPeer(context, remotePeer, peer)) return; await peer.addIceCandidate(candidate); }
    if (!currentPeer(context, remotePeer, peer)) return;
    pendingIce.delete(remotePeer);
  }
  async function handleSignal(signal, context) {
    if (!signalIsCurrent(context) || String(signal.session_id) !== String(context.sessionId) || signal.recipient !== context.peerId) return;
    const remotePeer = signal.sender;
    if (signal.kind === 'join' && isBroadcasting) {
      // A joining viewer must receive the source that survives the current switch.
      if (sourceSwitch) await sourceSwitch;
      if (!signalIsCurrent(context)) return;
      if (peers.has(remotePeer)) return;
      const peer = makePeer(remotePeer, context);
      const tracks = [currentVideoTrack(), currentAudioTrack()].filter(Boolean);
      const stream = new MediaStream(tracks);
      tracks.forEach((track) => peer.addTrack(track, stream));
      const offer = await peer.createOffer();
      if (!currentPeer(context, remotePeer, peer)) return;
      await peer.setLocalDescription(offer);
      if (!currentPeer(context, remotePeer, peer)) return;
      await sendSignal(remotePeer, 'offer', peer.localDescription.toJSON(), false, context);
    } else if (signal.kind === 'offer' && isWatching && remotePeer === 'host') {
      const oldPeer = peers.get('host');
      if (oldPeer) oldPeer.close();
      const peer = makePeer('host', context);
      await peer.setRemoteDescription(signal.payload);
      if (!currentPeer(context, 'host', peer)) return;
      await flushIce('host', peer, context);
      if (!currentPeer(context, 'host', peer)) return;
      const answer = await peer.createAnswer();
      if (!currentPeer(context, 'host', peer)) return;
      await peer.setLocalDescription(answer);
      if (!currentPeer(context, 'host', peer)) return;
      await sendSignal('host', 'answer', peer.localDescription.toJSON(), false, context);
    } else if (signal.kind === 'answer' && isBroadcasting) {
      const peer = peers.get(remotePeer);
      if (peer) { await peer.setRemoteDescription(signal.payload); if (currentPeer(context, remotePeer, peer)) await flushIce(remotePeer, peer, context); }
    } else if (signal.kind === 'ice') {
      const peer = peers.get(remotePeer);
      if (peer?.remoteDescription) await peer.addIceCandidate(signal.payload);
      else { const queue = pendingIce.get(remotePeer) || []; queue.push(signal.payload); pendingIce.set(remotePeer, queue); }
    } else if (signal.kind === 'leave') {
      peers.get(remotePeer)?.close();
      peers.delete(remotePeer);
      pendingIce.delete(remotePeer);
      if (isWatching && remotePeer === 'host') { leaveSession(false); message('The host has ended this video connection.'); }
    }
  }
  async function pollSignals() {
    if (closing || !(isBroadcasting || isWatching) || !room.active) return;
    const context = signalContext();
    if (signalPolling === context.generation) return;
    signalPolling = context.generation;
    try {
      const data = await api(`/api/signals/?peer=${encodeURIComponent(context.peerId)}&after=${signalCursor}&session_id=${encodeURIComponent(context.sessionId)}`);
      if (!signalIsCurrent(context)) return;
      for (const signal of data.signals || []) {
        try { await handleSignal(signal, context); } catch (error) { if (signalIsCurrent(context)) message(error.message || 'The video connection could not be completed.', true); }
        if (!signalIsCurrent(context)) return;
        signalCursor = Math.max(signalCursor, Number(signal.id) || 0);
      }
      signalCursor = Math.max(signalCursor, Number(data.newest_id) || 0);
    } catch (error) {
      if (signalIsCurrent(context) && error.status === 409) await refreshRoom();
      else if (signalIsCurrent(context)) message(error.message, true);
    } finally {
      if (signalPolling === context.generation) signalPolling = null;
      if (signalIsCurrent(context)) signalTimer = setTimeout(pollSignals, 1200);
    }
  }
  async function replaceVideoTrack() {
    const track = currentVideoTrack();
    if (!track && isBroadcasting) { await endBroadcast(); return; }
    await Promise.all(Array.from(peers.values()).map(async (peer) => {
      const sender = peer.getSenders().find((item) => item.track?.kind === 'video');
      if (sender) await sender.replaceTrack(track);
    }));
    updatePreview();
    updateControls();
  }
  async function endScreen() {
    if (!screenStream) return;
    screenOperations++;
    mediaGeneration++;
    screenStream.getVideoTracks().forEach((track) => { track.onended = null; });
    stopTracks(screenStream);
    screenStream = null;
    updatePreview(); updateControls();
    try {
      if (sourceSwitch) await sourceSwitch;
      if (!closing) await replaceVideoTrack();
    } finally { screenOperations--; updateControls(); }
  }
  async function cameraAction() {
    if (isBroadcasting) return;
    busy = true; updateControls(); message('');
    try {
      if (cameraStream) { stopTracks(cameraStream); cameraStream = null; }
      else {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable in this browser.');
        cameraStream = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}}, audio: true});
        cameraStream.getVideoTracks().forEach((track) => { track.onended = () => { if (!screenStream && isBroadcasting) endBroadcast().catch((error) => message(error.message, true)); else { updatePreview(); updateControls(); } }; });
        message('Camera and microphone enabled. This is a private preview until you select Go live.');
      }
      updatePreview();
    } catch (error) { message(mediaError(error, 'Camera and microphone'), true); }
    finally { busy = false; updateControls(); }
  }
  async function screenAction(surface) {
    if (busy || screenOperations || isWatching || closing) return;
    if (!screenSharingSupported) { message(screenSupportMessage, true); return; }
    const generation = mediaGeneration;
    let candidate = null;
    let finishSwitch = null;
    screenOperations++;
    busy = true; updateControls(); message('');
    setShareOptions(false);
    try {
      // The native picker must open directly from this click, before any other await.
      // displaySurface is a preference; the browser still lets the person choose.
      candidate = await navigator.mediaDevices.getDisplayMedia({video: {displaySurface: surface}, audio: false});
      if (closing || generation !== mediaGeneration) { stopTracks(candidate); candidate = null; return; }
      const track = candidate.getVideoTracks().find((item) => item.readyState === 'live');
      if (!track) throw new Error('The selected source has no live video. Please choose another screen or app window.');
      sourceSwitch = new Promise((resolve) => { finishSwitch = resolve; });
      const senders = Array.from(peers, ([id, peer]) => ({id, peer, sender: peer.getSenders().find((item) => item.track?.kind === 'video')})).filter((item) => item.sender);
      const restoreCurrentSource = async () => {
        let restoredGeneration;
        do {
          restoredGeneration = mediaGeneration;
          const fallback = currentVideoTrack();
          const remaining = senders.filter(({id, peer}) => !closing && peers.get(id) === peer);
          const rollback = await Promise.allSettled(remaining.map(({sender}) => sender.replaceTrack(fallback)));
          rollback.forEach((result, index) => {
            const {id, peer} = remaining[index];
            if (result.status === 'rejected' && peers.get(id) === peer) {
              peer.close(); peers.delete(id); pendingIce.delete(id);
            }
          });
        } while (!closing && restoredGeneration !== mediaGeneration);
      };
      const replacements = await Promise.allSettled(senders.map(({sender}) => sender.replaceTrack(track)));
      if (closing || generation !== mediaGeneration) {
        await restoreCurrentSource();
        stopTracks(candidate); candidate = null; return;
      }
      if (track.readyState !== 'live' || replacements.some((result) => result.status === 'rejected')) {
        await restoreCurrentSource();
        if (track.readyState !== 'live') throw new Error('The selected source closed before it could be shared. Your previous video was kept.');
        throw new Error('The shared source could not change for every viewer. Your previous video was kept; disconnected viewers may need to rejoin.');
      }
      const previousScreen = screenStream;
      const selected = candidate;
      screenStream = selected;
      candidate = null;
      selected.getVideoTracks().forEach((item) => { item.onended = () => { if (screenStream === selected) endScreen().catch((error) => message(screenError(error), true)); }; });
      previousScreen?.getVideoTracks().forEach((item) => { item.onended = null; });
      stopTracks(previousScreen);
      updatePreview();
      message(isBroadcasting ? 'Your selected source is now being broadcast.' : 'Your selected source is in private preview. Select Go live when you’re ready.');
    } catch (error) { stopTracks(candidate); if (!closing && generation === mediaGeneration) message(screenError(error), true); }
    finally {
      if (finishSwitch) { sourceSwitch = null; finishSwitch(); }
      screenOperations--; busy = false; updateControls();
    }
  }
  async function startBroadcast() {
    if (!currentVideoTrack()) return;
    if (!window.RTCPeerConnection) { message('This browser does not support live video. Try a current browser.', true); return; }
    busy = true; updateControls(); message('');
    try {
      const data = await api('/api/live/', {action: 'start', title: titleInput.value.trim() || 'Trading with Jay — live session'});
      room = data;
      syncChatSession();
      closePeers();
      isBroadcasting = true;
      isWatching = false;
      signalCursor = 0;
      updatePreview();
      message('You are live. Members can now watch your camera or selected screen.');
      pollSignals();
    } catch (error) { message(error.message, true); }
    finally { busy = false; updateControls(); }
  }
  async function endBroadcast() {
    if (!isBroadcasting && !(room.active && room.is_host)) return;
    busy = true; updateControls();
    try {
      room = await api('/api/live/', {action: 'stop'});
      syncChatSession();
      isBroadcasting = false;
      closePeers();
      releaseMedia();
      message('Broadcast ended. Your camera, microphone, and screen share have been released.');
    } catch (error) { message(`The room could not confirm the broadcast ended. ${error.message} Your media has been stopped.`, true); isBroadcasting = false; closePeers(); releaseMedia(); }
    finally { busy = false; updateControls(); }
  }
  async function watchSession() {
    let context = null;
    busy = true; updateControls(); message('');
    try {
      await refreshRoom();
      if (!room.active) throw new Error('There isn’t an active broadcast yet.');
      if (!window.RTCPeerConnection) throw new Error('This browser does not support live video. Try a current browser.');
      closePeers();
      viewerPeer = viewerId();
      remoteStream = null;
      isWatching = true;
      isBroadcasting = false;
      mainVideo.srcObject = null;
      cameraVideo.hidden = true;
      context = signalContext();
      await sendSignal('host', 'join', {}, false, context);
      if (!signalIsCurrent(context)) return;
      pollSignals();
    } catch (error) { if (!context || signalIsCurrent(context)) { isWatching = false; closePeers(); busy = false; message(error.message, true); updateControls(); } }
    finally { if (!context || signalIsCurrent(context)) { busy = false; updateControls(); } }
  }
  function leaveSession(notify = true) {
    if (notify && isWatching && room.active) sendSignal('host', 'leave').catch(() => {});
    isWatching = false;
    busy = false;
    closePeers();
    remoteStream = null;
    mainVideo.srcObject = null;
    if (playButton) playButton.hidden = true;
    updatePreview(); updateControls();
  }
  async function refreshRoom() {
    const next = await api('/api/live/');
    const changedSession = String(room.session_id) !== String(next.session_id);
    if ((!next.active || changedSession) && isWatching) leaveSession(false);
    if ((!next.active || changedSession || !next.is_host) && isBroadcasting) {
      isBroadcasting = false; closePeers(); releaseMedia(); message('This broadcast has ended. Your media has been released.');
    }
    room = next;
    syncChatSession();
    if (changedSession && titleInput && next.is_host) titleInput.value = next.title || titleInput.value;
    updateControls();
  }
  async function pollRoom() {
    if (closing) return;
    try { await refreshRoom(); } catch (error) { message(error.message, true); }
    if (!closing) setTimeout(pollRoom, 4000);
  }
  function addChatMessage(item) {
    if (chatIds.has(item.id)) return;
    chatIds.add(item.id);
    if (chatIds.size > 500) chatIds.delete(chatIds.values().next().value);
    const feed = $('studio-chat-feed');
    const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 100;
    const article = document.createElement('article');
    article.className = 'studio-chat-message';
    const header = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = item.user;
    header.append(name);
    if (item.is_host) { const badge = document.createElement('span'); badge.className = 'studio-host-badge'; badge.textContent = 'Host'; header.append(badge); }
    const time = document.createElement('time');
    const date = new Date(item.created_at);
    time.dateTime = item.created_at;
    time.textContent = Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    header.append(time);
    const body = document.createElement('p');
    body.textContent = item.body;
    article.append(header, body);
    feed.append(article);
    $('studio-chat-empty')?.remove();
    while (feed.children.length > 200) feed.firstElementChild.remove();
    if (nearBottom) feed.scrollTop = feed.scrollHeight;
  }
  function syncChatSession() {
    if (!authenticated) return;
    const sessionId = room.active ? room.session_id : null;
    if (String(sessionForChat) === String(sessionId)) return;
    sessionForChat = sessionId;
    chatGeneration++;
    chatSending = false;
    chatCursor = 0;
    chatIds.clear();
    if (chatInput) chatInput.value = '';
    $('studio-chat-feed').replaceChildren();
    const empty = document.createElement('p');
    empty.id = 'studio-chat-empty'; empty.className = 'studio-chat-empty';
    empty.textContent = 'No messages yet. Ask a question during a live session.';
    $('studio-chat-feed').append(empty);
  }
  function chatContext() { return {generation: chatGeneration, sessionId: room.session_id}; }
  function chatIsCurrent(context) {
    return !closing && room.active && context.generation === chatGeneration && String(context.sessionId) === String(room.session_id);
  }
  async function pollChat() {
    if (closing || !authenticated) return;
    let context = null;
    try {
      syncChatSession();
      if (!room.active || !room.session_id) return;
      context = chatContext();
      const data = await api(`/api/chat/?after=${chatCursor}&session_id=${encodeURIComponent(context.sessionId)}`);
      if (!chatIsCurrent(context) || String(data.session_id) !== String(context.sessionId)) return;
      (data.messages || []).forEach(addChatMessage);
      chatCursor = Math.max(chatCursor, Number(data.newest_id) || 0);
    } catch (error) {
      if (context && chatIsCurrent(context)) {
        if (error.status === 409) await refreshRoom();
        else message(error.message, true);
      }
    } finally { if (!closing) setTimeout(pollChat, 3000); }
  }
  function selectPanel(panel, focus = false) {
    ['chat', 'notes'].forEach((name) => {
      const selected = name === panel;
      $(`studio-${name}-tab`).setAttribute('aria-selected', String(selected));
      $(`studio-${name}-tab`).tabIndex = selected ? 0 : -1;
      $(`session-${name}`).hidden = !selected;
    });
    if (focus) $(`studio-${panel}-tab`).focus();
  }
  ['chat', 'notes'].forEach((name) => {
    const tab = $(`studio-${name}-tab`);
    tab.addEventListener('click', () => selectPanel(name));
    tab.addEventListener('keydown', (event) => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); selectPanel(event.key === 'Home' ? 'chat' : event.key === 'End' ? 'notes' : name === 'chat' ? 'notes' : 'chat', true); }
    });
  });
  root.querySelectorAll('[data-studio-panel]').forEach((button) => button.addEventListener('click', () => { selectPanel(button.dataset.studioPanel); $(`studio-${button.dataset.studioPanel}-tab`).scrollIntoView({behavior: 'smooth', block: 'center'}); }));
  cameraButton?.addEventListener('click', cameraAction);
  screenButton?.addEventListener('click', () => {
    if (busy || isWatching || closing) return;
    if (screenStream) endScreen().catch((error) => message(screenError(error), true));
    else setShareOptions(shareOptions?.hidden !== false, true);
  });
  screenChangeButton?.addEventListener('click', () => { if (!busy && !isWatching) setShareOptions(shareOptions?.hidden !== false, true); });
  shareMonitorButton?.addEventListener('click', () => screenAction('monitor'));
  shareWindowButton?.addEventListener('click', () => screenAction('window'));
  shareCancelButton?.addEventListener('click', () => setShareOptions(false, true));
  shareOptions?.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !busy) { event.preventDefault(); setShareOptions(false, true); } });
  microphoneButton?.addEventListener('click', () => { const track = currentAudioTrack(); if (track) track.enabled = !track.enabled; updateControls(); });
  startButton?.addEventListener('click', startBroadcast);
  stopButton?.addEventListener('click', endBroadcast);
  saveTitleButton?.addEventListener('click', async () => {
    busy = true; updateControls();
    try { room = await api('/api/live/', {action: 'title', title: titleInput.value.trim()}); message('Session title updated.'); }
    catch (error) { message(error.message, true); }
    finally { busy = false; updateControls(); }
  });
  watchButton?.addEventListener('click', watchSession);
  leaveButton?.addEventListener('click', () => { leaveSession(); message('You left the video session.'); });
  playButton?.addEventListener('click', () => { mainVideo.muted = false; mainVideo.play().then(() => { playButton.hidden = true; }).catch(() => message('Video playback could not start. Please leave and rejoin the session.', true)); });
  $('studio-chat-form')?.addEventListener('submit', async (event) => {
    event.preventDefault(); const body = chatInput.value.trim(); if (!body || !room.active || chatSending) return;
    const context = chatContext();
    chatSending = true; updateControls();
    try {
      const data = await api('/api/chat/', {body, session_id: context.sessionId});
      if (!chatIsCurrent(context) || String(data.session_id) !== String(context.sessionId)) return;
      if (data.message) addChatMessage(data.message);
      if (chatInput.value.trim() === body) chatInput.value = '';
      message('');
    } catch (error) { if (chatIsCurrent(context)) { if (error.status === 409) await refreshRoom(); else message(error.message, true); } }
    finally { if (context.generation === chatGeneration) chatSending = false; updateControls(); }
  });
  window.addEventListener('pagehide', () => {
    closing = true;
    if (isBroadcasting) api('/api/live/', {action: 'stop'}, true).catch(() => {});
    else if (isWatching && room.active) sendSignal('host', 'leave', {}, true).catch(() => {});
    closePeers(); releaseMedia();
  });
  updateControls();
  pollRoom();
  pollChat();
})();
