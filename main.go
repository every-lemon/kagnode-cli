// KagNode CLI: real account sign-in, explicitly fictional product workflows.
package main

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

//go:embed assets/*.html assets/*.json assets/*.css assets/*.js assets/*.svg assets/*.txt assets/*.py assets/built/*
var assets embed.FS

const version = "1.2.0-beta.1"

var productIDs = []string{"console", "vps", "q1", "cdn", "cloud-pc", "ai", "vpn", "cloud-browser", "edu", "biz", "enterprise", "tunnel", "status"}

type credentials struct {
	Base           string `json:"base"`
	Access         string `json:"access_token"`
	Refresh        string `json:"refresh_token"`
	Expires        int64  `json:"expires"`
	Name           string `json:"name"`
	Photo          string `json:"photo,omitempty"`
	ProfileUpdated int64  `json:"profile_updated,omitempty"`
	ID             string `json:"id"`
	Offline        bool   `json:"offline_demo_access"`
}
type product struct {
	ID     string         `json:"id"`
	Title  string         `json:"title"`
	Sample map[string]any `json:"sample"`
}
type localServer struct {
	URL string `json:"url"`
	Key string `json:"key"`
}

var input = bufio.NewReader(os.Stdin)

func pathFor(kind string) string {
	var base string
	if kind == "config" {
		base = os.Getenv("XDG_CONFIG_HOME")
		if base == "" {
			h, _ := os.UserHomeDir()
			base = filepath.Join(h, ".config")
		}
	} else {
		base = os.Getenv("XDG_DATA_HOME")
		if base == "" {
			h, _ := os.UserHomeDir()
			base = filepath.Join(h, ".local", "share")
		}
	}
	return filepath.Join(base, "kagnode", "cli")
}
func ensureDir(p string) error {
	if err := os.MkdirAll(p, 0700); err != nil {
		return err
	}
	info, err := os.Lstat(p)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("unsafe CLI directory")
	}
	return os.Chmod(p, 0700)
}
func writePrivate(p string, v any) error {
	if err := ensureDir(filepath.Dir(p)); err != nil {
		return err
	}
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(p), ".kagnode-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(data)
	}
	if closeErr := f.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(f.Name(), p)
}
func readCredentials() (credentials, error) {
	var c credentials
	p := filepath.Join(pathFor("config"), "account.json")
	info, err := os.Lstat(p)
	if err != nil {
		return c, errors.New("sign in first with: kagnode login")
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return c, errors.New("account file must be a regular file accessible only to its owner (0600)")
	}
	b, err := os.ReadFile(p)
	if err == nil {
		err = json.Unmarshal(b, &c)
	}
	if err == nil {
		_, err = validBase(c.Base)
	}
	return c, err
}
func saveCredentials(c credentials) error {
	return writePrivate(filepath.Join(pathFor("config"), "account.json"), c)
}
func validBase(base string) (string, error) {
	u, err := url.Parse(base)
	if err != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return "", errors.New("use an HTTPS account origin")
	}
	local := u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost" || u.Hostname() == "::1"
	if u.Scheme != "https" && !(u.Scheme == "http" && local) {
		return "", errors.New("HTTPS is required except for loopback development")
	}
	return strings.TrimSuffix(base, "/"), nil
}
func requestJSON(base, route, token string, data any) (map[string]any, int, error) {
	if _, err := validBase(base); err != nil {
		return nil, 0, err
	}
	method := "GET"
	var body io.Reader
	if data != nil {
		method = "POST"
		b, err := json.Marshal(data)
		if err != nil {
			return nil, 0, err
		}
		body = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, base+route, body)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "KagNode-CLI/"+version)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	client := &http.Client{Timeout: 20 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
		return errors.New("account redirects are not followed")
	}}
	res, err := client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer res.Body.Close()
	out := map[string]any{}
	if res.StatusCode == 204 {
		return out, res.StatusCode, nil
	}
	err = json.NewDecoder(io.LimitReader(res.Body, 1<<20)).Decode(&out)
	return out, res.StatusCode, err
}
func str(m map[string]any, k string) string {
	v, _ := m[k].(string)
	return strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return -1
		}
		return r
	}, v)
}
func num(m map[string]any, k string) int64 { v, _ := m[k].(float64); return int64(v) }

