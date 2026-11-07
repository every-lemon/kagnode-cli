package main

import (
	"regexp"
	"strings"
	"testing"
)

func TestSetupFramesRemainKeyboardOnlyAndFit(t *testing.T) {
	t.Setenv("TERM", "xterm-256color")
	ansi := regexp.MustCompile(`\x1b\[[0-9;]*[A-Za-z]`)
	for _, size := range [][2]int{{24, 10}, {40, 12}, {80, 24}, {130, 40}} {
		for selected := range setupProjects {
			frame := setupFrame("Applications", setupProjects, selected, size[0], size[1])
			if strings.Contains(frame, "?1000h") || strings.Contains(frame, "?1006h") {
				t.Fatal("mouse enabled")
			}
			for _, row := range strings.Split(frame, "\r\n") {
				row = ansi.ReplaceAllString(row, "")
				if tuiWidth(row) > size[0] {
					t.Fatalf("row overflow: %q", row)
				}
			}
		}
	}
}

func TestSetupRespectsNoColor(t *testing.T) {
	t.Setenv("TERM", "xterm-256color")
	t.Setenv("NO_COLOR", "1")
	frame := setupFrame("Applications", setupProjects, 0, 80, 24)
	if strings.Contains(frame, "38;5;") || strings.Contains(frame, "48;5;") {
		t.Fatal("color enabled despite NO_COLOR")
	}
}

func TestAppsRoutingDoesNotUseShell(t *testing.T) {
	args, err := tuiArguments("/apps check passwords --channel preview", "vps")
	if err != nil || strings.Join(args, " ") != "apps check passwords --channel preview" {
		t.Fatal(args, err)
	}
	if _, err = assets.ReadFile("assets/ecosystem.py"); err != nil {
		t.Fatal(err)
	}
}
