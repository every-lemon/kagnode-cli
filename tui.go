// KagNode terminal workspace. Account operations are real; cloud examples are fictional.
package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode"
	"unicode/utf8"
	"unsafe"
)

type tuiEvent struct {
	key    rune
	line   string
	output bool
	done   bool
	err    error
}
type tuiModel struct {
	lines     []string
	input     string
	cursor    int
	history   []string
	historyAt int
	product   string
	busy      bool
	account   string
	frame     int
	scroll    int
}

var tuiCommands = []string{"/setup", "/apps", "/core", "/help", "/login", "/whoami", "/logout", "/catalog", "/select", "/status", "/check", "/clear", "/quit"}

// Remote display names and command output must never become terminal control sequences.
func tuiSafe(value string) string {
	return strings.Map(func(r rune) rune {
		if r == '\n' || r == '\t' {
			return r
		}
		if unicode.IsControl(r) || (r >= 0x202a && r <= 0x202e) || (r >= 0x2066 && r <= 0x2069) {
			return -1
		}
		return r
	}, value)
}
func tuiRuneWidth(r rune) int {
	if unicode.Is(unicode.Mn, r) || unicode.Is(unicode.Me, r) {
		return 0
	}
	if r >= 0x1100 && (r <= 0x115f || r == 0x2329 || r == 0x232a || (r >= 0x2e80 && r <= 0xa4cf) || (r >= 0xac00 && r <= 0xd7a3) || (r >= 0xf900 && r <= 0xfaff) || (r >= 0xfe10 && r <= 0xfe6f) || (r >= 0xff00 && r <= 0xff60) || (r >= 0x1f300 && r <= 0x1faff) || (r >= 0x20000 && r <= 0x3fffd)) {
		return 2
	}
	return 1
}
func tuiWidth(s string) int {
	n := 0
	for _, r := range s {
		n += tuiRuneWidth(r)
	}
	return n
}
func tuiClip(s string, width int) string {
	if width <= 0 {
		return ""
	}
	var b strings.Builder
	n := 0
	for _, r := range tuiSafe(strings.ReplaceAll(s, "\t", "  ")) {
		if r == '\n' {
			break
		}
		w := tuiRuneWidth(r)
		if n+w > width {
			break
		}
		b.WriteRune(r)
		n += w
	}
	return b.String()
}
func tuiPad(s string, width int) string {
	s = tuiClip(s, width)
	return s + strings.Repeat(" ", max(0, width-tuiWidth(s)))
}
func tuiWrap(s string, width int) []string {
	if width < 1 {
		return nil
	}
	var result []string
	for _, line := range strings.Split(tuiSafe(s), "\n") {
		var b strings.Builder
		n := 0
		for _, r := range strings.ReplaceAll(line, "\t", "  ") {
			w := tuiRuneWidth(r)
			if n+w > width {
				result = append(result, b.String())
				b.Reset()
				n = 0
			}
			b.WriteRune(r)
			n += w
		}
		result = append(result, b.String())
	}
	return result
}
func tuiDimensions() (int, int) {
	var size struct{ rows, cols, x, y uint16 }
	_, _, err := syscall.Syscall(syscall.SYS_IOCTL, os.Stdout.Fd(), syscall.TIOCGWINSZ, uintptr(unsafe.Pointer(&size)))
	if err != 0 || size.cols == 0 || size.rows == 0 {
		return 80, 24
	}
	return int(size.cols), int(size.rows)
}
func tuiTerminal() bool {
	var state syscall.Termios
	_, _, err := syscall.Syscall(syscall.SYS_IOCTL, os.Stdin.Fd(), syscall.TCGETS, uintptr(unsafe.Pointer(&state)))
	_, out := terminalSize()
	return err == 0 && out && os.Getenv("TERM") != "dumb"
}
func (m *tuiModel) add(text string) {
	m.lines = append(m.lines, tuiSafe(text))
	if len(m.lines) > 400 {
		m.lines = m.lines[len(m.lines)-400:]
	}
}
func (m *tuiModel) identity() {
	m.account = "Not signed in"
	if c, err := readCredentials(); err == nil {
		if !profileSyncEnabled() {
			m.account = "KagNode Account"
			return
		}
		m.account = tuiSafe(c.Name)
		if m.account == "" {
			m.account = "KagNode account"
		}
	}
}
func (m *tuiModel) help() {
	m.add("/setup             Reviewed application setup wizard\n/catalog           Real application catalog\n/select APP        Select an application\n/status [APP]      Inspect installed state\n/check [APP]       Check published releases\n/apps --help       All scriptable application operations\n/core --help       Signed UI management\n/login             Browser authorization with PKCE\n/login --headless  Explicit device-code fallback\n/whoami            Refresh your account\n/logout            Revoke credentials\n/clear             Clear screen history\n/quit              Exit\n\nNo service is provisioned without reviewing its project-owned installer plan.")
}
func tuiArguments(command, product string) ([]string, error) {
	parts := strings.Fields(command)
	if len(parts) == 0 {
		return nil, nil
	}
	name := strings.TrimPrefix(parts[0], "/")
	switch name {
	case "login", "logout", "whoami", "apps", "core":
		return append([]string{name}, parts[1:]...), nil
	case "demo", "products", "use", "list", "create", "delete":
		return nil, fmt.Errorf("fictional example commands were retired; existing data remains. Use /setup or /catalog for real applications")
	case "catalog":
		if len(parts) != 1 {
			return nil, fmt.Errorf("use /catalog")
		}
		return []string{"apps", "list"}, nil
	case "status", "check":
		if len(parts) > 2 {
			return nil, fmt.Errorf("use /%s [APP]", name)
		}
		app := product
		if len(parts) == 2 {
			app = parts[1]
		}
		if app == "core" {
			return nil, fmt.Errorf("use /core %s APP for a bound application; Core is managed separately from application source", name)
		}
		return []string{"apps", name, app}, nil
	default:
		return nil, fmt.Errorf("unknown command; use /help")
	}
}
func (m *tuiModel) complete() {
	if !strings.HasPrefix(m.input, "/") {
		return
	}
	matches := []string{}
	for _, command := range tuiCommands {
		if strings.HasPrefix(command, m.input) {
			matches = append(matches, command)
		}
	}
	if len(matches) == 1 {
		m.input = matches[0] + " "
		m.cursor = len([]rune(m.input))
	}
}
func (m *tuiModel) historyMove(delta int) {
	if len(m.history) == 0 {
		return
	}
	m.historyAt = max(0, min(len(m.history), m.historyAt+delta))
	m.input = ""
	if m.historyAt < len(m.history) {
		m.input = m.history[m.historyAt]
	}
	m.cursor = len([]rune(m.input))
}

