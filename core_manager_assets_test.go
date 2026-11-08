package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"regexp"
	"testing"
)

func TestBundledManagerMatchesReviewedProvenance(t *testing.T) {
	raw, err := assets.ReadFile("assets/core-manager-manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Schema     int    `json:"schema"`
		Repository string `json:"repository"`
		Version    string `json:"version"`
		Commit     string `json:"source_commit"`
		Source     string `json:"source_path"`
		SHA        string `json:"sha256"`
	}
	if err = json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Schema != 1 || manifest.Repository != "every-lemon/kagnode-core" || manifest.Source != "packages/python/manager.py" || !regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`).MatchString(manifest.Version) || !regexp.MustCompile(`^[a-f0-9]{40}$`).MatchString(manifest.Commit) {
		t.Fatal("Invalid reviewed manager provenance")
	}
	bundled, err := assets.ReadFile("assets/core_manager.py")
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(bundled)
	if hex.EncodeToString(digest[:]) != manifest.SHA {
		t.Fatal("Bundled manager differs from reviewed source checksum")
	}
	source, err := os.ReadFile("vendor/core-source/packages/python/manager.py")
	if err != nil {
		t.Fatal(err)
	}
	if string(source) != string(bundled) {
		t.Fatal("Corresponding manager source differs from the bundled helper")
	}
}
