package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"html"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
)

var coreVersionPattern = regexp.MustCompile(`^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$`)

// Application upgrades select the baseline explicitly. A retained manager
// binding may replace that baseline only with a patch on the same minor line.
func corePatchCompatible(version, baseline string) bool {
	current, minimum := coreVersionPattern.FindStringSubmatch(version), coreVersionPattern.FindStringSubmatch(baseline)
	if current == nil || minimum == nil || current[1] != minimum[1] || current[2] != minimum[2] {
		return false
	}
	patch, err := strconv.ParseUint(current[3], 10, 64)
	if err != nil {
		return false
	}
	floor, err := strconv.ParseUint(minimum[3], 10, 64)
	return err == nil && patch >= floor
}

func coreHTML(original []byte) []byte {
	if !strings.Contains(string(original), `name="kagnode-core"`) {
		return original
	}
	root := os.Getenv("KAGNODE_CORE_ROOT")
	if root == "" {
		root = "/srv/kagnode/core"
	}
	if !filepath.IsAbs(root) {
		return original
	}
	p := filepath.Join(root, "apps", "cli", "state.json")
	info, err := os.Lstat(p)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0022 != 0 {
		return original
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != 0 {
		return original
	}
	data, err := os.ReadFile(p)
	if err != nil {
		return original
	}
	var state struct {
		Version string `json:"version"`
	}
	if json.Unmarshal(data, &state) != nil || !coreVersionPattern.MatchString(state.Version) {
		return original
	}
	manifestBytes, err := os.ReadFile(filepath.Join(root, "releases", state.Version, "manifest.json"))
	if err != nil {
		return original
	}
	var latest struct {
		API         int               `json:"ui_api"`
		Entrypoints map[string]string `json:"entrypoints"`
	}
	if json.Unmarshal(manifestBytes, &latest) != nil || latest.API != 1 {
		return original
	}
	baselineBytes, err := assets.ReadFile("assets/core-bundle.json")
	if err != nil {
		return original
	}
	var baseline struct {
		Version     string            `json:"version"`
		Entrypoints map[string]string `json:"entrypoints"`
	}
	if json.Unmarshal(baselineBytes, &baseline) != nil {
		return original
	}
	if !corePatchCompatible(state.Version, baseline.Version) {
		return original
	}
	result := string(original)
	for kind, old := range baseline.Entrypoints {
		name, ok := latest.Entrypoints[kind]
		if !ok {
			return original
		}
		url := "/kagnode-core/" + state.Version + "/" + name
		if _, _, ok = coreCachedAsset(url); !ok {
			return original
		}
		result = strings.ReplaceAll(result, "/kagnode-core/"+baseline.Version+"/"+old, url)
	}
	re := regexp.MustCompile(`<meta name="kagnode-core" content="([^"]*)">`)
	result = re.ReplaceAllStringFunc(result, func(tag string) string {
		m := re.FindStringSubmatch(tag)
		var value map[string]any
		if json.Unmarshal([]byte(html.UnescapeString(m[1])), &value) != nil {
			return tag
		}
		value["version"] = state.Version
		value["base"] = "/kagnode-core/" + state.Version + "/"
		raw, _ := json.Marshal(value)
		return `<meta name="kagnode-core" content="` + html.EscapeString(string(raw)) + `">`
	})
	return []byte(result)
}

// A bound Core manager may replace UI assets only. The embedded baseline remains
// available offline and old immutable URLs keep working through normal assets.
func coreCachedAsset(url string) ([]byte, string, bool) {
	match := regexp.MustCompile(`^/kagnode-core/(\d+\.\d+\.\d+)/([a-zA-Z0-9_.-]+)$`).FindStringSubmatch(url)
	if match == nil {
		return nil, "", false
	}
	root := os.Getenv("KAGNODE_CORE_ROOT")
	if root == "" {
		root = "/srv/kagnode/core"
	}
	if !filepath.IsAbs(root) {
		return nil, "", false
	}
	protected := func(p string) bool {
		info, e := os.Lstat(p)
		if e != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0022 != 0 {
			return false
		}
		s, ok := info.Sys().(*syscall.Stat_t)
		return ok && s.Uid == 0
	}
	base := filepath.Join(root, "releases", match[1])
	manifestPath := filepath.Join(base, "manifest.json")
	if !protected(manifestPath) {
		return nil, "", false
	}
	raw, e := os.ReadFile(manifestPath)
	if e != nil {
		return nil, "", false
	}
	var manifest struct {
		Version string `json:"version"`
		API     int    `json:"ui_api"`
		Files   map[string]struct {
			SHA  string `json:"sha256"`
			Size int    `json:"size"`
		} `json:"files"`
	}
	if json.Unmarshal(raw, &manifest) != nil || manifest.Version != match[1] || manifest.API != 1 {
		return nil, "", false
	}
	meta, ok := manifest.Files[match[2]]
	if !ok || meta.Size > 16*1024*1024 {
		return nil, "", false
	}
	p := filepath.Join(base, match[2])
	if !protected(p) {
		return nil, "", false
	}
	data, e := os.ReadFile(p)
	if e != nil || len(data) != meta.Size {
		return nil, "", false
	}
	digest := sha256.Sum256(data)
	if hex.EncodeToString(digest[:]) != meta.SHA {
		return nil, "", false
	}
	types := map[string]string{".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2"}
	kind, ok := types[strings.ToLower(filepath.Ext(p))]
	return data, kind, ok
}
