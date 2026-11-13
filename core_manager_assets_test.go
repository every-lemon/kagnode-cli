package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
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
		Schema      int    `json:"schema"`
		Repository  string `json:"repository"`
		Version     string `json:"version"`
		Commit      string `json:"source_commit"`
		Source      string `json:"source_path"`
		SHA         string `json:"sha256"`
		KeySHA      string `json:"public_key_sha256"`
		ManifestSHA string `json:"release_manifest_sha256"`
		SourceSHA   string `json:"source_archive_sha256"`
		WheelSHA    string `json:"python_wheel_sha256"`
		API         int    `json:"manager_api"`
		Policy      string `json:"upgrade_policy"`
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
	keyBytes, err := os.ReadFile("vendor/core-source/assets/release-public.pem")
	if err != nil {
		t.Fatal(err)
	}
	keyDigest := sha256.Sum256(keyBytes)
	if hex.EncodeToString(keyDigest[:]) != manifest.KeySHA || manifest.API != 1 || manifest.Policy != "explicit-review" {
		t.Fatal("helper key/policy provenance is missing")
	}
	block, _ := pem.Decode(keyBytes)
	if block == nil {
		t.Fatal("invalid pinned public key")
	}
	parsed, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	key, ok := parsed.(ed25519.PublicKey)
	if !ok {
		t.Fatal("Core release key must use Ed25519")
	}
	signed, err := os.ReadFile("vendor/core-source/release/release-manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	signature, err := os.ReadFile("vendor/core-source/release/release-manifest.sig")
	if err != nil {
		t.Fatal(err)
	}
	manifestDigest := sha256.Sum256(signed)
	if hex.EncodeToString(manifestDigest[:]) != manifest.ManifestSHA || !ed25519.Verify(key, signed, signature) {
		t.Fatal("invalid signed full-release provenance")
	}
	var release struct {
		Version  string `json:"version"`
		Commit   string `json:"source_commit"`
		Packages []struct {
			Name string `json:"name"`
			SHA  string `json:"sha256"`
		} `json:"packages"`
	}
	if json.Unmarshal(signed, &release) != nil || release.Version != manifest.Version || release.Commit != manifest.Commit {
		t.Fatal("helper source identity differs from signed release")
	}
	foundSource, foundWheel := false, false
	for _, entry := range release.Packages {
		if entry.Name == "kagnode-core-"+manifest.Version+"-source.tar.gz" {
			foundSource = entry.SHA == manifest.SourceSHA
		}
		if entry.Name == "kagnode_core-"+manifest.Version+"-py3-none-any.whl" {
			foundWheel = entry.SHA == manifest.WheelSHA
		}
	}
	if !foundSource || !foundWheel {
		t.Fatal("helper source/wheel not covered by signed release")
	}

}
