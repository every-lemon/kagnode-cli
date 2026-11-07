package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"net/http/httptest"
	"testing"
)

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
