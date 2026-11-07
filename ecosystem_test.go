package main

import (
	"strings"
	"testing"
)

func TestSetupFramesRemainKeyboardOnlyAndFit(t *testing.T) {
	for _, size := range [][2]int{{24, 10}, {40, 12}, {80, 24}, {130, 40}} {
		for selected := range setupProjects {
			frame := setupFrame("Applications", setupProjects, selected, size[0], size[1])
			if strings.Contains(frame, "?1000h") || strings.Contains(frame, "?1006h") {
				t.Fatal("mouse enabled")
			}
			for _, row := range strings.Split(frame, "\r\n") {
				row = strings.NewReplacer("\x1b[H", "", "\x1b[2J", "", "\x1b[K", "").Replace(row)
				if tuiWidth(row) > size[0] {
					t.Fatalf("row overflow: %q", row)
				}
			}
		}
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
