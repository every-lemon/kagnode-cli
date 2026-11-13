// Keyboard-only application setup. Privileged work stays in the local manager.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"unsafe"
)

var setupRootPattern = regexp.MustCompile(`^/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$`)

var errSetup = errors.New("open ecosystem setup")
var errSetupExit = errors.New("close ecosystem setup")

func ecosystemCommand(args []string) error { return managerCommand("ecosystem.py", args) }
func coreCommand(args []string) error      { return managerCommand("core_manager.py", args) }
func managerCommand(module string, args []string) error {
	if _, err := exec.LookPath("python3"); err != nil {
		return fmt.Errorf("application and Core management require Python 3.10 or newer; install Python before retrying")
	}
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
	{"entropy", "Entropy", "Local OS-backed randomness service; supplemental research remains unassessed"},
	{"core", "Core", "Signed shared UI installation and reviewed baseline adoption"},
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
	var line strings.Builder
	var err error
	for {
		var one [1]byte
		_, err = io.ReadFull(os.Stdin, one[:])
		if err != nil {
			break
		}
		if one[0] == '\n' {
			break
		}
		line.WriteByte(one[0])
		if line.Len() > 1024 {
			return "", fmt.Errorf("input is too long")
		}
	}
	value := line.String()
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

// ecosystemSetup reviews the owning project's actual plan. The CLI never
// constructs native installer commands or infers a successful service setup.
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
		if project == "core" {
			fmt.Println("Use kagnode core --help. Core installation/adoption verifies signed manifests and requires explicit baseline review.")
			continue
		}
		action, err := setupSelect("Manage "+project, []setupChoice{{"plan", "Set up application", "Review the project-owned dependencies, configuration and native changes"}, {"install", "Download verified release", "Install application source; does not claim native setup"}, {"status", "Status", "Inspect installed release and recovery state"}, {"check", "Check releases", "Read published versions"}, {"recover", "Recover setup", "Re-run only an explicitly reviewed recovery plan"}})
		if err != nil {
			return err
		}
		if action == "" {
			continue
		}
		root, err := setupPrompt("Application workspace root", "/srv/kagnode")
		if err != nil {
			return err
		}
		base := []string{"--root", root}
		if action == "status" || action == "check" {
			if err = ecosystemCommand(append(base, action, project)); err != nil {
				fmt.Println(err)
			}
			continue
		}
		if action == "install" {
			ok, e := setupSelect("Download "+project+" under "+root, []setupChoice{{"back", "Back", "Keep files unchanged"}, {"apply", "Install verified source", "Preserve data; service setup is a separate reviewed operation"}})
			if e != nil {
				return e
			}
			if ok == "apply" {
				if e = ecosystemCommand(append(base, "install", project)); e != nil {
					fmt.Println(e)
				}
			}
			continue
		}
		if project == "cli" {
			fmt.Println("The CLI has no native service setup. Its PATH activation is available through apps activate-cli.")
			continue
		}
		if !setupRootPattern.MatchString(root) || filepath.Clean(root) != root {
			fmt.Println("Setup roots must use canonical absolute ASCII paths without spaces or controls.")
			continue
		}
		if os.Geteuid() != 0 {
			fmt.Println("Use sudo kagnode setup for system application setup. Account login remains unprivileged.")
			continue
		}

		if _, statErr := os.Lstat(filepath.Join(root, project, "current")); os.IsNotExist(statErr) {
			if e := ecosystemCommand(append(base, "check", project)); e != nil {
				fmt.Println(e)
				continue
			}
			raw, e := os.ReadFile(filepath.Join(root, project, "candidate.json"))
			if e != nil {
				fmt.Println("No checked release is available: " + e.Error())
				continue
			}
			var candidate struct {
				ID      int64  `json:"release_id"`
				Version string `json:"version"`
			}
			if json.Unmarshal(raw, &candidate) != nil || candidate.ID <= 0 {
				fmt.Println("No valid source release is available.")
				continue
			}
			choice, e := setupSelect("Prepare "+project+" "+candidate.Version, []setupChoice{{"back", "Back", "Keep this system unchanged"}, {"download", "Download this checked source release", "Verify its archive and retain it under the shared root; native setup is reviewed next"}})
			if e != nil {
				return e
			}
			if choice != "download" {
				continue
			}
			if e = ecosystemCommand(append(base, "install", project, "--release-id", strconv.FormatInt(candidate.ID, 10))); e != nil {
				fmt.Println(e)
				continue
			}
		}
		mode := "application"
		var e error
		if action != "recover" {
			mode, e = setupSelect("Installation target", []setupChoice{{"native", "Native installation", "Project-owned supported host setup; existing native data paths remain"}, {"application", "Application service", "Project-owned source/service setup"}, {"adopt", "Adopt existing", "Inspect and record an existing installation without relocating its data"}})
			if e != nil {
				return e
			}
			if mode == "" {
				continue
			}
		}

		directory, e := os.MkdirTemp("", "kagnode-review-")
		if e != nil {
			return e
		}
		e = func() error {
			defer os.RemoveAll(directory)
			config, plan := filepath.Join(directory, "configuration.json"), filepath.Join(directory, "review.json")
			if e := writePrivate(config, map[string]any{}); e != nil {
				return e
			}
			args := append(append([]string{}, base...), "plan", project, "--mode", mode, "--save-plan", plan)
			if action == "recover" {
				args = append(args, "--recover")
			} else {
				args = append(args, "--config", config)
			}
			if e := ecosystemCommand(args); e != nil {
				return e
			}
			raw, e := os.ReadFile(plan)
			if e != nil {
				return e
			}
			var review struct {
				Plan struct {
					Supported     bool           `json:"supported"`
					Configuration map[string]any `json:"configuration"`
					Fields        []struct {
						Key      string `json:"key"`
						Label    string `json:"label"`
						Type     string `json:"type"`
						Required bool   `json:"required"`
						Secret   bool   `json:"secret"`
						Default  any    `json:"default"`
					} `json:"configuration_fields"`
				} `json:"plan"`
			}
			if e = json.Unmarshal(raw, &review); e != nil {
				return e
			}
			if !review.Plan.Supported {
				return fmt.Errorf("this project does not support the selected platform/target; no setup was performed")
			}
			values := map[string]any{}
			for _, field := range review.Plan.Fields {
				label := field.Label
				if label == "" {
					label = field.Key
				}
				if field.Secret {
					label += " (private secret file path)"
				}
				fallback := ""
				if value, ok := review.Plan.Configuration[field.Key]; ok {
					fallback = fmt.Sprint(value)
				} else if field.Default != nil {
					fallback = fmt.Sprint(field.Default)
				}
				value, e := setupPrompt(label, fallback)
				if e != nil {
					return e
				}
				if value == "" && !field.Required {
					continue
				}
				if value == "" {
					return fmt.Errorf("%s is required", field.Key)
				}
				var typed any = value
				if field.Type == "integer" || field.Type == "number" {
					n, e := strconv.Atoi(value)
					if e != nil {
						return fmt.Errorf("%s needs a number", field.Key)
					}
					typed = n
				}
				if field.Type == "boolean" {
					b, e := strconv.ParseBool(value)
					if e != nil {
						return fmt.Errorf("%s needs true or false", field.Key)
					}
					typed = b
				}
				values[field.Key] = typed
			}
			if e = writePrivate(config, values); e != nil {
				return e
			}
			if e = os.Remove(plan); e != nil {
				return e
			}
			if action == "recover" {
				args = append(args, "--config", config)
			}
			if e = ecosystemCommand(args); e != nil {
				return e
			}
			acknowledgement, e := setupPrompt("Review the complete plan above. Type REVIEW to continue", "")
			if e != nil {
				return e
			}
			if acknowledgement != "REVIEW" {
				return nil
			}
			choice, e := setupSelect("Review the complete project plan above", []setupChoice{{"back", "Cancel", "No installation changes"}, {"apply", "Apply this exact plan", "Dependencies/configuration/service health must all succeed"}})
			if e != nil {
				return e
			}
			if choice != "apply" {
				return nil
			}
			operation := "apply"
			if action == "recover" {
				operation = "recover"
			}
			return ecosystemCommand(append(base, operation, project, "--plan", plan))
		}()
		if e != nil {
			fmt.Println("Setup stopped: " + e.Error())
		}
	}
}