func tuiFrame(m *tuiModel, width, height int, color bool) string {
	width = max(8, width)
	height = max(6, height)
	blue := func(s string) string {
		if color {
			return "\x1b[94m" + s + "\x1b[0m"
		}
		return s
	}
	var b strings.Builder
	b.WriteString("\x1b[?25l\x1b[H")
	row := func(text string) { b.WriteString(text); b.WriteString("\x1b[K\r\n") }
	row(blue(tuiClip("KagNode. CLI  "+version, width)))
	status := m.account + "  ·  Applications"
	if m.busy {
		spinner := []string{"◐", "◓", "◑", "◒"}
		status = spinner[m.frame%4] + " Running command · Ctrl+C cancels"
	}
	row(tuiClip(status, width))
	row(tuiClip(strings.Repeat("─", width), width))
	side := 0
	if width >= 104 {
		side = 24
	}
	bodyWidth := width - side
	if side > 0 {
		bodyWidth -= 3
	}
	lines := []string{}
	for _, line := range m.lines {
		lines = append(lines, tuiWrap(line, bodyWidth)...)
	}
	visible := max(0, height-6)
	end := len(lines) - min(m.scroll, max(0, len(lines)-visible))
	lines = lines[max(0, end-visible):end]
	for i := 0; i < visible; i++ {
		text := ""
		if i < len(lines) {
			text = lines[i]
		}
		if side > 0 {
			label := ""
			if i == 0 {
				label = "APPLICATIONS"
			} else if i <= len(applicationIDs) {
				id := applicationIDs[i-1]
				label = "  " + id
				if id == m.product {
					label = "› " + id
				}
			}
			row(blue(tuiPad(label, side)) + " │ " + tuiClip(text, bodyWidth))
		} else {
			row(tuiClip(text, bodyWidth))
		}
	}
	hint := "Type /help to see commands"
	if m.scroll > 0 {
		hint = "Scrollback · PgDn returns to latest output"
	}
	if strings.HasPrefix(m.input, "/") {
		var options []string
		for _, c := range tuiCommands {
			if strings.HasPrefix(c, m.input) {
				options = append(options, c)
			}
		}
		if len(options) > 0 {
			hint = strings.Join(options, "  ")
		}
	}
	row(tuiClip(hint, width))
	runes := []rune(m.input)
	cursor := max(0, min(m.cursor, len(runes)))
	start := 0
	for tuiWidth(string(runes[start:cursor])) > width-5 && start < cursor {
		start++
	}
	prompt := tuiClip(string(runes[start:]), width-3)
	row(blue("› ") + prompt)
	b.WriteString(tuiClip("Enter run · ↑/↓ history · PgUp/PgDn scroll · Ctrl+C exit", width))
	b.WriteString("\x1b[K")
	b.WriteString(fmt.Sprintf("\x1b[%d;%dH\x1b[?25h", height-1, min(width, 3+tuiWidth(string(runes[start:cursor])))))
	return b.String()
}

