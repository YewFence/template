package main

import (
	"errors"
	"flag"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestIsTemplateOrigin(t *testing.T) {
	tests := []struct {
		name      string
		remoteURL string
		want      bool
	}{
		{
			name:      "matches template origin",
			remoteURL: "https://github.com/YewFence/go-cli-template",
			want:      true,
		},
		{
			name:      "matches template origin with git suffix",
			remoteURL: "https://github.com/YewFence/go-cli-template.git\n",
			want:      true,
		},
		{
			name:      "matches template origin with http",
			remoteURL: "http://github.com/YewFence/go-cli-template.git",
			want:      true,
		},
		{
			name:      "matches template origin with ssh",
			remoteURL: "git@github.com:YewFence/go-cli-template.git",
			want:      true,
		},
		{
			name:      "ignores other origin",
			remoteURL: "https://github.com/YewFence/other.git",
			want:      false,
		},
		{
			name:      "ignores other ssh origin",
			remoteURL: "git@github.com:YewFence/other.git",
			want:      false,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := isTemplateOrigin(test.remoteURL)
			if got != test.want {
				t.Fatalf("isTemplateOrigin(%q) = %v, want %v", test.remoteURL, got, test.want)
			}
		})
	}
}

func TestResetGitHistoryCreatesFreshRepository(t *testing.T) {
	requireGit(t)

	directory := t.TempDir()
	t.Chdir(directory)
	if err := os.WriteFile("main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	runTestGit(t, "init", "-b", "main")
	runTestGit(t, "remote", "add", "origin", "https://github.com/YewFence/go-cli-template.git")
	runTestGit(t, "add", ".")
	runTestGit(t, "-c", "user.name=Template", "-c", "user.email=template@example.com", "-c", "commit.gpgsign=false", "commit", "-m", "initial")

	if err := resetGitHistory(); err != nil {
		t.Fatalf("resetGitHistory() error = %v", err)
	}

	if info, err := os.Stat(".git"); err != nil || !info.IsDir() {
		t.Fatalf(".git directory was not recreated")
	}
	if remoteURL, err := runTestGitAllowError("remote", "get-url", "origin"); err == nil {
		t.Fatalf("origin remote = %q, want missing remote", remoteURL)
	}
	if output := runTestGit(t, "branch", "--show-current"); strings.TrimSpace(output) != "main" {
		t.Fatalf("branch = %q, want main", output)
	}
	if output, err := runTestGitAllowError("log", "--oneline"); err == nil {
		t.Fatalf("git log succeeded after history reset with output %q", output)
	}
}

func TestResetGitHistoryRejectsNestedRepository(t *testing.T) {
	requireGit(t)

	directory := t.TempDir()
	t.Chdir(directory)
	runTestGit(t, "init", "-b", "main")

	nestedDirectory := filepath.Join(directory, "nested")
	if err := os.Mkdir(nestedDirectory, 0o755); err != nil {
		t.Fatal(err)
	}
	t.Chdir(nestedDirectory)

	err := resetGitHistory()
	if err == nil {
		t.Fatalf("resetGitHistory() error = nil, want error")
	}
	if !strings.Contains(err.Error(), "repository root") {
		t.Fatalf("resetGitHistory() error = %v, want repository root error", err)
	}
}

func TestTemplateReplacementsSupportExplicitPlaceholders(t *testing.T) {
	config := config{
		module:      "github.com/acme/widget-module",
		name:        "widget",
		owner:       "acme",
		repo:        "widget-repo",
		description: "Manage widgets",
	}
	replacements := templateReplacements(config)

	directory := t.TempDir()
	path := filepath.Join(directory, "README.template.md")
	content := strings.Join([]string{
		"# {{PROJECT_NAME}}",
		"{{PROJECT_DESCRIPTION}}",
		"https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}",
		"{{MODULE_PATH}}",
	}, "\n")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := replaceInFile(path, replacements); err != nil {
		t.Fatalf("replaceInFile() error = %v", err)
	}
	output, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	got := string(output)
	for _, want := range []string{
		"# widget",
		"Manage widgets",
		"https://github.com/acme/widget-repo",
		"github.com/acme/widget-module",
	} {
		if !strings.Contains(got, want) {
			t.Fatalf("output missing %q:\n%s", want, got)
		}
	}
	if strings.Contains(got, "{{") {
		t.Fatalf("output still contains template placeholders:\n%s", got)
	}
}

func TestTemplateReplacementsDoNotRewriteReplacementValues(t *testing.T) {
	config := config{
		module:      "github.com/example-labs/your-cli-module",
		name:        "example-your-cli",
		owner:       "example-labs",
		repo:        "example-your-cli-repo",
		description: "Manage example your-cli projects",
	}
	replacements := templateReplacements(config)

	directory := t.TempDir()
	path := filepath.Join(directory, "main.go")
	content := strings.Join([]string{
		`explicitModule = "{{MODULE_PATH}}"`,
		`explicitName = "{{PROJECT_NAME}}"`,
		`explicitOwner = "{{GITHUB_OWNER}}"`,
		`explicitRepo = "{{REPO_NAME}}"`,
		`explicitDescription = "{{PROJECT_DESCRIPTION}}"`,
		`legacyModule = "github.com/example/your-cli"`,
		`legacyName = "your-cli"`,
		`legacyOwner = "example"`,
		`legacyDescription = "Your CLI description"`,
	}, "\n")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := replaceInFile(path, replacements); err != nil {
		t.Fatalf("replaceInFile() error = %v", err)
	}
	output, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	got := string(output)
	wants := []string{
		`explicitModule = "github.com/example-labs/your-cli-module"`,
		`explicitName = "example-your-cli"`,
		`explicitOwner = "example-labs"`,
		`explicitRepo = "example-your-cli-repo"`,
		`explicitDescription = "Manage example your-cli projects"`,
		`legacyModule = "github.com/example-labs/your-cli-module"`,
		`legacyName = "example-your-cli"`,
		`legacyOwner = "example-labs"`,
		`legacyDescription = "Manage example your-cli projects"`,
	}
	for _, want := range wants {
		if !strings.Contains(got, want) {
			t.Fatalf("output missing %q:\n%s", want, got)
		}
	}
}

func TestRenameCLIEntrypoint(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	if err := os.MkdirAll("cmd/your-cli", 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("cmd/your-cli/main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := renameCLIEntrypoint("widget"); err != nil {
		t.Fatalf("renameCLIEntrypoint() error = %v", err)
	}
	if _, err := os.Stat("cmd/your-cli"); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("cmd/your-cli stat error = %v, want not exist", err)
	}
	if _, err := os.Stat("cmd/widget/main.go"); err != nil {
		t.Fatalf("cmd/widget/main.go stat error = %v", err)
	}
}

func TestRemoveTOMLTable(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, "mise.toml")
	content := strings.Join([]string{
		"[settings]",
		"lockfile = true",
		"",
		"[tasks.init]",
		"description = \"Initialize project\"",
		"run = \"go run ./tools/init-template/main.go\"",
		"",
		"[tasks.test]",
		"description = \"Run tests\"",
		"run = \"go test ./...\"",
		"",
	}, "\n")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := removeTOMLTable(path, "tasks.init"); err != nil {
		t.Fatalf("removeTOMLTable() error = %v", err)
	}
	output, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	got := string(output)
	if strings.Contains(got, "[tasks.init]") {
		t.Fatalf("mise.toml still contains tasks.init:\n%s", got)
	}
	for _, want := range []string{
		"[settings]",
		"lockfile = true",
		"[tasks.test]",
		"description = \"Run tests\"",
		"run = \"go test ./...\"",
	} {
		if !strings.Contains(got, want) {
			t.Fatalf("mise.toml missing %q:\n%s", want, got)
		}
	}
}

