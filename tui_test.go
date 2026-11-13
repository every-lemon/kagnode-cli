package main

import (
	"strings"
	"testing"
	"unicode/utf8"
)

func TestTUICommandOutputIsBoundedWithoutLosingUTF8OrBytes(t *testing.T) {
	events := make(chan tuiEvent, 20)
	writer := tuiWriter{events: events}
	input := strings.Repeat("a", 4096) + strings.Repeat("學", 1800) + "END\n\nlast"
	if _, err := writer.Write([]byte(input)); err != nil {
		t.Fatal(err)
	}
	writer.flush()
	close(events)
	var output strings.Builder
	for event := range events {
		if !utf8.ValidString(event.line) {
			t.Fatal("split a UTF-8 character")
		}
		output.WriteString(event.line)
	}
	if output.String() != strings.ReplaceAll(input, "\n", "") {
		t.Fatal("command output lost bytes")
	}
}

func TestTUIOutputCannotInjectTerminalControls(t *testing.T) {
	got := tuiSafe("Caleb\x1b]52;c;payload\a\x00\u202ename")
	if strings.ContainsAny(got, "\x1b\a\x00\u202e") {
		t.Fatal("unsafe terminal controls retained")
	}
}
func TestTUICommandsAreRoutedWithoutShellExecution(t *testing.T) {
	args, e := tuiArguments("/status mail", "mail")
	if e != nil || strings.Join(args, " ") != "apps status mail" {
		t.Fatal(args, e)
	}
	if _, e = tuiArguments("/sh rm -rf something", "vps"); e == nil {
		t.Fatal("arbitrary command accepted")
	}
	args, e = tuiArguments("/login --server https://example.test", "vps")
	if e != nil || args[0] != "login" {
		t.Fatal(args, e)
	}
}
func TestTUIWrapPreservesWideAndCombiningCharacters(t *testing.T) {
	if tuiWidth("學校") != 4 || tuiWidth("e\u0301") != 1 {
		t.Fatal("incorrect display width")
	}
	for _, line := range tuiWrap("KagNode 學校 workspace", 8) {
		if tuiWidth(line) > 8 {
			t.Fatal(line)
		}
	}
}
func TestTUIRendersSmallTerminalsAndEditsHistory(t *testing.T) {
	m := tuiModel{account: "Signed out", product: "vps", input: "/help", cursor: 5, lines: []string{"Welcome"}, history: []string{"/products", "/whoami"}, historyAt: 2}
	for _, size := range [][2]int{{20, 8}, {40, 12}, {80, 24}, {140, 40}} {
		if !strings.Contains(tuiFrame(&m, size[0], size[1], false), "KagNode") {
			t.Fatal(size)
		}
	}
	m.historyMove(-1)
	if m.input != "/whoami" {
		t.Fatal(m.input)
	}
	m.input = "/cat"
	m.complete()
	if m.input != "/catalog " {
		t.Fatal(m.input)
	}
}
