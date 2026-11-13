package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
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
func TestLegacyCredentialsAndPrivateStorage(t *testing.T) {
	testHome(t)
	c := credentials{Base: "https://nebulacoder.com", ID: "legacy-subject", Name: "Legacy", Offline: true}
	if err := saveCredentials(c); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(pathFor("config"), "account.json")
	info, _ := os.Stat(file)
	if info.Mode().Perm() != 0600 {
		t.Fatal("credentials not private")
	}
	got, err := readCredentials()
	if err != nil || got.ID != c.ID || got.Protocol != "" {
		t.Fatal("legacy credentials changed", err)
	}
	os.Chmod(file, 0644)
	if _, err = readCredentials(); err == nil {
		t.Fatal("accepted exposed credential file")
	}
}
func TestNewDistributionHasNoFictionalAssets(t *testing.T) {
	names, err := assets.ReadDir("assets")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range names {
		for _, prefix := range []string{"demo", "frame-", "workspace-", "catalog.json", "index.html"} {
			if strings.HasPrefix(entry.Name(), prefix) {
				t.Fatal("retired asset embedded", entry.Name())
			}
		}
	}
}

func TestCredentialsRejectNonregularAliasesWithoutHanging(t *testing.T) {
	testHome(t)
	if err := saveCredentials(credentials{Base: "https://nebulacoder.com", ID: "legacy"}); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(pathFor("config"), "account.json")
	kept := path + ".kept"
	if err := os.Link(path, kept); err != nil {
		t.Fatal(err)
	}
	if _, err := readCredentials(); err == nil {
		t.Fatal("hardlinked credentials accepted")
	}
	os.Remove(path)
	if err := os.Symlink(kept, path); err != nil {
		t.Fatal(err)
	}
	if _, err := readCredentials(); err == nil {
		t.Fatal("symlink credentials accepted")
	}
	os.Remove(path)
	if err := syscall.Mkfifo(path, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := readCredentials(); err == nil {
		t.Fatal("FIFO credentials accepted")
	}
}
