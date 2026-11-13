package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestProfilePreferenceDoesNotRemoveLocalAuthentication(t *testing.T) {
	t.Setenv("XDG_CONFIG_HOME", t.TempDir())
	t.Setenv("KAGNODE_ACCOUNT_SYNC", "on")
	c := credentials{Base: "https://nebulacoder.com", ID: "local-profile-fixture", Name: "KagNode Name", Access: "fixture-access", Refresh: "fixture-refresh", Offline: true}
	if err := saveCredentials(c); err != nil {
		t.Fatal(err)
	}
	if !profileSyncEnabled() {
		t.Fatal("new local installations should offer explicit linking")
	}
	if err := setProfileSync(false); err != nil {
		t.Fatal(err)
	}
	if profileSyncEnabled() {
		t.Fatal("disable did not persist")
	}
	got, err := readCredentials()
	if err != nil || got.ID != c.ID || got.Refresh != c.Refresh {
		t.Fatal("profile preference changed authentication")
	}
	state := cliProfileState(got, "")
	if state["profile"] != nil || state["enabled"] != false {
		t.Fatal("disabled preference exposed profile")
	}
	info, err := os.Stat(filepath.Join(pathFor("config"), "profile-sync.json"))
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("preference permissions")
	}
	t.Setenv("KAGNODE_ACCOUNT_SYNC", "off")
	if err := setProfileSync(true); err == nil {
		t.Fatal("environment disable could be overridden")
	}
}

func TestTUIHonorsProfilePresentationOptOut(t *testing.T) {
	testHome(t)
	if err := saveCredentials(credentials{Base: "https://nebulacoder.com", ID: "subject", Name: "Synced profile name"}); err != nil {
		t.Fatal(err)
	}
	if err := setProfileSync(false); err != nil {
		t.Fatal(err)
	}
	var model tuiModel
	model.identity()
	if model.account != "KagNode Account" {
		t.Fatal("disabled profile shown in TUI")
	}
	if err := setProfileSync(true); err != nil {
		t.Fatal(err)
	}
	model.identity()
	if model.account != "Synced profile name" {
		t.Fatal("local sign-in/profile cache was lost")
	}
}
