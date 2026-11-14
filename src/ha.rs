//! A reviewable cluster declaration is not evidence that promotion is safe.
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::net::IpAddr;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub name: String,
    pub address: IpAddr,
    pub failure_domain: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cluster {
    pub name: String,
    pub primary: Node,
    pub standby: Node,
    pub witness: Node,
    pub vlan: u16,
    pub parent_interface: String,
    pub service_ip: IpAddr,
    pub products: Vec<String>,
    pub fencing_credential: String,
}
fn identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 48
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
}
impl Cluster {
    pub fn validate(&self) -> Result<()> {
        ensure!(identifier(&self.name), "Use a short cluster identifier");
        ensure!(
            (1..=4094).contains(&self.vlan),
            "VLAN must be between 1 and 4094"
        );
        ensure!(
            identifier(&self.parent_interface) && self.parent_interface.len() <= 15,
            "Invalid parent interface"
        );
        ensure!(
            identifier(&self.fencing_credential),
            "Use a local credential reference, not a secret"
        );
        let nodes = [&self.primary, &self.standby, &self.witness];
        for node in nodes {
            ensure!(
                identifier(&node.name) && identifier(&node.failure_domain),
                "Invalid node name or failure domain"
            );
            ensure!(
                !node.address.is_unspecified()
                    && !node.address.is_loopback()
                    && !node.address.is_multicast(),
                "Use a reachable node address"
            );
        }
        for (i, a) in nodes.iter().enumerate() {
            for b in &nodes[i + 1..] {
                ensure!(
                    a.name != b.name
                        && a.address != b.address
                        && a.failure_domain != b.failure_domain,
                    "HA nodes require distinct identities, addresses and failure domains"
                );
            }
        }
        ensure!(
            !self.service_ip.is_unspecified()
                && !self.service_ip.is_loopback()
                && !self.service_ip.is_multicast()
                && nodes.iter().all(|n| n.address != self.service_ip),
            "Service IP must be distinct and unicast"
        );
        ensure!(
            !self.products.is_empty() && self.products.len() <= 7,
            "Choose between one and seven HA applications"
        );
        let mut products = std::collections::HashSet::new();
        for id in &self.products {
            ensure!(
                crate::catalog::product(id).is_some_and(|p| p.id != "netctl")
                    && products.insert(id),
                "Unknown or duplicate HA application"
            );
        }
        Ok(())
    }
    pub fn plan(&self) -> Result<Value> {
        self.validate()?;
        Ok(
            json!({"schema":1,"cluster":self,"topology":"active-passive","replication":"synchronous","control_plane":"pacemaker-corosync","storage":"drbd9","quorum":"majority-with-independent-witness","writes_without_safe_quorum":"suspend","automatic_failback":false,"network":{"type":"vlan","id":self.vlan,"trunk_changes":"review-required"},"activation_ready":false,"blockers":["Enroll and authenticate the three nodes","Verify VLAN connectivity and unique service IP through Netctl","Qualify fencing against the actual failure domains","Verify synchronous replicated volumes and exclusive writable mounts","Qualify application-specific restart and recovery adapters"],"application_states":self.products.iter().filter_map(|id|crate::catalog::product(id)).map(|p|json!({"id":p.id,"replicate":p.ha_state})).collect::<Vec<_>>(),"changes_applied":false}),
        )
    }
}

#[derive(Clone, Copy, Default, Serialize, Deserialize)]
pub struct Evidence {
    pub quorum: bool,
    pub old_primary_fenced: bool,
    pub storage_current: bool,
    pub exclusive_mount: bool,
    pub vlan_verified: bool,
    pub adapter_qualified: bool,
}
/// This gate consumes fresh agent observations, never a browser-supplied flag.
pub fn may_promote(e: Evidence) -> bool {
    e.quorum
        && e.old_primary_fenced
        && e.storage_current
        && e.exclusive_mount
        && e.vlan_verified
        && e.adapter_qualified
}
