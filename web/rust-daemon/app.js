/* KagNode. Daemon — host workflows; Core owns presentation and interaction. */
(() => {
  let csrf = "";
  const content = document.querySelector("#content"),
    status = document.querySelector("#page-status");
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  async function api(path, body) {
    const r = await fetch("/api/v1/" + path, {
      method: body === undefined ? "GET" : "POST",
      headers:
        body === undefined
          ? {}
          : { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (r.status === 401) {
      location.assign("/login");
      throw Error("Sign in again");
    }
    const v = r.status === 204 ? {} : await r.json();
    if (!r.ok) throw Error(v.error || "The request failed");
    return v;
  }
  function link(label, url, icon) {
    const a = el("a", undefined, "card");
    a.href = url;
    const i = el("span");
    i.dataset.coreIcon = icon;
    const name = el("strong", label);
    a.append(i, name);
    return a;
  }
  function field(form, label, name, value = "", type = "text") {
    const row = el("label", label),
      input = el("input");
    input.name = name;
    input.type = type;
    input.value = value;
    input.required = true;
    row.append(input);
    form.append(row);
    return input;
  }
  async function render() {
    if (!content) return;
    try {
      const session = await api("session");
      csrf = session.user.csrf;
      document
        .querySelector("#sign-out")
        ?.addEventListener("click", async () => {
          await api("logout", {});
          location.assign("/login");
        });
      content.replaceChildren();
      const path = location.pathname;
      if (path === "/settings") {
        document.querySelector("h1").textContent = "Settings";
        const s = await api("settings"),
          f = el("form", undefined, "panel stack");
        f.append(el("h2", "Installation"), el("p", "Profile: " + s.profile));
        const row = el("label", undefined, "setting-row"),
          check = el("input");
        check.type = "checkbox";
        check.dataset.coreSwitch = "";
        check.checked = s.web_enabled;
        row.append(check, el("span", "Enable the Daemon web dashboard"));
        f.append(
          row,
          el(
            "p",
            "Disabling the dashboard leaves managed applications running. Re-enable it through kagnode settings web on and restart the Daemon.",
            "muted",
          ),
        );
        const save = el("button", "Save preferences", "button primary");
        f.append(save);
        f.onsubmit = async (e) => {
          e.preventDefault();
          save.disabled = true;
          try {
            const next = await api("settings", {
              ...s,
              web_enabled: check.checked,
            });
            Object.assign(s, next);
            status.textContent = check.checked
              ? "Preferences saved."
              : "Dashboard disabled. Your terminal management remains available.";
          } catch (e) {
            status.textContent = e.message;
          } finally {
            save.disabled = false;
          }
        };
        content.append(f);
        const appearance = el("section", undefined, "panel");
        appearance.dataset.corePreferencesHost = "";
        content.append(appearance);
      } else if (path === "/audit") {
        document.querySelector("h1").textContent = "Activity";
        const data = await api("audit");
        if (!data.events.length)
          content.append(el("p", "No administration activity yet."));
        for (const event of data.events) {
          const row = el("article", undefined, "panel");
          row.append(
            el("strong", event.action),
            el("p", event.detail),
            el(
              "small",
              event.actor + " · " + new Date(event.at * 1000).toLocaleString(),
            ),
          );
          content.append(row);
        }
      } else if (path === "/ha") {
        document.querySelector("h1").textContent = "High availability";
        const data = await api("ha/configuration");
        const f = el("form", undefined, "panel stack");
        f.append(
          el(
            "p",
            "Review an active/passive cluster. Saving a declaration does not activate networking, storage or failover.",
          ),
        );
        const c = data.configuration || {};
        field(f, "Cluster name", "name", c.name || "");
        for (const role of ["primary", "standby", "witness"]) {
          const group = el("fieldset", undefined, "stack");
          group.append(el("legend", role[0].toUpperCase() + role.slice(1)));
          for (const [key, label] of [
            ["name", "Node name"],
            ["address", "Node IP address"],
            ["failure_domain", "Independent failure domain"],
          ])
            field(group, label, role + "_" + key, c[role]?.[key] || "");
          f.append(group);
        }
        field(f, "HA VLAN ID", "vlan", c.vlan || "", "number").min = "1";
        f.elements.vlan.max = "4094";
        field(
          f,
          "Parent interface",
          "parent_interface",
          c.parent_interface || "",
        );
        field(f, "Virtual service IP", "service_ip", c.service_ip || "");
        field(
          f,
          "Local fencing credential reference",
          "fencing_credential",
          c.fencing_credential || "",
        );
        const products = el("fieldset");
        products.append(el("legend", "Applications"));
        for (const p of (await api("applications")).applications.filter(
          (p) => p.product.id !== "netctl",
        )) {
          const label = el("label", undefined, "setting-row"),
            box = el("input");
          box.type = "checkbox";
          box.name = "products";
          box.value = p.product.id;
          box.checked = c.products?.includes(box.value) || false;
          label.append(box, el("span", p.product.name));
          products.append(label);
        }
        f.append(products);
        const output = el("section", undefined, "panel"),
          review = el("button", "Review cluster plan", "button primary"),
          save = el("button", "Save declaration", "button");
        save.type = "button";
        save.disabled = true;
        f.append(review, save);
        let reviewed;
        f.onsubmit = async (e) => {
          e.preventDefault();
          save.disabled = true;
          try {
            const v = Object.fromEntries(new FormData(f));
            const input = {
              name: v.name,
              vlan: Number(v.vlan),
              parent_interface: v.parent_interface,
              service_ip: v.service_ip,
              fencing_credential: v.fencing_credential,
              products: new FormData(f).getAll("products"),
            };
            for (const role of ["primary", "standby", "witness"])
              input[role] = {
                name: v[role + "_name"],
                address: v[role + "_address"],
                failure_domain: v[role + "_failure_domain"],
              };
            const result = await api("ha/plan", input);
            reviewed = input;
            output.replaceChildren(el("h2", "Readiness checks"));
            for (const message of result.blockers)
              output.append(el("p", message));
            save.disabled = false;
            status.textContent =
              "Plan reviewed. Automatic HA remains blocked until the displayed checks pass.";
          } catch (e) {
            status.textContent = e.message;
          }
        };
        f.addEventListener("input", () => {
          save.disabled = true;
          reviewed = null;
        });
        save.onclick = async () => {
          if (!reviewed) return;
          try {
            const result = await api("ha/configuration", {
              revision: data.revision,
              configuration: reviewed,
            });
            data.revision = result.revision;
            status.textContent =
              "Declaration saved. No infrastructure was changed.";
            save.disabled = true;
          } catch (e) {
            status.textContent = e.message;
          }
        };
        content.append(f, output);
      } else {
        const apps = (await api("applications")).applications;
        const id = path.split("/").at(-1),
          app = apps.find((a) => a.product.id === id);
        if (app) {
          document.querySelector("h1").textContent =
            "KagNode. " + app.product.name;
          content.append(link("Back to applications", "/", "arrow-left"));
          const panel = el("section", undefined, "panel");
          panel.append(
            el("h2", "Installation"),
            el(
              "p",
              app.installed
                ? "Existing installation detected. Its project-owned runtime and data are retained."
                : "Not installed on this node.",
            ),
            el("h3", "High availability"),
            el("p", app.product.ha_state),
            link("Review HA configuration", "/ha", "shield"),
          );
          content.append(panel);
          const services = await api(
            "applications/" + app.product.id + "/services",
          );
          const management = el("section", undefined, "panel stack");
          management.append(el("h2", "Native services"));
          if (services.native_actions_enabled) {
            for (const [unit, state] of Object.entries(services.states))
              management.append(el("p", unit + " · " + state));
            const controls = el("div", undefined, "actions");
            for (const operation of ["start", "stop", "restart"]) {
              const button = el(
                "button",
                operation[0].toUpperCase() + operation.slice(1),
                "button",
              );
              button.onclick = async () => {
                button.disabled = true;
                try {
                  const plan = await api(
                    "applications/" + app.product.id + "/service-plan",
                    { operation },
                  );
                  const dialog = el("dialog"),
                    box = el("div", undefined, "stack");
                  box.append(
                    el("h2", "Review " + operation),
                    el("p", plan.effect),
                  );
                  for (const unit of Object.keys(plan.units))
                    box.append(el("p", unit));
                  const confirm = el(
                      "button",
                      "Confirm " + operation,
                      "button primary",
                    ),
                    cancel = el("button", "Cancel", "button");
                  const request_id = crypto.randomUUID().replaceAll("-", "");
                  cancel.onclick = () => dialog.close();
                  confirm.onclick = async () => {
                    confirm.disabled = true;
                    try {
                      const job = await api(
                        "applications/" + app.product.id + "/service-apply",
                        { operation, expected_sha256: plan.sha256, request_id },
                      );
                      status.textContent =
                        job.state === "completed"
                          ? "Native operation completed."
                          : "The operation needs inspection before further changes.";
                      dialog.close();
                    } catch (error) {
                      box.append(el("p", error.message));
                    } finally {
                      confirm.disabled = false;
                    }
                  };
                  box.append(confirm, cancel);
                  dialog.append(box);
                  document.body.append(dialog);
                  dialog.addEventListener("close", () => dialog.remove(), {
                    once: true,
                  });
                  dialog.showModal();
                } catch (error) {
                  status.textContent = error.message;
                } finally {
                  button.disabled = false;
                }
              };
              controls.append(button);
            }
            management.append(controls);
            const refresh = el("button", "Refresh operation history", "button"),
              history = el("div");
            refresh.onclick = async () => {
              try {
                const data = await api(
                  "applications/" + app.product.id + "/operations",
                );
                history.replaceChildren();
                for (const job of data.operations)
                  history.append(el("p", job.id + " · " + job.state));
              } catch (error) {
                status.textContent = error.message;
              }
            };
            management.append(refresh, history);
          } else {
            management.append(
              el(
                "p",
                services.message || "Native service control is unavailable.",
              ),
            );
            management.append(
              el(
                "p",
                "A root administrator must explicitly enroll each existing unit before Daemon can change it. Configuration and data remain with the application.",
                "muted",
              ),
            );
          }
          content.append(management);
        } else {
          const grid = el("div", undefined, "cards");
          for (const app of apps) {
            const card = link(app.product.name, app.url, app.product.icon);
            card.append(
              el(
                "small",
                app.installed ? "Installation detected" : "Not installed",
              ),
            );
            grid.append(card);
          }
          content.append(grid);
        }
      }
      if (
        !status.textContent.includes("saved") &&
        !status.textContent.includes("reviewed")
      )
        status.textContent = "";
      window.KagNodeControls?.enhance();
      window.KagNodeCore?.refresh();
    } catch (e) {
      if (status) status.textContent = e.message;
    }
  }
  render();
})();
