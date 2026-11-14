use serde::Serialize;
use std::path::Path;

#[derive(Clone, Copy, Serialize)]
pub struct Product {
    pub id: &'static str,
    pub name: &'static str,
    pub repository: &'static str,
    pub icon: &'static str,
    pub units: &'static [&'static str],
    pub ha_state: &'static str,
}
pub const PRODUCTS: &[Product] = &[
    Product {
        id: "proxy-manager",
        name: "PM",
        repository: "kagnode-pm",
        icon: "network",
        units: &[
            "kagnode-proxy-controller.service",
            "kagnode-proxy-agent.service",
            "kagnode-proxy-traffic.service",
        ],
        ha_state: "controller, configuration and certificates",
    },
    Product {
        id: "vpn",
        name: "VPN",
        repository: "kagnode-vpn",
        icon: "shield",
        units: &["kagnode-vpn.service"],
        ha_state: "configuration and authorized identity material; clients reconnect",
    },
    Product {
        id: "entropy",
        name: "Entropy",
        repository: "kagnode-entropy",
        icon: "activity",
        units: &["kagnode-entropy.service"],
        ha_state: "configuration only; reseed from OS, never replicate random pools",
    },
    Product {
        id: "media",
        name: "Media",
        repository: "kagnode-media",
        icon: "image",
        units: &["kagnode-media.service", "kagnode-media-worker.service"],
        ha_state: "catalog, originals and durable processing jobs",
    },
    Product {
        id: "passwords",
        name: "Passwords",
        repository: "kagnode-passwords",
        icon: "key",
        units: &["kagnode-passwords.service"],
        ha_state: "encrypted vault and service state; preserve unlock methods",
    },
    Product {
        id: "mail",
        name: "Mail",
        repository: "kagnode-mail",
        icon: "mail",
        units: &["kagnode-mail.service"],
        ha_state: "mailboxes and durable queues; ambiguous SMTP delivery requires reconciliation",
    },
    Product {
        id: "httpboot",
        name: "HTTP Boot",
        repository: "kagnode-httpboot",
        icon: "server",
        units: &["httpboot-server-v2.service"],
        ha_state: "published artifacts and committed saves; pending client RAM stays on client",
    },
    Product {
        id: "netctl",
        name: "Netctl",
        repository: "kagnode-netctl",
        icon: "network",
        units: &["kagnode-netctl.service"],
        ha_state: "network plans, IPAM and durable service configuration",
    },
];
pub fn product(id: &str) -> Option<&'static Product> {
    PRODUCTS
        .iter()
        .find(|p| p.id == id || (id == "pm" && p.id == "proxy-manager"))
}
pub fn installed(root: &Path, product: &Product) -> bool {
    let path = root.join(product.id);
    if path.is_symlink() {
        return false;
    }
    ["installation.json", "state.json", "current"]
        .iter()
        .any(|name| path.join(name).exists())
}
