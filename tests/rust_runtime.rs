use axum::{
    body::Body,
    http::{Request, StatusCode, header},
};
use kagnode_daemon::{
    auth,
    ha::{self, Evidence},
    store::{Profile, Store},
    web::{self, App},
};
use std::sync::Arc;
use tower::ServiceExt;

fn fixture() -> (tempfile::TempDir, Store) {
    let root = tempfile::tempdir().unwrap();
    let store = Store::open(root.path()).unwrap();
    store
        .init(
            "owner@fixture.invalid",
            "fixture-password-long",
            Profile::Light,
            true,
        )
        .unwrap();
    (root, store)
}
#[test]
fn initialization_cannot_replace_existing_accounts_or_settings() {
    let (_root, store) = fixture();
    assert!(
        store
            .init(
                "new@fixture.invalid",
                "another-long-password",
                Profile::Production,
                false
            )
            .is_err()
    );
    assert!(
        store
            .login(
                "owner@fixture.invalid",
                "fixture-password-long",
                "127.0.0.1"
            )
            .is_ok()
    );
    assert!(store.settings().unwrap().web_enabled);
}
#[test]
fn sessions_are_hashed_revocable_and_persistent() {
    let (root, store) = fixture();
    let token = store
        .login("owner@fixture.invalid", "fixture-password-long", "local")
        .unwrap();
    assert_eq!(
        store.session(&token).unwrap().unwrap().email,
        "owner@fixture.invalid"
    );
    drop(store);
    let reopened = Store::open(root.path()).unwrap();
    assert!(reopened.session(&token).unwrap().is_some());
    let db = rusqlite::Connection::open(root.path().join("daemon.sqlite")).unwrap();
    let saved: String = db
        .query_row("SELECT token_hash FROM sessions", [], |r| r.get(0))
        .unwrap();
    assert_ne!(saved, token);
    assert_eq!(saved, auth::digest(&token));
    reopened.logout(&token).unwrap();
    assert!(reopened.session(&token).unwrap().is_none());
}
#[test]
fn preference_conflicts_and_unreviewed_profile_changes_are_rejected() {
    let (_root, store) = fixture();
    let mut first = store.settings().unwrap();
    let stale = first.clone();
    first.web_enabled = false;
    assert_eq!(store.set_settings("owner", first).unwrap().revision, 2);
    assert!(store.set_settings("owner", stale).is_err());
    let mut current = store.settings().unwrap();
    current.profile = Profile::Production;
    assert!(store.set_settings("owner", current).is_err());
    let mut current = store.settings().unwrap();
    current.offloading = true;
    assert!(store.set_settings("owner", current).is_err());
}
#[test]
fn all_incomplete_promotion_evidence_is_rejected() {
    for bits in 0..64 {
        let e = Evidence {
            quorum: bits & 1 != 0,
            old_primary_fenced: bits & 2 != 0,
            storage_current: bits & 4 != 0,
            exclusive_mount: bits & 8 != 0,
            vlan_verified: bits & 16 != 0,
            adapter_qualified: bits & 32 != 0,
        };
        assert_eq!(ha::may_promote(e), bits == 63);
    }
}
#[test]
fn saved_configuration_does_not_activate_cluster_and_requires_current_revision() {
    let (_root, store) = fixture();
    let value = serde_json::json!({"name":"reviewed-plan"});
    assert_eq!(store.save_document("owner", "ha", 0, &value).unwrap(), 1);
    assert!(store.save_document("owner", "ha", 0, &value).is_err());
    assert_eq!(store.document("ha").unwrap().unwrap(), (1, value));
    assert!(
        store
            .audit()
            .unwrap()
            .iter()
            .any(|e| e.action == "configuration")
    );
}
#[test]
fn data_directory_symlinks_are_rejected_without_touching_target() {
    let root = tempfile::tempdir().unwrap();
    let target = root.path().join("target");
    std::fs::create_dir(&target).unwrap();
    let alias = root.path().join("alias");
    std::os::unix::fs::symlink(&target, &alias).unwrap();
    assert!(Store::open(&alias).is_err());
    assert!(!target.join("daemon.sqlite").exists());
}

#[test]
fn encrypted_snapshot_is_restore_checked_and_tampering_is_rejected() {
    let (root, store) = fixture();
    let work = tempfile::tempdir().unwrap();
    let output = work.path().join("backups");
    let key = work.path().join("keys/recovery.key");
    let receipt = kagnode_daemon::backup::create(root.path(), &output, &key).unwrap();
    assert_eq!(receipt["restore_checked"], true);
    assert_eq!(receipt["key_included"], false);
    let path = std::path::Path::new(receipt["file"].as_str().unwrap());
    assert!(kagnode_daemon::backup::validate(path, &key, &output).is_ok());
    let mut bytes = std::fs::read(path).unwrap();
    let last = bytes.len() - 1;
    bytes[last] ^= 1;
    std::fs::write(path, bytes).unwrap();
    assert!(kagnode_daemon::backup::validate(path, &key, &output).is_err());
    assert!(
        store
            .login(
                "owner@fixture.invalid",
                "fixture-password-long",
                "after-backup"
            )
            .is_ok()
    );
    assert!(!std::fs::read_dir(&output).unwrap().any(|entry| {
        entry
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with(".restore-check")
    }));
}