// terminalSize uses the Linux terminal itself, so redirected logs stay uncolored.
func terminalSize() (int, bool) {
	var size [4]uint16
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, os.Stdout.Fd(), syscall.TIOCGWINSZ, uintptr(unsafe.Pointer(&size)))
	if errno != 0 {
		return 80, false
	}
	if size[1] == 0 {
		return 80, true
	}
	return int(size[1]), true
}
func bannerArt(columns int) string {
	for _, name := range []string{"kagnode-display-ascii.txt", "kagnode-ascii.txt", "kagnode-compact-ascii.txt", "kagnode-small-ascii.txt"} {
		art, err := assets.ReadFile("assets/" + name)
		if err != nil {
			continue
		}
		fits := true
		for _, line := range strings.Split(string(art), "\n") {
			if len(line) >= columns {
				fits = false
				break
			}
		}
		if fits {
			return string(art)
		}
	}
	if columns > 8 {
		return "KagNode.\n"
	}
	if columns > 2 {
		return "KN\n"
	}
	return ""
}
func banner() {
	columns, terminal := terminalSize()
	_, noColor := os.LookupEnv("NO_COLOR")
	color := terminal && !noColor && os.Getenv("TERM") != "" && os.Getenv("TERM") != "dumb"
	fmt.Println()
	locale := os.Getenv("LC_ALL")
	if locale == "" {
		locale = os.Getenv("LC_CTYPE")
	}
	if locale == "" {
		locale = os.Getenv("LANG")
	}
	locale = strings.ToUpper(locale)
	blocks := terminal && os.Getenv("TERM") != "dumb" && os.Getenv("TERM") != "" && (strings.Contains(locale, "UTF-8") || strings.Contains(locale, "UTF8"))
	fmt.Print(renderBanner(columns, blocks, color))
	fmt.Printf("\n  CLI %s\n", version)
}

func renderBanner(columns int, blocks, color bool) string {
	art := bannerArt(columns)
	if !color {
		if blocks {
			return strings.ReplaceAll(art, "#", "█")
		}
		return art
	}
	width := 0
	for _, line := range strings.Split(art, "\n") {
		if len(line) > width {
			width = len(line)
		}
	}
	cut := width
	if width > 90 {
		cut = 26
	} else if width > 45 {
		cut = 25
	}
	var result strings.Builder
	for _, line := range strings.Split(strings.TrimSuffix(art, "\n"), "\n") {
		at := cut
		if at > len(line) {
			at = len(line)
		}
		left, right := line[:at], line[at:]
		if blocks {
			left = strings.ReplaceAll(left, "#", "█")
			right = strings.ReplaceAll(right, "#", "█")
		}
		result.WriteString("\033[94m" + left + "\033[97m" + right + "\033[0m\n")
	}
	return result.String()
}

