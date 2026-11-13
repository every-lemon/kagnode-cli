package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestLoopbackCallbackRejectsSpoofsAndDuplicates(t *testing.T) {
	good := "http://127.0.0.1:1234/auth/kagnode/callback?state=original&iss=https%3A%2F%2Fnebulacoder.com&code=once"
	for _, kind := range []string{"good", "host", "remote", "state", "issuer", "duplicate", "extra", "method", "both"} {
		r := httptest.NewRequest("GET", good, nil)
		r.RemoteAddr = "127.0.0.1:5555"
		switch kind {
		case "host":
			r.Host = "evil.test"
		case "remote":
			r.RemoteAddr = "192.168.0.9:2222"
		case "state":
			r.URL.RawQuery = strings.Replace(r.URL.RawQuery, "original", "other", 1)
		case "issuer":
			r.URL.RawQuery = strings.Replace(r.URL.RawQuery, "nebulacoder.com", "evil.test", 1)
		case "duplicate":
			r.URL.RawQuery += "&code=twice"
		case "extra":
			r.URL.RawQuery += "&access_token=secret"
		case "method":
			r.Method = "POST"
		case "both":
			r.URL.RawQuery += "&error=denied"
		}
		_, err := callbackValues(r, "127.0.0.1:1234", "https://nebulacoder.com", "original")
		if (err == nil) != (kind == "good") {
			t.Fatal(kind, err)
		}
	}
}
func TestBrowserLoginUsesPKCEAndPreservesLegacyUntilProof(t *testing.T) {
	for _, bad := range []bool{false, true} {
		t.Run(map[bool]string{false: "success", true: "wrong-subject"}[bad], func(t *testing.T) {
			testHome(t)
			legacy := credentials{Base: "https://nebulacoder.com", Access: "legacy", Refresh: "retain", ID: "old"}
			if err := saveCredentials(legacy); err != nil {
				t.Fatal(err)
			}
			var start map[string]any
			var issuer string
			exchanged := false
			cancelled := false
			revoked := false
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				switch r.URL.Path {
				case "/api/v1/account-sync/browser/start":
					json.NewDecoder(r.Body).Decode(&start)
					if str(start, "code_challenge_method") != "S256" || len(str(start, "code_challenge")) != 43 || str(start, "client_id") != profileClient {
						t.Error("invalid start")
					}
					json.NewEncoder(w).Encode(map[string]any{"request_id": "one", "authorization_uri": issuer + "/oauth/authorize?request=one", "expires_in": 600})
				case "/api/v1/account-sync/token":
					var exchange map[string]any
					json.NewDecoder(r.Body).Decode(&exchange)
					if str(exchange, "code_verifier") == "" || str(exchange, "redirect_uri") != str(start, "redirect_uri") || str(exchange, "code") != "code-one" {
						t.Error("invalid exchange")
					}
					exchanged = true
					now := time.Now().Unix()
					json.NewEncoder(w).Encode(map[string]any{"access_token": "access", "refresh_token": "refresh", "expires_in": 300, "authorization": map[string]any{"issuer": issuer, "subject": "new", "client_id": profileClient, "installation": str(start, "installation"), "purpose": "sign_in", "nonce": str(start, "nonce"), "issued_at": now, "approved_at": now, "auth_time": now, "expires_at": now + 120}})
				case "/api/v1/account-sync/profile":
					if r.URL.Query().Get("client_id") != profileClient || r.Header.Get("Authorization") != "Bearer access" {
						t.Error("profile not bound")
					}
					subject := "new"
					if bad {
						subject = "wrong"
					}
					json.NewEncoder(w).Encode(map[string]any{"subject": subject, "name": "New name"})
				case "/api/cli/revoke":
					revoked = true
					w.WriteHeader(204)
				case "/api/v1/account-sync/browser/cancel":
					cancelled = true
					json.NewEncoder(w).Encode(map[string]any{})
				default:
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			issuer = server.URL
			legacy.Base = issuer
			if err := saveCredentials(legacy); err != nil {
				t.Fatal(err)
			}
			err := browserLogin(issuer, func(destination string) error {
				if destination != issuer+"/oauth/authorize?request=one" {
					t.Error("bad URL")
				}
				go func() {
					u, _ := url.Parse(str(start, "redirect_uri"))
					q := u.Query()
					q.Set("iss", issuer)
					q.Set("state", str(start, "state"))
					q.Set("code", "code-one")
					u.RawQuery = q.Encode()
					res, e := http.Get(u.String())
					if e == nil {
						res.Body.Close()
					}
				}()
				return nil
			})
			if (err != nil) != bad {
				t.Fatal(err)
			}
			if revoked == bad {
				t.Fatal("previous grant revocation did not match committed sign-in")
			}
			if !exchanged || !cancelled {
				t.Fatal("incomplete exchange lifecycle")
			}
			saved, e := readCredentials()
			if e != nil {
				t.Fatal(e)
			}
			if bad && saved.ID != "old" {
				t.Fatal("legacy credentials overwritten before validated proof")
			}
			if !bad && (saved.ID != "new" || saved.Protocol != "account-sync") {
				t.Fatal("browser credentials not saved")
			}
			info, _ := os.Stat(filepath.Join(pathFor("config"), "account.json"))
			if info.Mode().Perm() != 0600 {
				t.Fatal("credentials exposed")
			}
		})
	}
}
