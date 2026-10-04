(() => {
  const feed = document.getElementById('lounge-feed');
  const form = document.getElementById('lounge-form');
  if (!feed || !form) return;
  const status = document.getElementById('lounge-status');
  const field = document.getElementById('lounge-body');
  let newest = Math.max(0, ...Array.from(feed.querySelectorAll('[data-message-id]')).map(item => Number(item.dataset.messageId)));
  let pending = false;
  const add = message => {
    if (feed.querySelector('[data-message-id="' + message.id + '"]')) return;
    document.getElementById('lounge-empty')?.remove();
    const article = document.createElement('article'); article.className = 'lounge-message'; article.dataset.messageId = message.id;
    const avatar = document.createElement('span'); avatar.className = 'message-avatar'; avatar.setAttribute('aria-hidden','true'); avatar.textContent = message.user.slice(0,1).toUpperCase();
    const content = document.createElement('div'); const meta = document.createElement('div'); meta.className = 'message-meta';
    const author = document.createElement('strong'); author.textContent = message.user;
    const time = document.createElement('time'); time.dateTime = message.created_at; time.textContent = new Date(message.created_at).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
    const body = document.createElement('p'); body.textContent = message.body;
    meta.append(author,time); content.append(meta,body); article.append(avatar,content); feed.append(article); newest = Math.max(newest, message.id);
  };
  const poll = async () => { if (pending || document.hidden) return; pending = true; try { const response = await fetch('/api/chat/?room=lounge&after=' + newest, {cache:'no-store'}); if (response.status === 401 || response.status === 403) { status.textContent = 'Please sign in again to continue.'; return; } if (!response.ok) throw new Error(); const data = await response.json(); data.messages.forEach(add); } catch { status.textContent = 'The connection paused. We’ll try again shortly.'; } finally { pending = false; } };
  form.addEventListener('submit', async event => { event.preventDefault(); const body = field.value.trim(); if (!body) return; const send = form.querySelector('button'); send.disabled = true; status.textContent = ''; try { const response = await fetch('/api/chat/', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({room:'lounge',body})}); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Your message could not be sent.'); field.value = ''; await poll(); } catch(error) { status.textContent = error.message; } finally { send.disabled = false; } });
  poll(); setInterval(poll, 4000);
})();
