package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

var accountProfileMutex sync.Mutex
var profilePhotoPattern = regexp.MustCompile(`^data:image/webp;base64,[A-Za-z0-9+/=]+$`)

type profilePreferences struct {
	Enabled bool `json:"enabled"`
}

func profileSyncEnabled() bool {
	if v := strings.ToLower(os.Getenv("KAGNODE_ACCOUNT_SYNC")); v == "off" || v == "false" || v == "0" {
		return false
	}
	p := filepath.Join(pathFor("config"), "profile-sync.json")
	info, err := os.Lstat(p)
	if os.IsNotExist(err) {
		return true
	}
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return false
	}
	raw, err := os.ReadFile(p)
	var prefs profilePreferences
	return err == nil && json.Unmarshal(raw, &prefs) == nil && prefs.Enabled
}
func setProfileSync(enabled bool) error {
	if enabled {
		v := strings.ToLower(os.Getenv("KAGNODE_ACCOUNT_SYNC"))
		if v == "off" || v == "false" || v == "0" {
			return errors.New("profile sync is disabled by this installation's configuration")
		}
	}
	return writePrivate(filepath.Join(pathFor("config"), "profile-sync.json"), profilePreferences{enabled})
}
func cacheProfile(c *credentials, profile map[string]any) error {
	if !profileSyncEnabled() {
		return nil
	}
	name, photo := str(profile, "name"), str(profile, "photo")
	if name != "" && len(name) <= 400 {
		c.Name = name
	}
	if len(photo) <= 180000 && (photo == "" || profilePhotoPattern.MatchString(photo)) {
		c.Photo = photo
	}
	c.ProfileUpdated = time.Now().Unix()
	return saveCredentials(*c)
}
func profileCommand(args []string) error {
	if len(args) != 2 || args[0] != "sync" {
		return errors.New("usage: kagnode account sync on|off|status")
	}
	switch args[1] {
	case "on":
		if err := setProfileSync(true); err != nil {
			return err
		}
	case "off":
		if err := setProfileSync(false); err != nil {
			return err
		}
	case "status":
	default:
		return errors.New("usage: kagnode account sync on|off|status")
	}
	fmt.Printf("KagNode Account profile sync: %t\n", profileSyncEnabled())
	return nil
}
func cliProfileState(c credentials, warning string) map[string]any {
	var profile any
	if profileSyncEnabled() {
		profile = map[string]any{"subject": c.ID, "name": c.Name, "photo": c.Photo}
	}
	configured := strings.ToLower(os.Getenv("KAGNODE_ACCOUNT_SYNC"))
	return map[string]any{"enabled": profileSyncEnabled(), "connected": profileSyncEnabled(), "admin": true, "profile": profile, "local_name": "CLI account", "configured_off": configured == "off" || configured == "false" || configured == "0", "warning": warning}
}
func serveAccountProfile(w http.ResponseWriter, r *http.Request, origin string) {
	accountProfileMutex.Lock()
	defer accountProfileMutex.Unlock()
	w.Header().Set("Content-Type", "application/json")
	fail := func(message string, status int) {
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
	}
	c, err := readCredentials()
	if err != nil {
		fail("Sign in through kagnode login first.", 401)
		return
	}
	action := "state"
	if r.Method == "POST" {
		if r.Header.Get("X-KagNode-Action") != "profile" || r.Header.Get("Origin") == "null" || r.Header.Get("Origin") != "" && r.Header.Get("Origin") != origin || r.Header.Get("Sec-Fetch-Site") == "cross-site" {
			fail("Same-origin profile controls are required.", 403)
			return
		}
		if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
			fail("Use a JSON request.", 400)
			return
		}
		var data struct {
			Action  string `json:"action"`
			Enabled *bool  `json:"enabled"`
		}
		decoder := json.NewDecoder(io.LimitReader(r.Body, 4097))
		if decoder.Decode(&data) != nil {
			fail("Invalid profile request.", 400)
			return
		}
		action = data.Action
		switch action {
		case "policy":
			if data.Enabled == nil {
				fail("Choose whether sync is enabled.", 400)
				return
			}
			err = setProfileSync(*data.Enabled)
		case "disconnect":
			err = setProfileSync(false)
		case "start", "refresh":
			if !profileSyncEnabled() {
				fail("Profile sync is disabled.", 403)
				return
			}
		default:
			fail("Unknown profile action.", 400)
			return
		}
		if err != nil {
			fail(err.Error(), 400)
			return
		}
	} else if r.Method != "GET" {
		fail("Method not allowed.", 405)
		return
	}
	warning := ""
	if profileSyncEnabled() && (action == "start" || action == "refresh" || action == "state" && time.Now().Unix()-c.ProfileUpdated > 900) {
		_, err = online(&c)
		if err != nil {
			warning = "Profile could not refresh. Your cached account and local applications remain available."
		}
	}
	_ = json.NewEncoder(w).Encode(cliProfileState(c, warning))
}
