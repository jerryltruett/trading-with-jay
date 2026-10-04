(() => {
  "use strict";
  const accounts = document.getElementById("card-accounts");
  const title = document.getElementById("card-title");
  const status = document.getElementById("card-status");
  const signin = document.getElementById("card-signin");
  let controller = new AbortController();
  let pageActive = true;
  let generation = 0;
  let token = "";
  const clear = () => {
    token = "";
    accounts.replaceChildren();
    accounts.hidden = true;
    signin.hidden = true;
    title.textContent = "Private login.";
    document.title = "Private login card · Trading with Jay";
    status.textContent = "Open your labelled QR code to view the login details.";
  };
  window.addEventListener("pagehide", () => { pageActive = false; generation += 1; controller.abort(); clear(); });
  window.addEventListener("pageshow", event => { if (event.persisted) clear(); });
  const unavailable = () => {
    clear();
    status.textContent = "This private card is unavailable. Use your current QR code or contact the site owner.";
  };
  const field = (label, value) => {
    const wrapper = document.createElement("div");
    wrapper.className = "access-field";
    const caption = document.createElement("span");
    caption.className = "access-field-label";
    caption.textContent = label;
    const row = document.createElement("div");
    row.className = "access-value-row";
    const content = document.createElement("span");
    content.className = "access-value";
    content.textContent = value;
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "access-copy";
    copy.textContent = "Copy";
    copy.setAttribute("aria-label", `Copy ${label.toLowerCase()}`);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(content.textContent);
        status.textContent = `${label} copied.`;
      } catch (_) {
        status.textContent = `Select the ${label.toLowerCase()} to copy it.`;
      }
    });
    row.append(content, copy);
    wrapper.append(caption, row);
    return wrapper;
  };
  const unlock = async () => {
    const currentGeneration = ++generation;
    controller.abort();
    controller = new AbortController();
    const submittedToken = token;
    token = "";
    const csrf = document.querySelector("#card-csrf input[name=csrfmiddlewaretoken]");
    status.textContent = "Opening your private login card…";
    try {
      const response = await fetch("/api/access-card/", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
        referrerPolicy: "no-referrer",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf ? csrf.value : ""},
        body: JSON.stringify({token: submittedToken})
      });
      if (!pageActive || currentGeneration !== generation) return;
      if (!response.ok) { unavailable(); return; }
      const card = await response.json();
      if (!pageActive || currentGeneration !== generation) return;
      if (typeof card.label !== "string" || !Array.isArray(card.accounts) || !card.accounts.length || card.accounts.length > 8 || card.accounts.some(account => typeof account.username !== "string" || typeof account.password !== "string")) {
        unavailable(); return;
      }
      title.textContent = card.label;
      document.title = `${card.label} · Trading with Jay`;
      accounts.replaceChildren();
      for (const account of card.accounts) {
        const section = document.createElement("section");
        section.className = "access-account";
        const heading = document.createElement("h3");
        heading.textContent = account.username;
        section.append(heading, field("Username", account.username), field("Password", account.password));
        accounts.append(section);
      }
      accounts.hidden = false;
      signin.hidden = false;
      status.textContent = "Use these details to sign in. Keep this card private.";
    } catch (_) {
      if (pageActive && currentGeneration === generation) unavailable();
    }
  };
  const openFromFragment = () => {
    const nextToken = window.location.hash.slice(1);
    if (nextToken === "main") return;
    controller.abort();
    generation += 1;
    clear();
    pageActive = true;
    if (window.location.hash) {
      try {
        window.history.replaceState(null, "", window.location.pathname);
      } catch (_) {
        unavailable();
        return;
      }
    }
    token = nextToken;
    if (!nextToken) return;
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) { unavailable(); return; }
    unlock();
  };
  window.addEventListener("hashchange", openFromFragment);
  openFromFragment();
})();
