package main

import (
	"io/fs"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestBuiltDemoDelivery(t *testing.T) {
	source, _ := fs.Sub(assets, "assets")
	handler := builtDemoAssets(source)
	for _, name := range []string{"/catalog.json", "/ui-manifest.json", "/built/", "/style.css.map", "/../main.go"} {
		r := httptest.NewRecorder()
		handler.ServeHTTP(r, httptest.NewRequest("GET", name, nil))
		if r.Code != 404 {
			t.Fatalf("exposed %s: %d", name, r.Code)
		}
	}
	r := httptest.NewRecorder()
	handler.ServeHTTP(r, httptest.NewRequest("GET", "/workspace-vps.html", nil))
	if r.Code != 200 || !strings.Contains(r.Body.String(), "/built/kagnode-ui.") || !strings.Contains(r.Body.String(), "kn-ui") {
		t.Fatal("missing compiled shared UI")
	}
	css := httptest.NewRecorder()
	handler.ServeHTTP(css, httptest.NewRequest("GET", "/kagnode-ui.css", nil))
	if css.Code != 200 || !strings.Contains(css.Header().Get("Cache-Control"), "immutable") {
		t.Fatal("source alias not compiled")
	}
	r = httptest.NewRecorder()
	handler.ServeHTTP(r, httptest.NewRequest("POST", "/style.css", nil))
	if r.Code != 405 {
		t.Fatal("asset accepted mutation")
	}
}
