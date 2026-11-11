package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDemoPagesUseOneSharedAccountMenu(t *testing.T) {
	for _, page := range append([]string{"index"}, productIDs...) {
		name := "assets/built/index.html"
		if page != "index" {
			name = "assets/built/workspace-" + page + ".html"
		}
		body, err := assets.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		text := string(body)
		if strings.Count(text, `id="account-menu"`) != 1 || strings.Count(text, `data-core-account-trigger`) != 1 {
			t.Fatalf("%s must contain one shared Core account control", page)
		}
		if strings.Contains(text, "data-cli-account") || strings.Contains(text, `<details class="kn-cli-profile"`) {
			t.Fatalf("%s contains an unresolved or retired account control", page)
		}
		if !strings.Contains(text, `data-kn-account-name`) || !strings.Contains(text, `data-kn-account-settings`) {
			t.Fatalf("%s lost synchronized identity or account preferences", page)
		}
	}
}

func TestCorePatchCompatibilityUsesApplicationBaseline(t *testing.T) {
	for _, tc := range []struct {
		version, baseline string
		want              bool
	}{
		{"5.0.0", "5.0.0", true},
		{"5.0.12", "5.0.0", true},
		{"5.1.0", "5.0.0", false},
		{"5.0.0-rc.1", "5.0.0", false},
		{"1.4.99", "5.0.0", false},
		{"1.3.0", "1.3.0", true},
		{"1.3.12", "1.3.0", true},
		{"1.0.9", "1.0.5", true},
		{"1.0.4", "1.0.5", false},
		{"1.0.9", "1.3.0", false},
		{"1.4.0", "1.3.0", false},
		{"2.3.0", "1.3.0", false},
		{"1.30.0", "1.3.0", false},
		{"1.3.0-rc.1", "1.3.0", false},
		{"01.3.0", "1.3.0", false},
		{"1.3.18446744073709551616", "1.3.0", false},
		{"1.3.0", "invalid", false},
	} {
		t.Run(tc.version+"_from_"+tc.baseline, func(t *testing.T) {
			if got := corePatchCompatible(tc.version, tc.baseline); got != tc.want {
				t.Fatalf("Core %q from baseline %q: compatible=%v, want %v", tc.version, tc.baseline, got, tc.want)
			}
		})
	}
}

func TestBundledCoreBytesMatchPinnedInventory(t *testing.T) {
	raw, err := assets.ReadFile("assets/core-bundle.json")
	if err != nil {
		t.Fatal(err)
	}
	var bundle struct {
		Version string `json:"version"`
		Files   map[string]struct {
			SHA string `json:"sha256"`
		} `json:"files"`
	}
	if err = json.Unmarshal(raw, &bundle); err != nil {
		t.Fatal(err)
	}
	source, err := fs.Sub(assets, "assets")
	if err != nil {
		t.Fatal(err)
	}
	handler := builtDemoAssets(source)
	for name, meta := range bundle.Files {
		r := httptest.NewRecorder()
		handler.ServeHTTP(r, httptest.NewRequest("GET", "/kagnode-core/"+bundle.Version+"/"+name, nil))
		if r.Code != 200 {
			t.Fatalf("%s: %d", name, r.Code)
		}
		digest := sha256.Sum256(r.Body.Bytes())
		if hex.EncodeToString(digest[:]) != meta.SHA {
			t.Fatalf("Core bytes changed during application build: %s", name)
		}
	}
}
