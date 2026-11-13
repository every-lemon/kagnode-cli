// KagNode CLI: real application management and authorized account sign-in.
package main

import (
	"bytes"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

//go:embed assets/*.txt assets/ecosystem.py assets/consolidate.py assets/core_manager.py assets/core-manager-manifest.json assets/installer.py assets/installer_protocol.py
var assets embed.FS

const version = "5.0.1"

var applicationIDs = []string{"passwords", "mail", "vpn", "httpboot", "media", "entropy", "logos", "cli", "core"}

type credentials struct {
	Protocol       string `json:"protocol,omitempty"`
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
	if err == nil {
		err = f.Sync()
	}
	if closeErr := f.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err = os.Rename(f.Name(), p); err != nil {
		return err
	}
	directory, err := os.Open(filepath.Dir(p))
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}
func readCredentials() (credentials, error) {
	var c credentials
	p := filepath.Join(pathFor("config"), "account.json")
	file, err := os.OpenFile(p, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return c, errors.New("sign in first with: kagnode login (credential file is unavailable or unsafe)")
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return c, err
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || !ok || owner.Uid != uint32(os.Geteuid()) || owner.Nlink != 1 || info.Size() > 1<<20 {
		return c, errors.New("account file must be a private single-link regular file owned by the current user (0600)")
	}
	raw, err := io.ReadAll(io.LimitReader(file, (1<<20)+1))
	if err != nil {
		return c, err
	}
	if len(raw) > 1<<20 {
		return c, errors.New("account file is too large")
	}
	if err = json.Unmarshal(raw, &c); err != nil {
		return c, err
	}
	if _, err = validBase(c.Base); err != nil {
		return c, err
	}
	if c.Protocol != "" && c.Protocol != "account-sync" {
		return c, errors.New("unknown credential protocol; sign in again")
	}
	return c, nil
}
func saveCredentials(c credentials) error {
	return writePrivate(filepath.Join(pathFor("config"), "account.json"), c)
}
func revokeCredential(c credentials) (bool, error) {
	route := "/api/cli/revoke"
	data := map[string]string{"token": c.Refresh}
	if c.Protocol == "account-sync" {
		route = "/api/v1/account-sync/revoke"
		data["client_id"] = profileClient
	}
	_, status, err := requestJSON(c.Base, route, "", data)
	return status == 204 && err == nil, err
}
func saveSignIn(c credentials) error {
	previous, previousError := readCredentials()
	if err := saveCredentials(c); err != nil {
		return err
	}
	if previousError == nil && previous.Refresh != "" && previous.Refresh != c.Refresh {
		if confirmed, _ := revokeCredential(previous); !confirmed {
			fmt.Println("Your new sign-in is saved. Previous authorization revocation was not confirmed; review connected devices in KagNode Account.")
		}
	}
	return nil
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

func deviceLogin(base string) error {
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
			if err = saveSignIn(c); err != nil {
				return err
			}
			fmt.Println("Signed in as " + c.Name + ".")
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
		route, client := "/api/cli/token", "kagnode-cli"
		if c.Protocol == "account-sync" {
			route, client = "/api/v1/account-sync/token", profileClient
		}
		m, status, err := requestJSON(c.Base, route, "", map[string]string{"client_id": client, "grant_type": "refresh_token", "refresh_token": c.Refresh})
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
	route := "/api/cli/me"
	if c.Protocol == "account-sync" {
		route = "/api/v1/account-sync/profile?client_id=" + profileClient
	}
	m, status, err := requestJSON(c.Base, route, c.Access, nil)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, errors.New("account access is unavailable; sign in again")
	}
	if c.Protocol == "account-sync" && str(m, "subject") != c.ID {
		return nil, errors.New("account subject changed; sign in again")
	}
	if err := cacheProfile(c, m); err != nil {
		return nil, err
	}
	return m, nil
}
func logout() error {
	c, err := readCredentials()
	if err == nil {
		confirmed, _ := revokeCredential(c)
		if !confirmed {
			fmt.Println("Online revocation was not confirmed. Revoke this device in your KagNode account when online.")
		}

	}
	if err = os.Remove(filepath.Join(pathFor("config"), "account.json")); err != nil && !os.IsNotExist(err) {
		return err
	}
	fmt.Println("Signed out. Local credentials removed. Existing application and legacy example data were retained.")
	return nil
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
			base, headless := "https://nebulacoder.com", false
			for i := 1; i < len(args); i++ {
				switch args[i] {
				case "--headless":
					headless = true
				case "--server":
					i++
					if i >= len(args) {
						err = errors.New("--server requires an origin")
					} else {
						base = args[i]
					}
				default:
					err = errors.New("usage: kagnode login [--headless] [--server ORIGIN]")
				}
			}
			if err == nil {
				if headless {
					err = deviceLogin(base)
				} else {
					err = login(base)
				}
			}
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
					fmt.Printf("%s <%s>\n", tuiSafe(str(m, "name")), tuiSafe(str(m, "email")))
				}
			}
		case "setup":
			err = ecosystemSetup()
		case "apps":
			err = ecosystemCommand(args[1:])
		case "core":
			err = coreCommand(args[1:])
		case "demo":
			err = errors.New("fictional demos were removed in 5.0.1; existing data was retained. Use kagnode setup to manage real applications")
		case "help", "--help", "-h":
			fmt.Println("KagNode CLI " + version + "\n\n  kagnode | tui                  Keyboard-only application workspace\n  kagnode setup                  Reviewed real application setup\n  kagnode apps --help            Scriptable installation/update manager\n  kagnode core --help            Verified shared UI manager\n  kagnode login                  Browser authorization with PKCE\n  kagnode login --headless       Explicit device-code fallback\n  kagnode whoami                 Check account online\n  kagnode account sync on|off    Control profile refresh\n  kagnode logout                 Revoke and clear credentials\n\nApplication setup requires an explicit reviewed plan. Native capabilities depend on each project and operating system.")
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
