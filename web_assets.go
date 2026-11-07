package main

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"mime"
	"net/http"
	"path"
	"strings"
	"time"
)

// Source remains in the repository; HTTP serves only the compiled page/asset set.
func builtDemoAssets(source fs.FS) http.Handler {
	manifestBytes, err := fs.ReadFile(source, "ui-manifest.json")
	if err != nil {
		panic("missing compiled demo manifest")
	}
	var manifest map[string]string
	if json.Unmarshal(manifestBytes, &manifest) != nil {
		panic("invalid demo asset manifest")
	}
	allowed := map[string]bool{"/favicon.svg": true, "/kagnode-wordmark.svg": true}
	for _, name := range manifest {
		allowed[name] = true
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if data, kind, ok := coreCachedAsset(r.URL.Path); ok && (r.Method == "GET" || r.Method == "HEAD") {
			w.Header().Set("Content-Type", kind)
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
			if r.Method != "HEAD" {
				_, _ = w.Write(data)
			}
			return
		}
		if r.Method != "GET" && r.Method != "HEAD" {
			w.Header().Set("Allow", "GET, HEAD")
			http.Error(w, "Method not allowed", 405)
			return
		}
		name := r.URL.Path
		if compiled, ok := manifest[name]; ok {
			name = compiled
		}
		if !allowed[name] {
			http.NotFound(w, r)
			return
		}
		content, err := fs.ReadFile(source, strings.TrimPrefix(name, "/"))
		if err != nil {
			http.NotFound(w, r)
			return
		}
		if strings.HasSuffix(name, ".html") {
			content = coreHTML(content)
		}
		if strings.HasPrefix(name, "/built/") && (strings.HasSuffix(name, ".css") || strings.HasSuffix(name, ".js")) {
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		}
		w.Header().Set("Content-Type", mime.TypeByExtension(path.Ext(name)))
		http.ServeContent(w, r, path.Base(name), time.Time{}, bytes.NewReader(content))
	})
}
