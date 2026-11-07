/*! KagNode Account profile linking. Credentials stay in the application's server-side storage. */
(() => {
  if (
    typeof window === "undefined" ||
    typeof document === "undefined" ||
    typeof fetch !== "function" ||
    !document.body?.dataset
  )
    return;
  const app = document.body.dataset.knAccountApp;
  if (!app || (app === "vpn" && !document.querySelector(".app-shell"))) return;
  const endpoint =
    app === "vpn"
      ? "/manage/kagnode-account"
      : app === "media"
        ? "/api/v1/kagnode-account"
        : "/api/kagnode-account";
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  let current = null,
    loading = false,
    last = 0,
    polling = null,
    expiry = 0;
  const panels = new Set();
  async function headers() {
    const result = { Accept: "application/json" };
    if (app === "httpboot") {
      const value = sessionStorage.getItem("kagnode.httpboot.console");
      if (value) result.Authorization = "Bearer " + value;
    } else if (app === "cli") result["X-KagNode-Action"] = "profile";
    else if (app === "vpn")
      result["X-CSRF-Token"] =
        document.querySelector("input[name=csrf]")?.value || "";
    else if (app === "media")
      result["X-CSRF-Token"] =
        document.querySelector('meta[name="csrf-token"]')?.content || "";
    else {
      if (app === "authenticator") result["X-Requested-With"] = "Authentactor";
      const address =
        app === "mail"
          ? "/api/session"
          : app === "authenticator"
            ? "/api/status"
            : "/manage/status?view=overview";
      const response = await fetch(address, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw Error("Sign in locally to manage your profile.");
      const value = await response.json();
      result["X-CSRF-Token"] = value.csrf || "";
    }
    return result;
  }
  async function request(action = "state", data = {}) {
    if (app === "mail" && typeof window.KagNodeAccountRequest === "function")
      return window.KagNodeAccountRequest(action, data);
    const response = await fetch(endpoint, {
      method: action === "state" ? "GET" : "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        ...(await headers()),
        ...(action !== "state" ? { "Content-Type": "application/json" } : {}),
      },
      body:
        action === "state" ? undefined : JSON.stringify({ action, ...data }),
    });
    const value = await response
      .json()
      .catch(() => ({ error: "The account connection could not be loaded." }));
    if (!response.ok) {
      const error = Error(
        value.error || "The account connection could not be updated.",
      );
      error.status = response.status;
      throw error;
    }
    return value;
  }
  function photo(node, profile) {
    const old = node.querySelector(".kn-linked-avatar");
    if (!profile?.photo) {
      if (old) old.remove();
      node.classList.remove("kn-has-linked-photo");
      return;
    }
    if (old?.src === profile.photo) return;
    if (old) old.remove();
    const image = el("img", "", "kn-linked-avatar");
    image.alt = "";
    image.src = profile.photo;
    node.append(image);
    node.classList.add("kn-has-linked-photo");
  }
  function identity() {
    if (!current) return;
    const profile = current.enabled ? current.profile : null;
    document.querySelectorAll("[data-kn-account-name]").forEach((node) => {
      const next =
        profile?.name ||
        current.local_name ||
        node.dataset.knLocalName ||
        "Account";
      if (!node.dataset.knLocalName)
        node.dataset.knLocalName = node.textContent;
      if (node.textContent !== next) node.textContent = next;
    });
    document.querySelectorAll("[data-kn-account-avatar]").forEach((node) => {
      if (!node.dataset.knLocalInitials)
        node.dataset.knLocalInitials = node.textContent;
      photo(node, profile);
      if (node.tagName !== "BUTTON") {
        node.setAttribute("aria-hidden", "true");
        if (!profile?.photo) {
          const initials = profile?.name
            ? profile.name
                .trim()
                .split(/\s+/)
                .slice(0, 2)
                .map((word) => word[0])
                .join("")
                .toUpperCase()
            : node.dataset.knLocalInitials;
          if (node.textContent !== initials) node.textContent = initials;
        }
      }
    });
  }
  const button = (label, action, panel, data = {}) => {
    const node = el("button", label, "kn-account-button");
    node.type = "button";
    node.addEventListener("click", async () => {
      node.disabled = true;
      const message = panel.querySelector("[role=status]");
      message.textContent = "";
      try {
        const value = await request(action, data);
        if (value.pending) pending(panel, value);
        else {
          current = value;
          render();
          identity();
        }
      } catch (error) {
        message.textContent = error.message;
      } finally {
        node.disabled = false;
      }
    });
    return node;
  };
  function pending(panel, value) {
    clearTimeout(polling);
    expiry = Date.now() + 600000;
    const area = panel.querySelector(".kn-account-actions");
    area.replaceChildren();
    area.append(
      el("p", "Confirm this code in your KagNode Account:"),
      el("strong", value.user_code, "kn-account-code"),
    );
    const link = el("a", "Open KagNode Account ↗", "kn-account-button");
    link.href = value.verification_uri;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    area.append(link);
    const tick = async () => {
      if (Date.now() > expiry || !panel.isConnected) {
        panel.querySelector("[role=status]").textContent = "This code expired.";
        panel
          .querySelector(".kn-account-actions")
          .append(button("Start again", "start", panel));
        return;
      }
      try {
        const result = await request("poll");
        if (result.pending)
          polling = setTimeout(tick, Math.max(5, result.interval || 5) * 1000);
        else {
          current = result;
          render();
          identity();
        }
      } catch (error) {
        panel.querySelector("[role=status]").textContent = error.message;
        if (error.status !== 401)
          panel
            .querySelector(".kn-account-actions")
            .append(button("Start again", "start", panel));
      }
    };
    polling = setTimeout(tick, 5000);
  }
  function render() {
    if (!current) return;
    for (const panel of panels) {
      if (!panel.isConnected) {
        panels.delete(panel);
        continue;
      }
      panel.replaceChildren();
      panel.append(
        el("h3", "KagNode Account"),
        el(
          "p",
          "Link your display name and photo. Local sign-in, email addresses and permissions stay under this application’s control.",
        ),
      );
      const status = el("p", "", "kn-account-status");
      status.setAttribute("role", "status");
      const actions = el("div", "", "kn-account-actions");
      if (!current.enabled)
        actions.append(
          el("p", "KagNode Account sync is disabled for this installation."),
        );
      else if (current.connected) {
        actions.append(
          el("p", "Linked as " + (current.profile?.name || "KagNode member")),
          button("Refresh profile", "refresh", panel),
          button("Disconnect profile", "disconnect", panel),
        );
      } else actions.append(button("Link KagNode Account", "start", panel));
      panel.append(actions, status);
      if (current.warning) status.textContent = current.warning;
      if (current.admin) {
        const settings = el("div", "", "kn-account-admin");
        settings.append(
          el("strong", "Installation settings"),
          el(
            "p",
            "This control belongs to your local application administrator. Disabling sync disconnects linked profiles and keeps local accounts available.",
          ),
        );
        const toggle = button(
          current.enabled ? "Turn account sync off" : "Turn account sync on",
          "policy",
          panel,
          { enabled: !current.enabled },
        );
        toggle.disabled = !!current.configured_off;
        settings.append(toggle);
        if (current.configured_off)
          settings.append(el("p", "Disabled in this server’s configuration."));
        if (current.revocations_pending) {
          settings.append(
            el(
              "p",
              current.revocations_pending +
                " remote disconnections need retrying.",
            ),
            button("Retry disconnections", "retry_disconnections", panel),
          );
        }
        panel.append(settings);
      }
    }
  }
  function mount() {
    const shell = document.querySelector("#dashboard,#workspace");
    if (shell?.hidden) {
      current = null;
      clearTimeout(polling);
      document.querySelectorAll(".kn-linked-avatar").forEach((n) => n.remove());
      return;
    }
    const hosts = [...document.querySelectorAll("[data-kn-account-settings]")];
    if (!hosts.length)
      for (const scroll of document.querySelectorAll(
        "[data-kn-scroll-settings]",
      )) {
        const panel = el("section", "", "kn-account-settings");
        panel.dataset.knAccountSettings = "";
        scroll.insertAdjacentElement("afterend", panel);
        hosts.push(panel);
      }
    let added = false;
    for (const host of hosts)
      if (!panels.has(host)) {
        panels.add(host);
        added = true;
      }
    if (added) render();
    identity();
  }
  async function refresh() {
    const shell = document.querySelector("#dashboard,#workspace");
    if (
      shell?.hidden ||
      (app === "media" && !document.querySelector('a[href="/account"]'))
    )
      return;
    if (loading) return;
    loading = true;
    try {
      current = await request();
      last = Date.now();
      mount();
      render();
      identity();
    } catch (error) {
      if (error.status === 401) {
        current = null;
        clearTimeout(polling);
        document
          .querySelectorAll(".kn-linked-avatar")
          .forEach((n) => n.remove());
      }
    } finally {
      last = Date.now();
      loading = false;
    }
  }
  new MutationObserver((records) => {
    if (
      records.some(
        (r) =>
          !r.target.closest?.(".kn-account-settings,.kn-scroll-rail") &&
          (r.type === "childList" || r.attributeName === "hidden"),
      )
    ) {
      mount();
      if (!current && !loading && Date.now() - last > 5000) refresh();
    }
  }).observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["hidden"],
  });
  window.addEventListener("focus", () => {
    if (Date.now() - last > 60000) refresh();
  });
  window.addEventListener("kagnode:account-ready", refresh);
  setInterval(() => {
    const shell = document.querySelector("#dashboard,#workspace");
    if (!document.hidden && !shell?.hidden && Date.now() - last > 60000)
      refresh();
  }, 60000);
  window.KagNodeAccounts = { refresh };
  refresh();
})();