func login(base string) error {
	base, err := validBase(base)
	if err != nil {
		return err
	}
	m, status, err := requestJSON(base, "/api/cli/device", "", map[string]string{"client_id": "kagnode-cli"})
	if err != nil {
		return err
	}
	if status != 200 {
		return fmt.Errorf("device sign-in unavailable (%d)", status)
	}
	device, code, verify := str(m, "device_code"), str(m, "user_code"), str(m, "verification_uri")
	if device == "" || code == "" || verify != base+"/account/cli/device" {
		return errors.New("invalid device response")
	}
	banner()
	fmt.Printf("\nOpen %s\nEnter code: %s\nApprove only this request in your browser.\nWaiting for your approval…\n", verify, code)
	deadline := time.Now().Add(10 * time.Minute)
	interval := 5 * time.Second
	for time.Now().Before(deadline) {
		time.Sleep(interval)
		m, status, err = requestJSON(base, "/api/cli/token", "", map[string]string{"client_id": "kagnode-cli", "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": device})
		if err != nil {
			return err
		}
		if status == 200 {
			if str(m, "access_token") == "" || str(m, "refresh_token") == "" {
				return errors.New("invalid token response")
			}
			c := credentials{Base: base, Access: str(m, "access_token"), Refresh: str(m, "refresh_token"), Expires: time.Now().Unix() + num(m, "expires_in"), Offline: true}
			me, status, err := requestJSON(base, "/api/cli/me", c.Access, nil)
			if err != nil {
				return err
			}
			if status != 200 {
				return errors.New("unable to verify account")
			}
			c.Name = str(me, "name")
			if photo := str(me, "photo"); profileSyncEnabled() && len(photo) <= 180000 && (photo == "" || profilePhotoPattern.MatchString(photo)) {
				c.Photo = photo
			}
			c.ID = str(me, "id")
			if err = saveCredentials(c); err != nil {
				return err
			}
			fmt.Println("Signed in as " + c.Name + ".\nRun kagnode demo install to install the fictional examples.")
			return nil
		}
		switch str(m, "error") {
		case "authorization_pending":
			continue
		case "slow_down":
			interval += 5 * time.Second
			continue
		default:
			return fmt.Errorf("sign-in ended: %s", str(m, "error"))
		}
	}
	return errors.New("device code expired; run kagnode login again")
}
func online(c *credentials) (map[string]any, error) {
	if time.Now().Unix() >= c.Expires-30 {
		m, status, err := requestJSON(c.Base, "/api/cli/token", "", map[string]string{"client_id": "kagnode-cli", "grant_type": "refresh_token", "refresh_token": c.Refresh})
		if err != nil {
			return nil, fmt.Errorf("refresh could not be confirmed; sign in again: %w", err)
		}
		if status != 200 {
			return nil, errors.New("account authorization expired or was revoked; run kagnode login")
		}
		if str(m, "access_token") == "" || str(m, "refresh_token") == "" {
			return nil, errors.New("invalid refresh response")
		}
		c.Access = str(m, "access_token")
		c.Refresh = str(m, "refresh_token")
		c.Expires = time.Now().Unix() + num(m, "expires_in")
		if err = saveCredentials(*c); err != nil {
			return nil, err
		}
	}
	m, status, err := requestJSON(c.Base, "/api/cli/me", c.Access, nil)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, errors.New("account access is unavailable; sign in again")
	}
	if err := cacheProfile(c, m); err != nil {
		return nil, err
	}
	return m, nil
}
func logout() error {
	c, err := readCredentials()
	if err == nil {
		_, status, callErr := requestJSON(c.Base, "/api/cli/revoke", "", map[string]string{"token": c.Refresh})
		if callErr != nil || status != 204 {
			fmt.Println("Online revocation was not confirmed. Revoke this device in your KagNode account when online.")
		}
	}
	_ = stopDemo()
	if err = os.Remove(filepath.Join(pathFor("config"), "account.json")); err != nil && !os.IsNotExist(err) {
		return err
	}
	fmt.Println("Signed out. Local credentials and offline demo access removed.")
	return nil
}
func requireDemo() error {
	c, err := readCredentials()
	if err != nil {
		return err
	}
	if !c.Offline || c.ID == "" {
		return errors.New("sign in once to use offline demos")
	}
	return nil
}
func catalog() ([]product, error) {
	b, err := assets.ReadFile("assets/catalog.json")
	if err != nil {
		return nil, err
	}
	var p []product
	err = json.Unmarshal(b, &p)
	return p, err
}
func demoInstall() error {
	if err := requireDemo(); err != nil {
		return err
	}
	p, err := catalog()
	if err != nil {
		return err
	}
	if err = writePrivate(filepath.Join(pathFor("data"), "installed.json"), map[string]any{"version": version, "products": productIDs, "fictional": true}); err != nil {
		return err
	}
	for _, item := range p {
		file := filepath.Join(pathFor("data"), "state", item.ID+".json")
		if _, err = os.Stat(file); os.IsNotExist(err) {
			if err = writePrivate(file, item.Sample); err != nil {
				return err
			}
		}
	}
	fmt.Println("Installed 13 fictional terminal and browser demos. No cloud resources were created.")
	return nil
}
func installed() error {
	if err := requireDemo(); err != nil {
		return err
	}
	if _, err := os.Stat(filepath.Join(pathFor("data"), "installed.json")); err != nil {
		return errors.New("install examples first: kagnode demo install")
	}
	return nil
}
func known(product string) bool {
	for _, id := range productIDs {
		if product == id {
			return true
		}
	}
	return false
}
func state(product string) (map[string]any, error) {
	if !known(product) {
		return nil, errors.New("unknown demo product")
	}
	b, err := os.ReadFile(filepath.Join(pathFor("data"), "state", product+".json"))
	if err != nil {
		return nil, err
	}
	m := map[string]any{}
	err = json.Unmarshal(b, &m)
	return m, err
}
func randomKey() string { b := make([]byte, 24); _, _ = rand.Read(b); return hex.EncodeToString(b) }
func demoCommand(args []string) error {
	if len(args) == 0 {
		return menu()
	}
	switch args[0] {
	case "install":
		return demoInstall()
	case "start":
		return startDemo()
	case "serve":
		return serveDemo()
	case "stop":
		return stopDemo()
	case "reset":
		if err := installed(); err != nil {
			return err
		}
		p, _ := catalog()
		for _, item := range p {
			if err := writePrivate(filepath.Join(pathFor("data"), "state", item.ID+".json"), item.Sample); err != nil {
				return err
			}
		}
		fmt.Println("Fictional terminal data reset. Refresh a browser demo to reset its memory.")
		return nil
	case "list":
		if err := installed(); err != nil {
			return err
		}
		p, _ := catalog()
		fmt.Println("FICTIONAL DEMOS · no live services")
		for _, v := range p {
			fmt.Printf("  %-16s %s\n", v.ID, v.Title)
		}
		return nil
	}
	if err := installed(); err != nil {
		return err
	}
	id := args[0]
	m, err := state(id)
	if err != nil {
		return err
	}
	fmt.Println("FICTIONAL DEMO · " + id + " · no live resources or charges")
	action := "list"
	if len(args) > 1 {
		action = args[1]
	}
	resources, _ := m["resources"].([]any)
	switch action {
	case "list":
		for _, raw := range resources {
			r, _ := raw.(map[string]any)
			fmt.Printf("  %-18s %-28s %s\n", str(r, "id"), str(r, "name"), str(r, "state"))
		}
	case "create":
		if len(args) < 3 {
			return errors.New("usage: kagnode demo " + id + " create NAME")
		}
		if len(resources) >= 500 {
			return errors.New("demo limit reached; remove a resource or reset")
		}
		name := strings.Join(args[2:], " ")
		if len(name) > 100 {
			return errors.New("name must be 100 characters or fewer")
		}
		r := map[string]any{"id": "demo-" + randomKey()[:8], "name": name, "project": "studio", "state": "Ready"}
		m["resources"] = append(resources, r)
		if err = writePrivate(filepath.Join(pathFor("data"), "state", id+".json"), m); err != nil {
			return err
		}
		fmt.Println("Created fictional resource " + str(r, "id"))
	case "delete":
		if len(args) != 3 {
			return errors.New("usage: kagnode demo " + id + " delete ID")
		}
		next := []any{}
		found := false
		for _, raw := range resources {
			r, _ := raw.(map[string]any)
			if str(r, "id") == args[2] {
				found = true
			} else {
				next = append(next, raw)
			}
		}
		if !found {
			return errors.New("fictional resource not found")
		}
		m["resources"] = next
		return writePrivate(filepath.Join(pathFor("data"), "state", id+".json"), m)
	case "settings":
		b, _ := json.MarshalIndent(m["settings"], "", "  ")
		fmt.Println(string(b))
	case "prompt":
		if id != "ai" || len(args) < 3 {
			return errors.New("usage: kagnode demo ai prompt TEXT")
		}
		fmt.Println("Sample response: this is predefined demonstration output. No AI model was called.")
	default:
		return errors.New("choose list, create, delete, settings, or ai prompt")
	}
	return nil
}
func startDemo() error {
	if err := installed(); err != nil {
		return err
	}
	if b, err := os.ReadFile(filepath.Join(pathFor("data"), "server.json")); err == nil {
		var s localServer
		if json.Unmarshal(b, &s) == nil && localAddress(s.URL) {
			client := &http.Client{Timeout: time.Second}
			res, err := client.Get(s.URL + "/health")
			if err == nil {
				res.Body.Close()
				if res.StatusCode == 200 {
					fmt.Println("Demo running: " + s.URL + "/?key=" + s.Key)
					return nil
				}
			}
		}
	}
	_ = os.Remove(filepath.Join(pathFor("data"), "server.json"))
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	if err = ensureDir(pathFor("data")); err != nil {
		return err
	}
	log, err := os.OpenFile(filepath.Join(pathFor("data"), "demo.log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		return err
	}
	defer log.Close()
	cmd := exec.Command(executable, "demo", "serve")
	cmd.Stdout = log
	cmd.Stderr = log
	cmd.Stdin = nil
	if err = cmd.Start(); err != nil {
		return err
	}
	_ = cmd.Process.Release()
	for n := 0; n < 40; n++ {
		time.Sleep(100 * time.Millisecond)
		b, err := os.ReadFile(filepath.Join(pathFor("data"), "server.json"))
		if err != nil {
			continue
		}
		var s localServer
		if json.Unmarshal(b, &s) == nil {
			fmt.Println("Open the local demo: " + s.URL + "/?key=" + s.Key + "\nOnly your computer can access this server. Stop it with kagnode demo stop.")
			return nil
		}
	}
	return errors.New("demo server did not start; inspect demo.log")
}
func stopDemo() error {
	b, err := os.ReadFile(filepath.Join(pathFor("data"), "server.json"))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	var s localServer
	if err = json.Unmarshal(b, &s); err != nil {
		return err
	}
	u, err := url.Parse(s.URL)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" {
		return errors.New("invalid local server address")
	}
	req, _ := http.NewRequest("POST", s.URL+"/stop", nil)
	req.Header.Set("Authorization", "Bearer "+s.Key)
	client := &http.Client{Timeout: 2 * time.Second}
	res, err := client.Do(req)
	if err != nil {
		return errors.New("demo server is unavailable")
	}
	res.Body.Close()
	if res.StatusCode != 200 {
		return errors.New("demo server refused stop")
	}
	fmt.Println("Local demo server stopped.")
	return nil
}
func localAddress(raw string) bool {
	u, err := url.Parse(raw)
	return err == nil && u.Scheme == "http" && u.Hostname() == "127.0.0.1" && u.Port() != "" && u.User == nil && u.RawQuery == "" && u.Fragment == "" && u.Path == ""
}
func serveDemo() error {
	if err := ensureDir(pathFor("data")); err != nil {
		return err
	}
	lock, err := os.OpenFile(filepath.Join(pathFor("data"), "server.lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer lock.Close()
	if err = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return errors.New("a local demo server is already starting or running")
	}
	if err := installed(); err != nil {
		return err
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	base := "http://" + listener.Addr().String()
	key := randomKey()
	s := localServer{URL: base, Key: key}
	if err = writePrivate(filepath.Join(pathFor("data"), "server.json"), s); err != nil {
		listener.Close()
		return err
	}
	defer os.Remove(filepath.Join(pathFor("data"), "server.json"))
	assetFS, _ := fs.Sub(assets, "assets")
	files := builtDemoAssets(assetFS)
	server := &http.Server{ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 8192}
	server.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Host != listener.Addr().String() {
			http.Error(w, "Invalid host", 403)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		if r.URL.Path == "/health" {
			fmt.Fprint(w, "KagNode fictional demo")
			return
		}
		if r.URL.Path == "/stop" {
			if r.Method != "POST" || r.Header.Get("Authorization") != "Bearer "+key {
				http.Error(w, "Denied", 403)
				return
			}
			fmt.Fprint(w, "Stopped")
			go func() { time.Sleep(50 * time.Millisecond); _ = server.Close() }()
			return
		}
		if r.URL.Path == "/" && r.URL.Query().Get("key") == key {
			http.SetCookie(w, &http.Cookie{Name: "kagnode_demo", Value: key, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode})
			http.Redirect(w, r, "/demos/workspace", 303)
			return
		}
		cookie, err := r.Cookie("kagnode_demo")
		if err != nil || cookie.Value != key {
			http.Error(w, "Open the address printed by kagnode demo start.", 403)
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" && origin != base && origin != "null" {
			http.Error(w, "Denied", 403)
			return
		}
		if r.URL.Path == "/api/kagnode-account" {
			serveAccountProfile(w, r, base)
			return
		}
		w.Header().Set("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://nebulacoder.com; object-src 'none'; frame-ancestors 'none'; form-action 'none'")
		w.Header().Set("X-Frame-Options", "DENY")
		if strings.HasPrefix(r.URL.Path, "/demos/") && strings.HasSuffix(r.URL.Path, "/frame") {
			id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/demos/"), "/frame")
			if !known(id) {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("Content-Security-Policy", "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
			w.Header().Set("X-Frame-Options", "SAMEORIGIN")
			r.URL.Path = "/frame-" + id + ".html"
		} else if strings.HasPrefix(r.URL.Path, "/demos") {
			id := strings.TrimPrefix(r.URL.Path, "/demos/")
			if id == "workspace" {
				id = r.URL.Query().Get("product")
				if !known(id) {
					id = "console"
				}
				r.URL.Path = "/workspace-" + id + ".html"
			} else if known(id) {
				r.URL.Path = "/demo-" + id + ".html"
			} else {
				r.URL.Path = "/index.html"
			}
		}
		if r.URL.Path == "/catalog.json" {
			http.NotFound(w, r)
			return
		}
		files.ServeHTTP(w, r)
	})
	err = server.Serve(listener)
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
func menu() error {
	banner()
	fmt.Print("\nReal account sign-in. Fictional cloud examples.\n\n")
	for {
		fmt.Println("  1  Sign in\n  2  Account\n  3  Install demo package\n  4  Open browser demo\n  5  Explore terminal products\n  6  Stop browser demo\n  7  Sign out\n  0  Exit")
		fmt.Print("Choose › ")
		choice, err := input.ReadString('\n')
		if err != nil {
			return nil
		}
		choice = strings.TrimSpace(choice)
		switch choice {
		case "0":
			return nil
		case "1":
			err = login("https://nebulacoder.com")
		case "2":
			var c credentials
			c, err = readCredentials()
			if err == nil {
				var m map[string]any
				m, err = online(&c)
				if err == nil {
					fmt.Println("Signed in as " + str(m, "name") + " · " + str(m, "email"))
				}
			}
		case "3":
			err = demoInstall()
		case "4":
			err = startDemo()
		case "5":
			err = demoCommand([]string{"list"})
			if err == nil {
				fmt.Print("Product ID › ")
				p, _ := input.ReadString('\n')
				err = demoCommand([]string{strings.TrimSpace(p), "list"})
			}
		case "6":
			err = stopDemo()
		case "7":
			err = logout()
		default:
			fmt.Println("Choose a number above.")
		}
		if err != nil {
			fmt.Println("  " + err.Error())
		}
		fmt.Println()
	}
}
func main() {
	var err error
	args := os.Args[1:]
	if len(args) == 0 {
		err = interactive()
	} else {
		switch args[0] {
		case "tui":
			err = terminalUI()
		case "--version", "version":
			fmt.Println("KagNode CLI " + version)
		case "login":
			base := "https://nebulacoder.com"
			if len(args) == 3 && args[1] == "--server" {
				base = args[2]
			} else if len(args) != 1 {
				err = errors.New("usage: kagnode login [--server HTTPS_ORIGIN]")
				break
			}
			err = login(base)
		case "logout":
			err = logout()
		case "account":
			err = profileCommand(args[1:])
		case "whoami":
			var c credentials
			c, err = readCredentials()
			if err == nil {
				var m map[string]any
				m, err = online(&c)
				if err == nil {
					fmt.Printf("%s <%s>\n", str(m, "name"), str(m, "email"))
				}
			}
		case "setup":
			err = ecosystemSetup()
		case "apps":
			err = ecosystemCommand(args[1:])
		case "core":
			err = coreCommand(args[1:])
		case "demo":
			err = demoCommand(args[1:])
		case "help", "--help", "-h":
			fmt.Println("KagNode CLI " + version + "\n\n  kagnode                         Interactive terminal workspace\n  kagnode tui                     Open the keyboard TUI\n  kagnode setup                   Keyboard-only install and setup wizard\n  kagnode apps --help              Scriptable application manager\n  kagnode core --help              Signed shared UI manager\n  kagnode login [--server ORIGIN]  Browser device sign-in\n  kagnode whoami                   Check account online\n  kagnode account sync on|off      Choose profile synchronization\n  kagnode logout                   Revoke and clear credentials\n  kagnode demo install             Install all fictional examples\n  kagnode demo start|stop          Local browser examples\n  kagnode demo list|reset          Products or reset sample state\n  kagnode demo PRODUCT list|create NAME|delete ID|settings\n  kagnode demo ai prompt TEXT      Predefined sample response\n\nDemos work offline after first sign-in. No live infrastructure or billing.")
		default:
			err = errors.New("unknown command; run kagnode help")
		}
	}
	if errors.Is(err, errSetup) {
		err = ecosystemSetup()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "KagNode: "+err.Error())
		os.Exit(1)
	}
}