#[test]
fn recovery_key_cannot_be_stored_inside_the_backup_payload_directory() {
    let (root, _store) = fixture();
    let work = tempfile::tempdir().unwrap();
    assert!(
        kagnode_daemon::backup::create(root.path(), work.path(), &work.path().join("key")).is_err()
    );
}

#[test]
fn unrelated_existing_state_directory_is_not_claimed_or_repermissioned() {
    use std::os::unix::fs::PermissionsExt;
    let root = tempfile::tempdir().unwrap();
    std::fs::write(root.path().join("existing-data"), "retained").unwrap();
    std::fs::set_permissions(root.path(), std::fs::Permissions::from_mode(0o755)).unwrap();
    assert!(Store::open(root.path()).is_err());
    assert_eq!(
        root.path().metadata().unwrap().permissions().mode() & 0o777,
        0o755
    );
    assert_eq!(
        std::fs::read_to_string(root.path().join("existing-data")).unwrap(),
        "retained"
    );
}

#[test]
fn installation_profiles_have_concrete_owned_services_and_do_not_enable_ha() {
    let light = kagnode_daemon::install::units(Profile::Light, "http://127.0.0.1:8750");
    let production = kagnode_daemon::install::units(Profile::Production, "http://127.0.0.1:8750");
    assert_eq!(light.len(), 2);
    assert!(production.contains_key("kagnode-daemon-monitor.timer"));
    assert!(production.contains_key("kagnode-daemon-backup.timer"));
    assert!(production["kagnode-daemon.service"].contains("ProtectSystem=strict"));
    assert_eq!(
        kagnode_daemon::install::plan(Profile::Production, false, "http://127.0.0.1:8750").unwrap()
            ["network_or_ha_activation"],
        false
    );
    assert!(
        kagnode_daemon::install::plan(
            Profile::Light,
            true,
            "https://example.invalid/\nExecStart=bad"
        )
        .is_err()
    );
}
#[tokio::test]
async fn dashboard_requires_local_admin_and_protects_mutations() {
    let (_root, store) = fixture();
    let token = store
        .login("owner@fixture.invalid", "fixture-password-long", "test")
        .unwrap();
    let csrf = store.session(&token).unwrap().unwrap().csrf;
    let app = App {
        store: store.clone(),
        origin: "http://127.0.0.1:8750".into(),
        core: Arc::new(kagnode_core::Core::new("/srv/kagnode/core", "daemon").unwrap()),
    };
    let router = web::router(app);
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/v1/applications")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/v1/applications")
                .header(header::COOKIE, format!("kn_daemon={token}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = serde_json::to_string(&store.settings().unwrap()).unwrap();
    for (origin, nonce, expected) in [
        ("https://evil.invalid", csrf.as_str(), StatusCode::FORBIDDEN),
        ("http://127.0.0.1:8750", "wrong", StatusCode::FORBIDDEN),
        ("http://127.0.0.1:8750", csrf.as_str(), StatusCode::OK),
    ] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/settings")
                    .header(header::COOKIE, format!("kn_daemon={token}"))
                    .header(header::ORIGIN, origin)
                    .header("x-csrf-token", nonce)
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(body.clone()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), expected);
    }
    for (nonce, expected) in [
        ("wrong", StatusCode::FORBIDDEN),
        (csrf.as_str(), StatusCode::NO_CONTENT),
    ] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/logout")
                    .header(header::COOKIE, format!("kn_daemon={token}"))
                    .header(header::ORIGIN, "http://127.0.0.1:8750")
                    .header("x-csrf-token", nonce)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), expected);
    }
    assert!(store.session(&token).unwrap().is_none());
}

#[test]
fn vendored_core_fallback_matches_its_signed_public_manifest() {
    use base64::Engine;
    let raw = include_bytes!("../vendor/core-rust/core-manifest.json");
    let signature = include_bytes!("../vendor/core-rust/core-manifest.sig");
    let key = base64::engine::general_purpose::STANDARD
        .decode("uJzR4gg2djgIrWTepTgtJsPnlbvhUYz/mwO7ubtl8l4=")
        .unwrap();
    ring::signature::UnparsedPublicKey::new(&ring::signature::ED25519, key)
        .verify(raw, signature)
        .unwrap();
    let manifest: serde_json::Value = serde_json::from_slice(raw).unwrap();
    let fallback: serde_json::Value =
        serde_json::from_slice(include_bytes!("../vendor/core-rust/fallback/bundle.json")).unwrap();
    let compatibility: serde_json::Value =
        serde_json::from_slice(include_bytes!("../assets/core-bundle.json")).unwrap();
    assert_eq!(fallback, compatibility);
    assert_eq!(fallback["source_commit"], manifest["source_commit"]);
    assert_eq!(fallback["version"], manifest["version"]);
    assert_eq!(
        fallback["files"].as_object().unwrap().len(),
        manifest["files"].as_object().unwrap().len()
    );
    for (name, item) in manifest["files"].as_object().unwrap() {
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(fallback["files"][name]["data"].as_str().unwrap())
            .unwrap();
        assert_eq!(
            hex::encode(<sha2::Sha256 as sha2::Digest>::digest(&bytes)),
            item["sha256"]
        );
        assert_eq!(bytes.len() as u64, item["size"].as_u64().unwrap());
    }
}