type tuiWriter struct {
	mu      sync.Mutex
	pending string
	events  chan<- tuiEvent
}

func (w *tuiWriter) Write(data []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.pending += string(data)
	for {
		index := strings.IndexByte(w.pending, '\n')
		if index < 0 && len(w.pending) < 4096 {
			break
		}
		advance := index + 1
		if index < 0 || index > 4096 {
			index = 4096
			for index > 0 && index < len(w.pending) && !utf8.RuneStart(w.pending[index]) {
				index--
			}
			if index == len(w.pending) {
				start := index - 1
				for start > 0 && !utf8.RuneStart(w.pending[start]) {
					start--
				}
				if !utf8.FullRuneInString(w.pending[start:index]) {
					index = start
				}
			}
			advance = index
		}
		w.events <- tuiEvent{line: w.pending[:index], output: true}
		w.pending = w.pending[advance:]
	}
	return len(data), nil
}
func (w *tuiWriter) flush() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.pending != "" {
		w.events <- tuiEvent{line: w.pending, output: true}
		w.pending = ""
	}
}

func interactive() error {
	if !tuiTerminal() {
		fmt.Println("Run kagnode help for scriptable commands or kagnode setup for guided setup.")
		return nil
	}
	return terminalUI()
}
func terminalUI() error {
	if !tuiTerminal() {
		return fmt.Errorf("the TUI needs an interactive terminal; use kagnode help for scriptable commands")
	}
	var saved syscall.Termios
	fd := os.Stdin.Fd()
	_, _, err := syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCGETS, uintptr(unsafe.Pointer(&saved)))
	if err != 0 {
		return err
	}
	raw := saved
	raw.Lflag &^= syscall.ICANON | syscall.ECHO | syscall.ISIG | syscall.IEXTEN
	raw.Iflag &^= syscall.ICRNL | syscall.IXON
	raw.Cc[syscall.VMIN] = 1
	raw.Cc[syscall.VTIME] = 0
	if _, _, err = syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCSETS, uintptr(unsafe.Pointer(&raw))); err != 0 {
		return err
	}
	defer func() {
		syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCSETS, uintptr(unsafe.Pointer(&saved)))
		fmt.Print("\x1b[0m\x1b[?25h\x1b[?7h\x1b[?1049l")
	}()
	fmt.Print("\x1b[?1049h\x1b[?7l\x1b[2J")
	events := make(chan tuiEvent, 128)
	go func() {
		reader := bufio.NewReader(os.Stdin)
		for {
			r, _, e := reader.ReadRune()
			if e != nil {
				events <- tuiEvent{key: -1}
				return
			}
			events <- tuiEvent{key: r}
		}
	}()
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, syscall.SIGWINCH, syscall.SIGTERM, syscall.SIGHUP, os.Interrupt)
	defer signal.Stop(signals)
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	model := tuiModel{product: "passwords"}
	model.identity()
	model.add("Welcome to KagNode.\n\nSet up applications with /setup, inspect /apps list, or sign in with /login.\nManage local applications and your account. Review a real installer plan before changing this system.")
	var cancel context.CancelFunc
	defer func() {
		if cancel != nil {
			cancel()
		}
	}()
	escape := ""
	_, noColor := os.LookupEnv("NO_COLOR")
	dirty := true
	for {
		if dirty {
			w, h := tuiDimensions()
			fmt.Print(tuiFrame(&model, w, h, !noColor))
			dirty = false
		}
		select {
		case sig := <-signals:
			if sig != syscall.SIGWINCH {
				return nil
			}
			dirty = true
		case <-ticker.C:
			if model.busy {
				model.frame++
				dirty = true
			}
		case event := <-events:
			dirty = true
			if event.done {
				model.busy = false
				cancel = nil
				if event.err != nil {
					model.add("Command stopped or failed: " + event.err.Error())
				}
				model.identity()
				continue
			}
			if event.output {
				model.add(event.line)
				continue
			}
			r := event.key
			if r == -1 {
				return nil
			}
			if escape != "" {
				escape += string(r)
				if escape == "\x1b[" {
					continue
				}
				if strings.HasPrefix(escape, "\x1b[") && r >= '0' && r <= '9' && len(escape) < 8 {
					continue
				}
				switch escape {
				case "\x1b[A":
					model.historyMove(-1)
				case "\x1b[B":
					model.historyMove(1)
				case "\x1b[C":
					model.cursor = min(model.cursor+1, len([]rune(model.input)))
				case "\x1b[D":
					model.cursor = max(0, model.cursor-1)
				case "\x1b[H", "\x1b[1~":
					model.cursor = 0
				case "\x1b[F", "\x1b[4~":
					model.cursor = len([]rune(model.input))
				case "\x1b[5~":
					_, h := tuiDimensions()
					model.scroll += max(1, h-6)
				case "\x1b[6~":
					_, h := tuiDimensions()
					model.scroll = max(0, model.scroll-max(1, h-6))
				case "\x1b[3~":
					runes := []rune(model.input)
					if model.cursor < len(runes) {
						model.input = string(append(runes[:model.cursor], runes[model.cursor+1:]...))
					}
				}
				escape = ""
				continue
			}
			if r == 27 {
				escape = "\x1b"
				continue
			}
			switch r {
			case 3:
				if model.busy && cancel != nil {
					cancel()
					model.add("Cancelling command…")
				} else if model.input != "" {
					model.input = ""
					model.cursor = 0
				} else {
					return nil
				}
			case 4:
				if model.input == "" && !model.busy {
					return nil
				}
			case 21:
				model.input = ""
				model.cursor = 0
			case 12:
				fmt.Print("\x1b[2J")
			case 9:
				model.complete()
			case 127, 8:
				if model.cursor > 0 {
					runes := []rune(model.input)
					model.input = string(append(runes[:model.cursor-1], runes[model.cursor:]...))
					model.cursor--
				}
			case 10, 13:
				if model.busy {
					continue
				}
				command := strings.TrimSpace(model.input)
				if command == "" {
					continue
				}
				model.input = ""
				model.cursor = 0
				model.scroll = 0
				model.history = append(model.history, command)
				if len(model.history) > 100 {
					model.history = model.history[1:]
				}
				model.historyAt = len(model.history)
				model.add("› " + command)
				fields := strings.Fields(command)
				name := strings.TrimPrefix(fields[0], "/")
				switch name {
				case "setup":
					return errSetup
				case "quit", "exit":
					return nil
				case "help":
					model.help()
					continue
				case "select":
					found := false
					if len(fields) == 2 {
						for _, app := range setupProjects {
							if app.id == fields[1] {
								model.product = app.id
								model.add("Selected " + app.name + ". Use /status, /check or /setup.")
								found = true
								break
							}
						}
					}
					if !found {
						model.add("Use /select APP with an application from /catalog.")
					}
					continue
				case "catalog":
					rows := []string{"Application catalog:"}
					for _, app := range setupProjects {
						rows = append(rows, app.id+"  "+app.name)
					}
					model.add(strings.Join(rows, "\n"))
					continue
				case "clear":
					model.lines = nil
					continue

				}
				args, parseErr := tuiArguments(command, model.product)
				if (name == "status" || name == "check") && len(fields) == 2 {
					for _, app := range setupProjects {
						if app.id == fields[1] {
							model.product = app.id
							break
						}
					}
				}
				if parseErr != nil {
					model.add(parseErr.Error())
					continue
				}
				executable, e := os.Executable()
				if e != nil {
					model.add(e.Error())
					continue
				}
				ctx, stop := context.WithCancel(context.Background())
				cancel = stop
				model.busy = true
				go func(args []string) {
					writer := &tuiWriter{events: events}
					child := exec.CommandContext(ctx, executable, args...)
					child.Cancel = func() error { return child.Process.Signal(syscall.SIGTERM) }
					child.WaitDelay = 30 * time.Second
					child.Stdout = writer
					child.Stderr = writer
					runErr := child.Run()
					writer.flush()
					events <- tuiEvent{done: true, err: runErr}
				}(args)
			default:
				if !unicode.IsControl(r) && len([]rune(model.input)) < 2048 {
					runes := []rune(model.input)
					runes = append(runes, 0)
					copy(runes[model.cursor+1:], runes[model.cursor:])
					runes[model.cursor] = r
					model.cursor++
					model.input = string(runes)
				}
			}
		}
	}
}
