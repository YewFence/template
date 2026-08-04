package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	defaultRepositoryRawBase = "https://raw.githubusercontent.com/YewFence/go-cli-template"
	defaultRef               = "main"
)

var repositoryRawBase = defaultRepositoryRawBase

var newHTTPClient = func() *http.Client {
	return &http.Client{Timeout: 30 * time.Second}
}

var obsoleteTemplateFiles = []string{
	".github/workflows/actions-up.yml",
}

type config struct {
	ref string
}

type templateFile struct {
	path      string
	overwrite bool
	mode      os.FileMode
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "apply existing: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	config := parseFlags()
	if err := ensureCleanGitWorktree(); err != nil {
		return err
	}
	if err := confirmApply(os.Stdin, os.Stdout); err != nil {
		return err
	}

	files, err := planTemplateFiles()
	if err != nil {
		return err
	}
	if err := applyTemplateFiles(config, files); err != nil {
		return err
	}

	_, err = fmt.Fprintln(os.Stdout, "Template project configuration has been applied. Run git diff to review and merge the changes you need.")
	return err
}

func parseFlags() config {
	config := config{}
	flag.StringVar(&config.ref, "ref", defaultRef, "Template repository ref to download from")
	flag.Parse()
	return config
}

func ensureCleanGitWorktree() error {
	if _, err := exec.LookPath("git"); err != nil {
		return fmt.Errorf("find git: %w", err)
	}

	output, err := gitOutput("status", "--porcelain")
	if err != nil {
		return fmt.Errorf("check git status: %w", err)
	}
	if strings.TrimSpace(output) != "" {
		return errors.New("existing project apply requires a clean Git working tree; commit or stash changes first")
	}
	return nil
}

func gitOutput(args ...string) (string, error) {
	output, err := exec.Command("git", args...).CombinedOutput()
	if err != nil {
		if errors.Is(err, exec.ErrNotFound) {
			return "", fmt.Errorf("find git: %w", err)
		}
		return "", fmt.Errorf("git %s: %v: %s", strings.Join(args, " "), err, strings.TrimSpace(string(output)))
	}
	return string(output), nil
}

func confirmApply(input *os.File, output *os.File) error {
	reader := bufio.NewReader(input)
	message := "This will overwrite mise.toml, mise.ci.toml, mise lock files, renovate.json, .gitignore, hk.pkl, cliff.toml, and .github/workflows, and download the template documentation site when docs does not exist. Type yes to continue: "
	if _, err := fmt.Fprint(output, message); err != nil {
		return err
	}

	answer, err := reader.ReadString('\n')
	if err != nil {
		return err
	}
	if strings.TrimSpace(answer) != "yes" {
		return errors.New("apply was not confirmed")
	}
	return nil
}

func planTemplateFiles() ([]templateFile, error) {
	files := []templateFile{
		{path: "mise.toml", overwrite: true},
		{path: "mise.ci.toml", overwrite: true},
		{path: "mise.lock", overwrite: true},
		{path: "mise.ci.lock", overwrite: true},
		{path: "renovate.json", overwrite: true},
		{path: ".gitignore", overwrite: true},
		{path: "hk.pkl", overwrite: true},
		{path: "cliff.toml", overwrite: true},
		{path: ".github/workflows/ci.yml", overwrite: true},
		{path: ".github/workflows/docs.yml", overwrite: true},
		{path: ".github/workflows/prepare-release.yml", overwrite: true},
		{path: ".github/workflows/release.yml", overwrite: true},
	}

	if _, err := os.Stat("docs"); err == nil {
		fmt.Fprintln(os.Stdout, "Detected an existing docs directory. Skipping the template documentation site.")
		return files, nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}

	files = append(files,
		templateFile{path: "docs/.vitepress/config.ts"},
		templateFile{path: "docs/index.md"},
		templateFile{path: "docs/guide/completion.md"},
		templateFile{path: "docs/package.json"},
		templateFile{path: "docs/pnpm-lock.yaml"},
		templateFile{path: "docs/pnpm-workspace.yaml"},
	)
	return files, nil
}

func applyTemplateFiles(config config, files []templateFile) error {
	client := newHTTPClient()
	for _, file := range files {
		if !file.overwrite {
			if _, err := os.Stat(file.path); err == nil {
				continue
			} else if !errors.Is(err, os.ErrNotExist) {
				return err
			}
		}

		content, err := downloadTemplateFile(client, config.ref, file.path)
		if err != nil {
			return err
		}
		if err := writeFile(file.path, content, file.mode); err != nil {
			return err
		}
		fmt.Fprintf(os.Stdout, "Wrote %s\n", file.path)
	}
	if err := removeObsoleteTemplateFiles(); err != nil {
		return err
	}
	return removeMiseInitTask()
}

func downloadTemplateFile(client *http.Client, ref string, path string) ([]byte, error) {
	url := fmt.Sprintf("%s/%s/%s", strings.TrimRight(repositoryRawBase, "/"), ref, filepath.ToSlash(path))
	request, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	response, err := client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("download %s: %w", path, err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("download %s: unexpected status %s", path, response.Status)
	}

	content, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	return content, nil
}

func writeFile(path string, content []byte, mode os.FileMode) error {
	if mode == 0 {
		mode = 0o644
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, content, mode)
}

func removeObsoleteTemplateFiles() error {
	for _, path := range obsoleteTemplateFiles {
		if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	return nil
}

func removeMiseInitTask() error {
	return removeTOMLTable("mise.toml", "tasks.init")
}

func removeTOMLTable(path string, table string) error {
	content, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}

	lines := strings.SplitAfter(string(content), "\n")
	targetHeader := "[" + table + "]"
	updated := make([]string, 0, len(lines))
	removing := false
	removed := false

	for _, line := range lines {
		trimmedLine := strings.TrimSpace(line)
		if !removing && trimmedLine == targetHeader {
			removing = true
			removed = true
			continue
		}
		if removing {
			if isTOMLTableHeader(trimmedLine) {
				removing = false
			} else {
				continue
			}
		}
		updated = append(updated, line)
	}
	if !removed {
		return nil
	}

	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(strings.Join(updated, "")), info.Mode())
}

func isTOMLTableHeader(line string) bool {
	return strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]")
}