func TestRunReplacesReadmeWithReadmeTemplate(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	if err := os.WriteFile("README.md", []byte("# Template repository README\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	readmeTemplate := strings.Join([]string{
		"# {{PROJECT_NAME}}",
		"{{PROJECT_DESCRIPTION}}",
		"https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}",
		"{{MODULE_PATH}}",
	}, "\n")
	if err := os.WriteFile("README.template.md", []byte(readmeTemplate), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("renovate.json", []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("CHANGELOG.md", []byte("# Changelog\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	miseTOML := strings.Join([]string{
		"[tasks.init]",
		"description = \"Initialize project\"",
		"run = \"go run ./tools/init-template/main.go\"",
		"",
		"[tasks.test]",
		"description = \"Run tests\"",
		"run = \"go test ./...\"",
		"",
	}, "\n")
	if err := os.WriteFile("mise.toml", []byte(miseTOML), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll("cmd/your-cli", 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("cmd/your-cli/main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldArgs := os.Args
	oldCommandLine := flag.CommandLine
	t.Cleanup(func() {
		os.Args = oldArgs
		flag.CommandLine = oldCommandLine
	})
	flag.CommandLine = flag.NewFlagSet("init-template", flag.ContinueOnError)
	os.Args = []string{
		"init-template",
		"--module", "github.com/acme/widget-module",
		"--name", "widget",
		"--owner", "acme",
		"--repo", "widget-repo",
		"--description", "Manage widgets",
	}

	if err := run(); err != nil {
		t.Fatalf("run() error = %v", err)
	}

	if _, err := os.Stat("README.template.md"); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("README.template.md stat error = %v, want not exist", err)
	}
	if _, err := os.Stat("renovate.json"); err != nil {
		t.Fatalf("renovate.json stat error = %v", err)
	}
	if _, err := os.Stat("CHANGELOG.md"); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("CHANGELOG.md stat error = %v, want not exist", err)
	}
	miseOutput, err := os.ReadFile("mise.toml")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(miseOutput), "[tasks.init]") {
		t.Fatalf("mise.toml still contains tasks.init:\n%s", string(miseOutput))
	}
	if !strings.Contains(string(miseOutput), "[tasks.test]") {
		t.Fatalf("mise.toml missing tasks.test:\n%s", string(miseOutput))
	}
	if _, err := os.Stat("cmd/widget/main.go"); err != nil {
		t.Fatalf("cmd/widget/main.go stat error = %v", err)
	}
	output, err := os.ReadFile("README.md")
	if err != nil {
		t.Fatal(err)
	}

	got := string(output)
	for _, want := range []string{
		"# widget",
		"Manage widgets",
		"https://github.com/acme/widget-repo",
		"github.com/acme/widget-module",
	} {
		if !strings.Contains(got, want) {
			t.Fatalf("README.md missing %q:\n%s", want, got)
		}
	}
	if strings.Contains(got, "Template repository README") {
		t.Fatalf("README.md still contains the template repository README:\n%s", got)
	}
}

func TestRunReplacesAgentsWithAgentsTemplate(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	if err := os.WriteFile("README.md", []byte("# Template repository README\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("README.template.md", []byte("# {{PROJECT_NAME}}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("AGENTS.md", []byte("Template repository agent instructions\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	agentsTemplate := strings.Join([]string{
		"After changing Go code, run `mise run check` before finishing.",
		"{{PROJECT_NAME}} is in early development.",
	}, "\n")
	if err := os.WriteFile("AGENTS.template.md", []byte(agentsTemplate), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll("cmd/your-cli", 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("cmd/your-cli/main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldArgs := os.Args
	oldCommandLine := flag.CommandLine
	t.Cleanup(func() {
		os.Args = oldArgs
		flag.CommandLine = oldCommandLine
	})
	flag.CommandLine = flag.NewFlagSet("init-template", flag.ContinueOnError)
	os.Args = []string{
		"init-template",
		"--module", "github.com/acme/widget-module",
		"--name", "widget",
		"--owner", "acme",
		"--repo", "widget-repo",
		"--description", "Manage widgets",
	}

	if err := run(); err != nil {
		t.Fatalf("run() error = %v", err)
	}

	if _, err := os.Stat("AGENTS.template.md"); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("AGENTS.template.md stat error = %v, want not exist", err)
	}
	output, err := os.ReadFile("AGENTS.md")
	if err != nil {
		t.Fatal(err)
	}

	got := string(output)
	for _, want := range []string{
		"After changing Go code, run `mise run check` before finishing.",
		"widget is in early development.",
	} {
		if !strings.Contains(got, want) {
			t.Fatalf("AGENTS.md missing %q:\n%s", want, got)
		}
	}
	if strings.Contains(got, "Template repository agent instructions") {
		t.Fatalf("AGENTS.md still contains the template repository instructions:\n%s", got)
	}
}

func requireGit(t *testing.T) {
	t.Helper()
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git is not installed")
	}
}

func runTestGit(t *testing.T, args ...string) string {
	t.Helper()
	output, err := runTestGitAllowError(args...)
	if err != nil {
		t.Fatalf("git %s failed: %v\n%s", strings.Join(args, " "), err, output)
	}
	return output
}

func runTestGitAllowError(args ...string) (string, error) {
	output, err := exec.Command("git", args...).CombinedOutput()
	return string(output), err
}
