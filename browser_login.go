package main

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

const profileClient = "kagnode-cli-profile"

func loginSecret() (string, error) {
	var raw [32]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw[:]), nil
}
func sameSecret(a, b string) bool {
	return len(a) == len(b) && subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

// Callback accepts only the original loopback listener, exact issuer and unique
// parameters. No credentials or authorization code are ever rendered or logged.
func callbackValues(r *http.Request, host, issuer, state string) (string, error) {
	if r.Method != "GET" || r.Host != host || r.URL.Path != "/auth/kagnode/callback" {
		return "", errors.New("invalid callback destination")
	}
	peer, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil || !net.ParseIP(peer).IsLoopback() {
		return "", errors.New("callback must be local")
	}
	values, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		return "", errors.New("invalid callback query")
	}
	for key, v := range values {
		if len(v) != 1 || (key != "state" && key != "iss" && key != "code" && key != "error") {
			return "", errors.New("unexpected callback parameter")
		}
	}
	if !sameSecret(values.Get("state"), state) || values.Get("iss") != issuer {
		return "", errors.New("callback issuer or state mismatch")
	}
	code, denied := values.Get("code"), values.Get("error")
	if denied != "" {
		if code != "" {
			return "", errors.New("ambiguous authorization response")
		}
		return "", errors.New("authorization was declined or expired; local applications remain available")
	}
	if code == "" || len(code) > 2048 {
		return "", errors.New("missing authorization code")
	}
	return code, nil
}
func validateLoginProof(m map[string]any, issuer, origin, nonce string, now int64) (string, error) {
	proof, ok := m["authorization"].(map[string]any)
	if !ok || str(proof, "issuer") != issuer || str(proof, "client_id") != profileClient || str(proof, "installation") != origin || str(proof, "purpose") != "sign_in" || !sameSecret(str(proof, "nonce"), nonce) || str(proof, "subject") == "" || num(proof, "expires_at") <= now || num(proof, "issued_at") > now+30 || now-num(proof, "issued_at") > 120 || num(proof, "approved_at") <= 0 || num(proof, "approved_at") > now+30 || now-num(proof, "approved_at") > 120 || num(proof, "expires_at") > num(proof, "approved_at")+120 || num(proof, "auth_time") <= 0 || num(proof, "auth_time") > num(proof, "issued_at")+30 {
		return "", errors.New("invalid fresh account authorization proof")
	}
	return str(proof, "subject"), nil
}
func login(base string) error {
	return browserLogin(base, func(target string) error {
		child := exec.Command("xdg-open", target)
		if err := child.Start(); err != nil {
			return err
		}
		go func() { _ = child.Wait() }()
		return nil
	})
}
func browserLogin(base string, open func(string) error) error {
	base, err := validBase(base)
	if err != nil {
		return err
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return err
	}
	defer listener.Close()
	origin := "http://" + listener.Addr().String()
	redirect := origin + "/auth/kagnode/callback"
	state, err := loginSecret()
	if err != nil {
		return err
	}
	verifier, err := loginSecret()
	if err != nil {
		return err
	}
	nonce, err := loginSecret()
	if err != nil {
		return err
	}
	hash := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(hash[:])
	m, status, err := requestJSON(base, "/api/v1/account-sync/browser/start", "", map[string]string{"client_id": profileClient, "installation": origin, "redirect_uri": redirect, "scope": "profile.read email.read", "purpose": "sign_in", "nonce": nonce, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
	if err != nil {
		return err
	}
	if status != 200 {
		return fmt.Errorf("browser authorization unavailable (%d); use login --headless when needed", status)
	}
	requestID, authorization := str(m, "request_id"), str(m, "authorization_uri")
	target, e := url.Parse(authorization)
	expected, _ := url.Parse(base)
	if e != nil || target.Scheme != expected.Scheme || target.Host != expected.Host || target.Path != "/oauth/authorize" || target.User != nil || target.Fragment != "" || len(target.Query()) != 1 || target.Query().Get("request") != requestID || requestID == "" {
		return errors.New("invalid authorization destination")
	}
	defer func() {
		_, _, _ = requestJSON(base, "/api/v1/account-sync/browser/cancel", "", map[string]string{"client_id": profileClient, "request_id": requestID, "code_verifier": verifier})
	}()
	type outcome struct {
		code string
		err  error
	}
	results := make(chan outcome, 1)
	var mu sync.Mutex
	used := false
	expires := num(m, "expires_in")
	if expires <= 0 || expires > 600 {
		return errors.New("invalid authorization deadline")
	}
	deadline := time.Now().Add(time.Duration(expires) * time.Second)
	server := &http.Server{ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second, MaxHeaderBytes: 8192}
	server.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
		code, check := callbackValues(r, listener.Addr().String(), base, state)
		// Ignore unrelated/forged requests without consuming the legitimate attempt.
		if check != nil && (r.URL.Query().Get("state") != state || r.URL.Query().Get("iss") != base || r.URL.Query().Get("error") == "") {
			http.Error(w, "Authorization callback rejected.", 400)
			return
		}
		mu.Lock()
		defer mu.Unlock()
		if used || time.Now().After(deadline) {
			http.Error(w, "Authorization already completed or expired.", 409)
			return
		}
		used = true
		results <- outcome{code, check}
		fmt.Fprintln(w, "Return to the KagNode terminal to complete sign-in.")
	})
	go func() { _ = server.Serve(listener) }()
	defer server.Close()
	fmt.Println("Opening KagNode Account in your browser…")
	fmt.Println("Browser authorization: " + authorization)
	if err = open(authorization); err != nil {
		fmt.Println("Open this authorization address in a browser on this computer:")
		fmt.Println(authorization)
	}
	interrupts := make(chan os.Signal, 1)
	signal.Notify(interrupts, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(interrupts)
	timer := time.NewTimer(time.Until(deadline))
	defer timer.Stop()
	var result outcome
	select {
	case result = <-results:
	case <-interrupts:
		return errors.New("browser authorization cancelled; local applications remain available")
	case <-timer.C:
		return errors.New("browser authorization expired; run kagnode login again")
	}
	if result.err != nil {
		return result.err
	}
	m, status, err = requestJSON(base, "/api/v1/account-sync/token", "", map[string]string{"client_id": profileClient, "grant_type": "authorization_code", "code": result.code, "redirect_uri": redirect, "code_verifier": verifier})
	if err != nil {
		return err
	}
	if status != 200 {
		return fmt.Errorf("authorization exchange failed (%d); start a new sign-in", status)
	}
	subject, err := validateLoginProof(m, base, origin, nonce, time.Now().Unix())
	if err != nil {
		return err
	}
	if str(m, "access_token") == "" || str(m, "refresh_token") == "" || num(m, "expires_in") <= 0 {
		return errors.New("invalid token response")
	}
	c := credentials{Protocol: "account-sync", Base: base, Access: str(m, "access_token"), Refresh: str(m, "refresh_token"), ID: subject, Expires: time.Now().Unix() + num(m, "expires_in")}
	profile, code, err := requestJSON(base, "/api/v1/account-sync/profile?client_id="+profileClient, c.Access, nil)
	if err != nil {
		return err
	}
	if code != 200 || str(profile, "subject") != subject {
		return errors.New("authorized account profile did not match")
	}
	if profileSyncEnabled() {
		c.Name = str(profile, "name")
		photo := str(profile, "photo")
		if len(photo) <= 180000 && (photo == "" || profilePhotoPattern.MatchString(photo)) {
			c.Photo = photo
		}
		c.ProfileUpdated = time.Now().Unix()
	}
	if err = saveSignIn(c); err != nil {
		return err
	}
	fmt.Println("Signed in to KagNode Account.")
	return nil
}
