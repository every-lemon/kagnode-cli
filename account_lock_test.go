package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestAccountControlRejectsContentionAndUnsafeFiles(t *testing.T) {
	testHome(t)
	unlock, err := credentialLock()
	if err != nil {
		t.Fatal(err)
	}
	if other, e := credentialLock(); e == nil {
		other()
		t.Fatal("account contention ignored")
	}
	unlock()
	path := filepath.Join(pathFor("config"), ".account.lock")
	before, _ := os.Stat(path)
	if _, err = os.Stat(path); err != nil {
		t.Fatal("stable control was removed")
	}
	os.Remove(path)
	if err = syscall.Mkfifo(path, 0600); err != nil {
		t.Fatal(err)
	}
	if close, e := credentialLock(); e == nil {
		close()
		t.Fatal("FIFO account control accepted")
	}
	os.Remove(path)
	kept := path + ".kept"
	if err = os.WriteFile(kept, []byte("retained"), 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.Link(kept, path); err != nil {
		t.Fatal(err)
	}
	if close, e := credentialLock(); e == nil {
		close()
		t.Fatal("hardlinked account control accepted")
	}
	raw, _ := os.ReadFile(kept)
	if string(raw) != "retained" {
		t.Fatal("control validation altered existing bytes")
	}
	if before.Mode().Perm() != 0600 {
		t.Fatal("account control was not private")
	}
}
func TestProfileRefreshCannotOverwriteAnAccountSwitch(t *testing.T) {
	testHome(t)
	started := make(chan struct{})
	release := make(chan struct{})
	done := make(chan error, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/cli/me":
			close(started)
			<-release
			json.NewEncoder(w).Encode(map[string]any{"id": "old", "name": "Old profile"})
		case "/api/cli/revoke":
			w.WriteHeader(204)
		case "/api/v1/account-sync/profile":
			if r.Header.Get("Authorization") != "Bearer new-access" {
				t.Error("stale account token used")
			}
			json.NewEncoder(w).Encode(map[string]any{"subject": "new", "name": "New profile"})
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	old := credentials{Base: server.URL, Access: "old-access", Refresh: "old-refresh", ID: "old", Expires: time.Now().Unix() + 600}
	if err := saveCredentials(old); err != nil {
		t.Fatal(err)
	}
	go func() { _, err := online(&old); done <- err }()
	<-started
	next := credentials{Protocol: "account-sync", Base: server.URL, Access: "new-access", Refresh: "new-refresh", ID: "new", Expires: time.Now().Unix() + 600}
	err := saveSignIn(next)
	if err == nil || !strings.Contains(err.Error(), "in progress") {
		close(release)
		t.Fatal("in-flight old profile did not protect identity switch", err)
	}
	close(release)
	if err = <-done; err != nil {
		t.Fatal(err)
	}
	if err = saveSignIn(next); err != nil {
		t.Fatal(err)
	}
	// A caller that read the previous account before acquiring the control must
	// reread the committed current identity, not put its stale tokens back.
	stale := old
	if _, err = online(&stale); err != nil {
		t.Fatal(err)
	}
	current, err := readCredentials()
	if err != nil || current.ID != "new" || stale.ID != "new" || current.Name != "New profile" {
		t.Fatal("stale profile replaced the authorized account", err)
	}
}
