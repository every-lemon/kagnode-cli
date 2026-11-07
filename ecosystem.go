// Keyboard-only application setup. Privileged work stays in the local manager.
package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"unsafe"
)

var errSetup = errors.New("open ecosystem setup")
var errSetupExit = errors.New("close ecosystem setup")

func ecosystemCommand(args []string) error { return managerCommand("ecosystem.py", args) }
func coreCommand(args []string) error      { return managerCommand("core_manager.py", args) }
func managerCommand(module string, args []string) error {
	source, err := assets.ReadFile("assets/" + module)
	if err != nil {
		return err
	}
	directory, err := os.MkdirTemp("", "kagnode-manager-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(directory)
	file := directory + "/" + module
	if err = os.WriteFile(file, source, 0600); err != nil {
		return err
	}
	migration, err := assets.ReadFile("assets/consolidate.py")
	if err != nil {
		return err
	}
	if err = os.WriteFile(directory+"/consolidate.py", migration, 0600); err != nil {
		return err
	}
	command := exec.Command("python3", append([]string{file}, args...)...)
	command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err = command.Start(); err != nil {
		return err
	}
	signals := make(chan os.Signal, 2)
	done := make(chan struct{})
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signals)
	defer close(done)
	go func() {
		for {
			select {
			case sig := <-signals:
				_ = command.Process.Signal(sig)
			case <-done:
				return
			}
		}
	}()
	return command.Wait()
}

type setupChoice struct{ id, name, detail string }

var setupProjects = []setupChoice{
	{"passwords", "Passwords", "Encrypted web vault · Bitwarden engine setup available"},
	{"mail", "Mail", "Mail server · native provisioning needs its network settings"},
	{"vpn", "VPN", "VPN server · native updates retain signature verification"},
	{"httpboot", "HTTP Boot", "Boot server · image and device updates stay separate"},
	{"media", "Media", "Media library · preview; processing must be configured"},
	{"logos", "Logos", "Artwork and downloadable gallery"},
	{"cli", "CLI", "Terminal workspace and ecosystem manager"},
}

func setupFrame(title string, choices []setupChoice, selected, width, height int) string {
	width = max(16, width)
	height = max(8, height)
	var b strings.Builder
	_, noColor := os.LookupEnv("NO_COLOR")
	color := !noColor && os.Getenv("TERM") != "" && os.Getenv("TERM") != "dumb"
	row := func(text, style string) {
		text = tuiClip(text, width-2)
		if color && style != "" {
			b.WriteString("\x1b[" + style + "m" + text + "\x1b[0m")
		} else {
			b.WriteString(text)
		}
		b.WriteString("\x1b[K\r\n")
	}
	b.WriteString("\x1b[H\x1b[2J")
	row("KagNode.  /  Setup", "1;38;5;75")
	row("", "")
	row(title, "1")
	row("", "")
	visible := max(1, (height-7)/2)
	start := max(0, min(selected-visible/2, len(choices)-visible))
	for i := start; i < min(len(choices), start+visible); i++ {
		prefix := "  "
		style := ""
		if i == selected {
			prefix = "› "
			style = "1;38;5;75;48;5;236"
		}
		row(prefix+choices[i].name, style)
		row("  "+choices[i].detail, "2")
	}
	row(fmt.Sprintf("%d / %d", selected+1, len(choices)), "2")
	row("↑/↓ choose · Enter continue · Esc back · Ctrl+C exit", "2")
	return b.String()
}

