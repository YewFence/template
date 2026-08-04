package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const templateOriginPath = "github.com/YewFence/go-cli-template"

type config struct {
	module      string
	name        string
	owner       string
	repo        string
	description string
	freshGit    bool
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "init template: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	config := parseFlags()
	if config.needsPrompt() {
		if err := config.promptMissing(os.Stdin, os.Stdout); err != nil {
			return err
		}
	}
	if err := config.validate(); err != nil {
		return err
	}

	replacements := templateReplacements(config)

	if err := filepath.WalkDir(".", func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if shouldSkipDir(path) {
				return filepath.SkipDir
			}
			return nil
		}
		if shouldSkipFile(path) {
			return nil
		}
		return replaceInFile(path, replacements)
	}); err != nil {
		return err
	}

	if err := renameCLIEntrypoint(config.name); err != nil {
		return err
	}
	if err := removeTemplateOrigin(); err != nil {
		return err
	}
	if err := replaceWithTemplate("README.md", "README.template.md"); err != nil {
		return err
	}
	if err := replaceWithTemplate("AGENTS.md", "AGENTS.template.md"); err != nil {
		return err
	}
	if err := os.Remove("CHANGELOG.md"); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := removeMiseInitTask(); err != nil {
		return err
	}

	if config.freshGit {
		if err := resetGitHistory(); err != nil {
			return err
		}
	}

	if _, err := fmt.Fprintln(os.Stdout, "Third-party library versions may be outdated. Run mise run deps:update to update Go dependencies and tidy modules."); err != nil {
		return err
	}
	_, err := fmt.Fprintln(os.Stdout, "If you no longer need the template initialization tool, delete `tools/init-template`.")
	return err
}

func parseFlags() config {
	config := config{}
	flag.StringVar(&config.module, "module", "", "Go module path, for example github.com/you/your-cli")
	flag.StringVar(&config.name, "name", "", "CLI binary name")
	flag.StringVar(&config.owner, "owner", "", "GitHub owner or organization")
	flag.StringVar(&config.repo, "repo", "", "GitHub repository name")
	flag.StringVar(&config.description, "description", "", "Project description")
	flag.BoolVar(&config.freshGit, "fresh-git", false, "Reset Git history and create a fresh main branch")
	flag.Parse()
	return config
}

func resetGitHistory() error {
	if _, err := exec.LookPath("git"); err != nil {
		return fmt.Errorf("find git: %w", err)
	}
	if err := ensureFreshGitRoot(); err != nil {
		return err
	}
	if err := os.RemoveAll(".git"); err != nil {
		return fmt.Errorf("remove .git: %w", err)
	}
	if err := runGit("init", "-b", "main"); err != nil {
		return err
	}
	return nil
}

func ensureFreshGitRoot() error {
	currentDir, err := os.Getwd()
	if err != nil {
		return err
	}
	currentDir, err = filepath.EvalSymlinks(currentDir)
	if err != nil {
		return err
	}

	gitInfo, err := os.Stat(".git")
	if err == nil && !gitInfo.IsDir() {
		return errors.New("--fresh-git does not support Git worktrees or repositories with a .git file")
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}

	topLevel, err := gitOutput("rev-parse", "--show-toplevel")
	if err != nil {
		if errors.Is(err, errGitCommandFailed) {
			return nil
		}
		return err
	}

	topLevel = strings.TrimSpace(topLevel)
	if topLevel == "" {
		return nil
	}
	topLevel, err = filepath.EvalSymlinks(topLevel)
	if err != nil {
		return err
	}
	if topLevel != currentDir {
		return fmt.Errorf("--fresh-git must be run from the Git repository root, current root is %s", topLevel)
	}
	return nil
}

var errGitCommandFailed = errors.New("git command failed")

func gitOutput(args ...string) (string, error) {
	output, err := exec.Command("git", args...).CombinedOutput()
	if err != nil {
		if errors.Is(err, exec.ErrNotFound) {
			return "", fmt.Errorf("find git: %w", err)
		}
		if len(output) == 0 {
			return "", fmt.Errorf("%w: git %s: %v", errGitCommandFailed, strings.Join(args, " "), err)
		}
		return "", fmt.Errorf("%w: git %s: %v: %s", errGitCommandFailed, strings.Join(args, " "), err, strings.TrimSpace(string(output)))
	}
	return string(output), nil
}

func runGit(args ...string) error {
	_, err := gitOutput(args...)
	return err
}

func (config config) validate() error {
	if config.module == "" {
		return errors.New("--module is required")
	}
	if config.name == "" {
		return errors.New("--name is required")
	}
	if config.repo == "" {
		return errors.New("--repo is required")
	}
	if config.owner == "" {
		return errors.New("--owner is required")
	}
	if config.description == "" {
		return errors.New("--description is required")
	}
	if strings.ContainsAny(config.name, " /\\") {
		return errors.New("--name must be a binary-friendly name without spaces or slashes")
	}
	return nil
}

func (config config) needsPrompt() bool {
	return config.module == "" || config.name == "" || config.owner == "" || config.repo == "" || config.description == ""
}

