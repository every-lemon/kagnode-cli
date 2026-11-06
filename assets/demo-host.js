(() => {
  "use strict";
  const search = document.querySelector("[data-demo-search]"),
    category = document.querySelector("[data-demo-category]");
  if (search && category) {
    const filter = () => {
      let count = 0;
      document.querySelectorAll("[data-demo-card]").forEach((card) => {
        card.hidden =
          (!!category.value && card.dataset.category !== category.value) ||
          !card.textContent
            .toLowerCase()
            .includes(search.value.toLowerCase().trim());
        if (!card.hidden) count++;
      });
      document.querySelector("[data-demo-count]").textContent =
        count + " examples";
      document.querySelector("[data-demo-empty]").hidden = !!count;
    };
    search.oninput = filter;
    category.onchange = filter;
  }
  for (const host of document.querySelectorAll("[data-demo-host]")) {
    let frame = host.querySelector("iframe");
    const status = host.querySelector("[data-demo-status]"),
      connected = host.dataset.connected === "true";
    let products = [];
    try {
      products = JSON.parse(host.dataset.products || "[]");
    } catch {}
    let product = host.dataset.product,
      channel = "",
      revision = 0,
      loadingTimer,
      revealTimer,
      initialized = false,
      projectsInitialized = false;
    const states = new Map(),
      summaries = Object.fromEntries(
        products.map((p) => [p.id, p.counts || {}]),
      );
    let projects = [
        { id: "studio", name: "Northstar Studio" },
        { id: "lab", name: "Research Lab" },
      ],
      project = "studio",
      activity = [];
    const send = (type, data = {}) =>
      frame.contentWindow?.postMessage(
        { protocol: "kagnode-demo-v1", channel, type, ...data },
        "*",
      );
    const theme = () =>
      document.documentElement.dataset.theme === "light" ? "light" : "dark";
    const token = () =>
      Array.from(crypto.getRandomValues(new Uint32Array(4)), (n) =>
        n.toString(16),
      ).join("");
    const validJson = (v) => {
      try {
        const text = JSON.stringify(v);
        return (
          text.length <= 180000 &&
          !/("__proto__"|"constructor"|"prototype")\s*:/.test(text)
        );
      } catch {
        return false;
      }
    };
    const renderProjects = () => {
      const select = host.querySelector("[data-demo-project]");
      if (!select) return;
      select.replaceChildren(
        ...projects.map((p) => {
          const option = document.createElement("option");
          option.value = p.id;
          option.textContent = p.name;
          return option;
        }),
      );
      select.value = project;
    };
    const init = () =>
      send("init", {
        state: states.get(product + "@" + revision),
        theme: theme(),
        connected,
        project,
        shared: { projects, summaries, activity },
      });
    const busy = () => {
      clearTimeout(revealTimer);
      initialized = false;
      channel = token();
      frame.style.height = "700px";
      frame.closest(".demo-stage")?.setAttribute("aria-busy", "true");
      if (status) status.textContent = "Loading example…";
      clearTimeout(loadingTimer);
      loadingTimer = setTimeout(() => {
        if (frame.closest(".demo-stage")?.hasAttribute("aria-busy")) {
          frame.closest(".demo-stage")?.removeAttribute("aria-busy");
          if (status)
            status.textContent =
              "Example unavailable. Reload or choose another product.";
        }
      }, 10000);
    };
    const loadFrame = (url) => {
      const previous = frame,
        next = document.createElement("iframe");
      for (const attribute of previous.attributes)
        if (!["src", "srcdoc", "style"].includes(attribute.name))
          next.setAttribute(attribute.name, attribute.value);
      next.style.height = "700px";
      next.addEventListener("load", () => send("hello"));
      next.src = url;
      frame = next;
      previous.replaceWith(next);
    };
    const navigate = (next, history = true) => {
      if (!connected || !products.some((p) => p.id === next)) return;
      product = next;
      host.dataset.product = next;
      busy();
      loadFrame("/demos/" + encodeURIComponent(next) + "/frame");
      host
        .querySelector(".demo-workspace-toolbar")
        ?.scrollIntoView({ block: "start", behavior: "instant" });
      frame.title =
        (products.find((p) => p.id === next)?.title || next) +
        " fictional demo";
      host.querySelectorAll("[data-demo-product]").forEach((b) => {
        if (b.dataset.demoProduct === next)
          b.setAttribute("aria-current", "page");
        else b.removeAttribute("aria-current");
      });
      const link = host.querySelector("[data-demo-standalone]");
      if (link) link.href = "/demos/" + encodeURIComponent(next);
      if (history)
        window.history.pushState(
          null,
          "",
          "/demos/workspace?product=" + encodeURIComponent(next),
        );
    };
    host
      .querySelectorAll("[data-demo-product]")
      .forEach((button) =>
        button.addEventListener("click", () =>
          navigate(button.dataset.demoProduct),
        ),
      );
    const validProjects = (p) =>
      Array.isArray(p) &&
      p.length > 0 &&
      p.length <= 100 &&
      p.every(
        (x) =>
          x &&
          typeof x.id === "string" &&
          /^[a-z0-9-]{1,80}$/i.test(x.id) &&
          typeof x.name === "string" &&
          x.name.length > 0 &&
          x.name.length <= 100,
      ) &&
      new Set(p.map((x) => x.id)).size === p.length;
    addEventListener("message", (event) => {
      if (
        event.source !== frame.contentWindow ||
        event.origin !== "null" ||
        event.data?.protocol !== "kagnode-demo-v1"
      )
        return;
      const m = event.data;
      if (m.type === "ready") {
        if (m.product !== product || !Number.isSafeInteger(m.revision)) return;
        if (initialized && revision === m.revision) return;
        if (!channel) channel = token();
        revision = m.revision;
        initialized = true;
        if (!projectsInitialized && validProjects(m.projects)) {
          projects = m.projects;
          project = projects[0].id;
          projectsInitialized = true;
          renderProjects();
        }
        init();
        return;
      }
      if (!initialized || m.channel !== channel) return;
      if (m.type === "state" && validJson(m.state)) {
        states.set(product + "@" + revision, m.state);
        if (typeof m.message === "string" && m.message) {
          activity.unshift({
            text: m.message.slice(0, 160),
            at: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            product,
          });
          activity = activity.slice(0, 60);
          if (status) status.textContent = m.message.slice(0, 100);
        }
      } else if (
        m.type === "summary" &&
        m.counts &&
        typeof m.counts === "object" &&
        !Array.isArray(m.counts) &&
        validJson(m.counts)
      ) {
        summaries[product] = Object.fromEntries(
          Object.entries(m.counts).filter(
            ([key, value]) =>
              projects.some((p) => p.id === key) &&
              Number.isSafeInteger(value) &&
              value >= 0 &&
              value <= 500,
          ),
        );
      } else if (m.type === "projects" && validProjects(m.projects)) {
        projects = m.projects.map((p) => ({ id: p.id, name: p.name }));
        if (!projects.some((p) => p.id === project)) project = projects[0].id;
        renderProjects();
      } else if (
        m.type === "project" &&
        projects.some((p) => p.id === m.project)
      ) {
        project = m.project;
        renderProjects();
        init();
      } else if (m.type === "navigate" && typeof m.product === "string")
        navigate(m.product);
      else if (m.type === "resize" && Number.isFinite(m.height)) {
        frame.style.height =
          Math.min(5000, Math.max(420, Math.ceil(m.height))) + "px";
        if (frame.closest(".demo-stage")?.hasAttribute("aria-busy")) {
          clearTimeout(revealTimer);
          revealTimer = setTimeout(() => {
            frame.closest(".demo-stage")?.removeAttribute("aria-busy");
            clearTimeout(loadingTimer);
            if (status)
              status.textContent = "Example ready · revision " + revision;
          }, 80);
        }
      }
    });
    frame.addEventListener("load", () => {
      if (!channel) channel = token();
      send("hello");
    });
    host
      .querySelector("[data-demo-project]")
      ?.addEventListener("change", (event) => {
        project = event.target.value;
        init();
      });
    const resetDialog = host.querySelector("[data-demo-reset-dialog]");
    host.querySelector("[data-reset-demo]")?.addEventListener("click", () => {
      if (resetDialog) resetDialog.showModal();
      else {
        states.clear();
        busy();
        loadFrame(frame.getAttribute("src"));
      }
    });
    host
      .querySelector("[data-reset-cancel]")
      ?.addEventListener("click", () => resetDialog.close());
    host
      .querySelector("[data-reset-confirm]")
      ?.addEventListener("click", () => {
        states.clear();
        activity = [];
        projectsInitialized = false;
        projects = [
          { id: "studio", name: "Northstar Studio" },
          { id: "lab", name: "Research Lab" },
        ];
        project = "studio";
        for (const p of products) summaries[p.id] = p.counts || {};
        renderProjects();
        resetDialog.close();
        busy();
        loadFrame(frame.getAttribute("src"));
      });
    host
      .querySelector("[data-demo-focus]")
      ?.addEventListener("click", (event) => {
        const expanded = host.classList.toggle("is-expanded");
        document.body.classList.toggle("demo-expanded", expanded);
        event.target.textContent = expanded ? "Exit expanded view" : "Expand";
      });
    addEventListener("keydown", (event) => {
      if (event.key === "Escape" && host.classList.contains("is-expanded"))
        host.querySelector("[data-demo-focus]").click();
    });
    addEventListener("popstate", () => {
      if (connected)
        navigate(
          new URL(location.href).searchParams.get("product") || "console",
          false,
        );
    });
    new MutationObserver(() => send("theme", { theme: theme() })).observe(
      document.documentElement,
      { attributes: true, attributeFilter: ["data-theme"] },
    );
    host.addEventListener("demo-preview", (event) => {
      if (
        typeof event.detail !== "string" ||
        !event.detail.startsWith("/operator/documents/" + product + "/preview/")
      )
        return;
      states.clear();
      busy();
      loadFrame(event.detail);
    });
    renderProjects();
    busy();
    send("hello");
  }
})();