func setupSelect(title string, choices []setupChoice) (string, error) {
	if !tuiTerminal() {
		return "", fmt.Errorf("setup requires a terminal; use kagnode apps --help for scriptable operations")
	}
	var saved syscall.Termios
	fd := os.Stdin.Fd()
	_, _, e := syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCGETS, uintptr(unsafe.Pointer(&saved)))
	if e != 0 {
		return "", e
	}
	raw := saved
	raw.Lflag &^= syscall.ICANON | syscall.ECHO | syscall.ISIG
	raw.Iflag &^= syscall.ICRNL | syscall.IXON
	raw.Cc[syscall.VMIN] = 0
	raw.Cc[syscall.VTIME] = 1
	_, _, e = syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCSETS, uintptr(unsafe.Pointer(&raw)))
	if e != 0 {
		return "", e
	}
	defer func() {
		syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCSETS, uintptr(unsafe.Pointer(&saved)))
		fmt.Print("\x1b[?25h\x1b[?1049l")
	}()
	fmt.Print("\x1b[?1049h\x1b[?25l")
	termination := make(chan os.Signal, 1)
	signal.Notify(termination, syscall.SIGTERM)
	defer signal.Stop(termination)
	selected := 0
	key := make([]byte, 1)
	escape := ""
	lastFrame := ""
	for {
		select {
		case <-termination:
			return "", errSetupExit
		default:
		}
		w, h := tuiDimensions()
		frame := setupFrame(title, choices, selected, w, h)
		if frame != lastFrame {
			fmt.Print(frame)
			lastFrame = frame
		}
		n, err := syscall.Read(int(fd), key)
		if err != nil {
			return "", err
		}
		if n == 0 {
			if escape == "\x1b" {
				return "", nil
			}
			continue
		}
		c := key[0]
		if escape != "" {
			escape += string(c)
			if escape == "\x1b[" {
				continue
			}
			if escape == "\x1b[A" {
				selected = (selected + len(choices) - 1) % len(choices)
			}
			if escape == "\x1b[B" {
				selected = (selected + 1) % len(choices)
			}
			// Consume mouse reports but never enable or act on mouse input.
			if strings.HasPrefix(escape, "\x1b[<") && len(escape) < 40 && c != 'M' && c != 'm' {
				continue
			}
			escape = ""
			continue
		}
		switch c {
		case 3, 4:
			return "", errSetupExit
		case 27:
			escape = "\x1b"
		case 9, 'j':
			selected = (selected + 1) % len(choices)
		case 'k':
			selected = (selected + len(choices) - 1) % len(choices)
		case 10, 13:
			return choices[selected].id, nil
		}
	}
}

func setupPrompt(label, fallback string) (string, error) {
	fmt.Printf("%s", label)
	if fallback != "" {
		fmt.Printf(" [%s]", fallback)
	}
	fmt.Print(": ")
	value, err := bufio.NewReader(os.Stdin).ReadString('\n')
	if err != nil {
		return "", err
	}
	value = strings.TrimSpace(value)
	if value == "" {
		value = fallback
	}
	if value != tuiSafe(value) || len(value) > 1024 {
		return "", fmt.Errorf("invalid input")
	}
	return value, nil
}

func setupExecute(args, followup []string, run func([]string) error) error {
	if err := run(args); err != nil {
		return err
	}
	if len(followup) != 0 {
		return run(followup)
	}
	return nil
}