func (config *config) promptMissing(input *os.File, output *os.File) error {
	reader := bufio.NewReader(input)

	var err error
	config.module, err = prompt(reader, output, "Go module path", config.module)
	if err != nil {
		return err
	}

	defaultName := config.name
	if defaultName == "" {
		defaultName = moduleName(config.module)
	}
	config.name, err = prompt(reader, output, "Binary name", defaultName)
	if err != nil {
		return err
	}

	defaultOwner := config.owner
	if defaultOwner == "" {
		defaultOwner = moduleOwner(config.module)
	}
	config.owner, err = prompt(reader, output, "GitHub owner", defaultOwner)
	if err != nil {
		return err
	}

	defaultRepo := config.repo
	if defaultRepo == "" {
		defaultRepo = config.name
	}
	config.repo, err = prompt(reader, output, "GitHub repo", defaultRepo)
	if err != nil {
		return err
	}

	config.description, err = prompt(reader, output, "Description", config.description)
	if err != nil {
		return err
	}

	return nil
}

func prompt(reader *bufio.Reader, output *os.File, label string, defaultValue string) (string, error) {
	if defaultValue == "" {
		if _, err := fmt.Fprintf(output, "%s: ", label); err != nil {
			return "", err
		}
	} else {
		if _, err := fmt.Fprintf(output, "%s [%s]: ", label, defaultValue); err != nil {
			return "", err
		}
	}

	value, err := reader.ReadString('\n')
	if err != nil {
		return "", err
	}
	value = strings.TrimSpace(value)
	if value == "" {
		return defaultValue, nil
	}
	return value, nil
}

func moduleName(module string) string {
	module = strings.TrimSuffix(module, "/")
	if module == "" {
		return ""
	}
	index := strings.LastIndex(module, "/")
	if index < 0 {
		return module
	}
	return module[index+1:]
}

func moduleOwner(module string) string {
	parts := strings.Split(strings.Trim(module, "/"), "/")
	if len(parts) >= 2 {
		return parts[len(parts)-2]
	}
	return ""
}

func shouldSkipDir(path string) bool {
	if hasPathSegment(path, "node_modules") {
		return true
	}
	switch path {
	case ".git", "dist", "bin", "docs/.vitepress/cache", "docs/.vitepress/dist":
		return true
	default:
		return false
	}
}

func shouldSkipFile(path string) bool {
	if hasPathSegment(path, "node_modules") {
		return true
	}
	switch filepath.Base(path) {
	case "go.sum", "pnpm-lock.yaml":
		return true
	default:
		return false
	}
}

func hasPathSegment(path string, segment string) bool {
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if part == segment {
			return true
		}
	}
	return false
}

func renameCLIEntrypoint(name string) error {
	templateEntrypoint := filepath.Join("cmd", "your-cli")
	targetEntrypoint := filepath.Join("cmd", name)
	if targetEntrypoint == templateEntrypoint {
		return nil
	}
	if _, err := os.Stat(templateEntrypoint); errors.Is(err, os.ErrNotExist) {
		return nil
	} else if err != nil {
		return err
	}
	if err := os.RemoveAll(targetEntrypoint); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(targetEntrypoint), 0o755); err != nil {
		return err
	}
	return os.Rename(templateEntrypoint, targetEntrypoint)
}

func replaceWithTemplate(targetPath string, templatePath string) error {
	if _, err := os.Stat(templatePath); err == nil {
		if err := os.Remove(targetPath); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		return os.Rename(templatePath, targetPath)
	} else if errors.Is(err, os.ErrNotExist) {
		return nil
	} else {
		return err
	}
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

type replacement struct {
	old string
	new string
}

func templateReplacements(config config) []replacement {
	return []replacement{
		{old: "{{MODULE_PATH}}", new: config.module},
		{old: "{{PROJECT_NAME}}", new: config.name},
		{old: "{{GITHUB_OWNER}}", new: config.owner},
		{old: "{{REPO_NAME}}", new: config.repo},
		{old: "{{PROJECT_DESCRIPTION}}", new: config.description},
		{old: "github.com/example/your-cli", new: config.module},
		{old: "example", new: config.owner},
		{old: "your-cli", new: config.name},
		{old: "Your CLI description", new: config.description},
	}
}

func replaceInFile(path string, replacements []replacement) error {
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	pairs := make([]string, 0, len(replacements)*2)
	for _, replacement := range replacements {
		pairs = append(pairs, replacement.old, replacement.new)
	}
	updated := strings.NewReplacer(pairs...).Replace(string(content))
	if updated == string(content) {
		return nil
	}

	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(updated), info.Mode())
}

func removeTemplateOrigin() error {
	remoteURLOutput, err := exec.Command("git", "remote", "get-url", "origin").Output()
	if err != nil {
		return nil
	}

	if !isTemplateOrigin(string(remoteURLOutput)) {
		return nil
	}

	return exec.Command("git", "remote", "remove", "origin").Run()
}

func isTemplateOrigin(remoteURL string) bool {
	remoteURL = strings.TrimSpace(remoteURL)
	remoteURL = strings.TrimSuffix(remoteURL, ".git")
	remoteURL = strings.TrimPrefix(remoteURL, "https://")
	remoteURL = strings.TrimPrefix(remoteURL, "http://")
	remoteURL = strings.TrimPrefix(remoteURL, "git@")
	remoteURL = strings.Replace(remoteURL, ":", "/", 1)
	return remoteURL == templateOriginPath
}
