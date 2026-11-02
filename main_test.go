package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"unicode/utf8"
)

func TestBannerFitsTerminalWidths(t *testing.T) {
	for _, width := range []int{1, 2, 3, 8, 9, 18, 19, 22, 23, 40, 68, 69, 80, 100, 112, 113, 120, 160} {
		art := bannerArt(width)
		for _, line := range strings.Split(art, "\n") {
			if len(line) >= width {
				t.Fatalf("banner wraps at %d columns: %q", width, line)
			}
		}
		if strings.Contains(art, "\x1b") || strings.ContainsRune(art, '\t') || strings.ContainsRune(art, '\r') {
			t.Fatal("control characters in plain banner")
		}
	}
	if !strings.Contains(bannerArt(80), "#####") {
		t.Fatal("standard terminal lost the block wordmark")
	}
	if len(bannerArt(120)) <= len(bannerArt(80)) {
		t.Fatal("wide terminal did not select the larger layout")
	}
}

func TestColorBannerPreservesUnicodeAndAlignment(t *testing.T) {
	escape := regexp.MustCompile(`\x1b\[[0-9;]*m`)
	for _, width := range []int{19, 23, 40, 69, 80, 113, 120} {
		plain := renderBanner(width, true, false)
		colored := renderBanner(width, true, true)
		if !utf8.ValidString(colored) {
			t.Fatal("color split a Unicode cell")
		}
		if escape.ReplaceAllString(colored, "") != plain {
			t.Fatal("colored banner changed alignment")
		}
		for _, line := range strings.Split(plain, "\n") {
			if utf8.RuneCountInString(line) >= width {
				t.Fatalf("block banner wraps at %d", width)
			}
		}
	}
	if strings.Contains(renderBanner(80, false, false), "\x1b") {
		t.Fatal("plain output contains terminal escapes")
	}
}

func testHome(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(dir, "config"))
	t.Setenv("XDG_DATA_HOME", filepath.Join(dir, "data"))
}
func TestOriginValidation(t *testing.T) {
	for _, origin := range []string{"http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?token=secret", "file:///etc/passwd"} {
		if _, err := validBase(origin); err == nil {
			t.Fatal("accepted", origin)
		}
	}
	for _, origin := range []string{"https://nebulacoder.com", "http://127.0.0.1:8791"} {
		if _, err := validBase(origin); err != nil {
			t.Fatal(err)
		}
	}
}
func TestFirstSignInAndPrivateStorage(t *testing.T) {
	testHome(t)
	if err := demoInstall(); err == nil {
		t.Fatal("installed without sign-in")
	}
	c := credentials{Base: "https://nebulacoder.com", ID: "fictional-account", Name: "Sample", Offline: true}
	if err := saveCredentials(c); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(pathFor("config"), "account.json")
	info, _ := os.Stat(file)
	if info.Mode().Perm() != 0600 {
		t.Fatal("credentials not private")
	}
	if err := demoInstall(); err != nil {
		t.Fatal(err)
	}
	catalog, err := catalog()
	if err != nil || len(catalog) != 13 {
		t.Fatal("incomplete catalog", err)
	}
	for _, p := range catalog {
		if _, err := state(p.ID); err != nil {
			t.Fatal(err)
		}
	}
	os.Chmod(file, 0644)
	if _, err := readCredentials(); err == nil {
		t.Fatal("accepted exposed credential file")
	}
}
func TestAllProductsResetAndTraversal(t *testing.T) {
	testHome(t)
	saveCredentials(credentials{Base: "https://nebulacoder.com", ID: "sample", Offline: true})
	demoInstall()
	for _, p := range productIDs {
		if err := demoCommand([]string{p, "create", "QA Example"}); err != nil {
			t.Fatal(p, err)
		}
		m, _ := state(p)
		resources := m["resources"].([]any)
		last := resources[len(resources)-1].(map[string]any)
		if str(last, "name") != "QA Example" {
			t.Fatal(p)
		}
		if err := demoCommand([]string{p, "delete", str(last, "id")}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := state("../../account"); err == nil {
		t.Fatal("path traversal")
	}
	if err := demoCommand([]string{"reset"}); err != nil {
		t.Fatal(err)
	}
	for _, p := range productIDs {
		b, err := assets.ReadFile("assets/frame-" + p + ".html")
		if err != nil || !strings.Contains(string(b), "connect-src &#39;none&#39;") {
			t.Fatal("missing sandbox", p, err)
		}
	}
	os.Remove(filepath.Join(pathFor("config"), "account.json"))
	if err := installed(); err == nil {
		t.Fatal("offline demos survived local sign-out")
	}
}