func ecosystemSetup() (result error) {
	defer func() {
		if errors.Is(result, errSetupExit) || errors.Is(result, io.EOF) {
			result = nil
		}
	}()
	for {
		project, err := setupSelect("Choose an application", setupProjects)
		if err != nil || project == "" {
			return err
		}
		choices := []setupChoice{{"check", "Check releases", "Read GitHub release information; no installation changes"}, {"install", "Install or update", "Verify source archive and retain previous release/data"}, {"setup", "Configure web service", "Set HTTPS address and local port after installation"}, {"status", "Installation status", "Show files, channel and the last operation"}}
		if project == "cli" {
			choices[2] = setupChoice{"activate-cli", "Activate managed CLI", "Add /usr/local/bin/kagnode without replacing existing executables"}
		}
		if project == "passwords" || project == "media" || project == "logos" || project == "cli" {
			choices = append([]setupChoice{{"guided", "Install and set up", "Choose your settings, then install and activate in one workflow"}}, choices...)
		}
		if project == "mail" || project == "vpn" || project == "httpboot" {
			choices = append(choices, setupChoice{"bind-native", "Connect an existing installation", "Recognize this app's native paths and enable its guarded updater"}, setupChoice{"consolidate", "Consolidate application files", "Preview a move with retained originals and compatibility paths"})
		}
		if project != "logos" && project != "cli" {
			choices = append(choices, setupChoice{"enable-panel", "Enable administration updates", "Authorize the local service account to use its update socket"})
		}
		if project == "passwords" {
			choices = append(choices, setupChoice{"bitwarden", "Bitwarden apps & extensions", "Install the separate Vaultwarden engine with a pinned image"})
		}
		projectName := project
		for _, choice := range setupProjects {
			if choice.id == project {
				projectName = choice.name
			}
		}
		action, err := setupSelect("KagNode "+projectName, choices)
		if err != nil {
			return err
		}
		if action == "" {
			continue
		}
		actionName := action
		for _, choice := range choices {
			if choice.id == action {
				actionName = choice.name
			}
		}
		root, err := setupPrompt("Application root", "/srv/kagnode")
		if err != nil {
			return err
		}
		args := []string{"--root", root, action, project}
		var followup []string
		if action == "guided" {
			args = []string{"--root", root, "install", project}
			if project == "cli" {
				followup = []string{"--root", root, "activate-cli"}
			}
		}
		if action == "activate-cli" {
			args = []string{"--root", root, action}
		}
		if action == "check" || action == "install" || action == "bind-native" || action == "guided" {
			channel, err := setupSelect("Release channel", []setupChoice{{"stable", "Stable", "Published stable releases with compatible manifests"}, {"preview", "Preview", "Explicitly include prereleases and packaging previews"}})
			if err != nil {
				return err
			}
			if channel == "" {
				continue
			}
			args = append(args, "--channel", channel)
		}
		if action == "enable-panel" {
			username, err := setupPrompt("Local account running this web service", "kn-"+project)
			if err != nil {
				return err
			}
			args = append(args, "--user", username)
		}
		if action == "consolidate" {
			if err := ecosystemCommand(args); err != nil {
				return err
			}
			choice, err := setupSelect("Consolidate "+project+" after reviewing these paths", []setupChoice{{"back", "Back", "Preview only; keep existing paths"}, {"apply", "Apply migration", "Requires stopped services; retain originals and verify every copied file"}})
			if err != nil {
				return err
			}
			if choice != "apply" {
				continue
			}
			args = append(args, "--apply")
		}
		if action == "setup" || action == "bitwarden" || (action == "guided" && project != "cli") {
			origin, err := setupPrompt("HTTPS address (for example https://app.example.com)", "")
			if err != nil {
				return err
			}
			if action == "guided" {
				followup = []string{"--root", root, "setup", project, "--origin", origin}
			} else {
				args = append(args, "--origin", origin)
			}
			if action == "bitwarden" {
				image, err := setupPrompt("Pinned image (leave empty to resolve the latest stable Vaultwarden release)", "")
				if err != nil {
					return err
				}
				args = []string{"--root", root, "bitwarden", "--origin", origin, "--apply"}
				if image != "" {
					args = append(args, "--image", image)
				}
			}
		}
		if action != "check" && action != "status" {
			if os.Geteuid() != 0 {
				fmt.Println("Run sudo kagnode setup to install or configure applications.")
				continue
			}
			ok, err := setupSelect("Review: "+actionName+" · "+projectName+" in "+root, []setupChoice{{"back", "Back", "Keep the installation unchanged"}, {"apply", "Continue", "Apply this operation; preserve existing vaults and user data"}})
			if err != nil {
				return err
			}
			if ok != "apply" {
				continue
			}
		}
		fmt.Println("KagNode. / " + projectName + " / " + actionName)
		if err = setupExecute(args, followup, ecosystemCommand); err != nil {
			fmt.Println("Operation failed. Inspect the message above before retrying.")
		}
		if _, err = setupPrompt("Press Enter to return to setup", ""); err != nil {
			return err
		}
	}
}
