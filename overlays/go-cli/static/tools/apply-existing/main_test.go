package main

import (
	"bytes"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestPlanTemplateFilesSkipsDocsWhenDocsExists(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)
	if err := os.Mkdir("docs", 0o755); err != nil {
		t.Fatal(err)
	}

	files, err := planTemplateFiles()
	if err != nil {
		t.Fatalf("planTemplateFiles() error = %v", err)
	}

	for _, file := range files {
		if strings.HasPrefix(file.path, "docs/") {
			t.Fatalf("planTemplateFiles() included docs file %s when docs exists", file.path)
		}
	}
}

func TestPlanTemplateFilesIncludesDocsWhenDocsMissing(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	files, err := planTemplateFiles()
	if err != nil {
		t.Fatalf("planTemplateFiles() error = %v", err)
	}

	if !hasTemplatePath(files, "docs/.vitepress/config.ts") {
		t.Fatalf("planTemplateFiles() missing docs/.vitepress/config.ts")
	}
	if !hasTemplatePath(files, ".gitignore") {
		t.Fatalf("planTemplateFiles() missing .gitignore")
	}
	if !hasTemplatePath(files, "mise.ci.toml") {
		t.Fatalf("planTemplateFiles() missing mise.ci.toml")
	}
	if !hasTemplatePath(files, ".github/workflows/prepare-release.yml") {
		t.Fatalf("planTemplateFiles() missing .github/workflows/prepare-release.yml")
	}
	if hasTemplatePath(files, ".github/workflows/actions-up.yml") {
		t.Fatalf("planTemplateFiles() included removed actions-up workflow")
	}
	if !hasTemplatePath(files, "renovate.json") {
		t.Fatalf("planTemplateFiles() missing renovate.json")
	}
}

func TestApplyTemplateFilesOverwritesConfigAndCreatesMissingDocs(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	oldRawBase := repositoryRawBase
	repositoryRawBase = "https://example.test/templates"
	t.Cleanup(func() {
		repositoryRawBase = oldRawBase
	})
	oldNewHTTPClient := newHTTPClient
	newHTTPClient = func() *http.Client {
		return &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			bodyByPath := map[string]string{
				"/templates/test-ref/mise.toml": strings.Join([]string{
					"[tasks.init]",
					"description = \"Initialize project\"",
					"run = \"go run ./tools/init-template/main.go\"",
					"",
					"[tasks.test]",
					"description = \"Run tests\"",
					"run = \"go test ./...\"",
					"",
				}, "\n"),
				"/templates/test-ref/renovate.json": "{}\n",
				"/templates/test-ref/.gitignore":    "bin/\ndist/\n",
				"/templates/test-ref/docs/index.md": "# docs\n",
			}
			body, ok := bodyByPath[request.URL.Path]
			if !ok {
				return &http.Response{
					StatusCode: http.StatusNotFound,
					Status:     "404 Not Found",
					Body:       io.NopCloser(bytes.NewBufferString("not found")),
				}, nil
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Status:     "200 OK",
				Body:       io.NopCloser(bytes.NewBufferString(body)),
			}, nil
		})}
	}
	t.Cleanup(func() {
		newHTTPClient = oldNewHTTPClient
	})

	if err := os.WriteFile("mise.toml", []byte("old mise\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(".gitignore", []byte("old ignore\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	files := []templateFile{
		{path: "mise.toml", overwrite: true},
		{path: "renovate.json", overwrite: true},
		{path: ".gitignore", overwrite: true},
		{path: "docs/index.md"},
	}
	config := config{ref: "test-ref"}
	if err := applyTemplateFiles(config, files); err != nil {
		t.Fatalf("applyTemplateFiles() error = %v", err)
	}

	assertFileContent(t, "mise.toml", strings.Join([]string{
		"[tasks.test]",
		"description = \"Run tests\"",
		"run = \"go test ./...\"",
		"",
	}, "\n"))
	assertFileContent(t, "renovate.json", "{}\n")
	assertFileContent(t, ".gitignore", "bin/\ndist/\n")
	assertFileContent(t, "docs/index.md", "# docs\n")
}

func TestRemoveMiseInitTask(t *testing.T) {
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

func TestRemoveObsoleteTemplateFiles(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)
	path := filepath.Join(".github", "workflows", "actions-up.yml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("name: actions-up\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := removeObsoleteTemplateFiles(); err != nil {
		t.Fatalf("removeObsoleteTemplateFiles() error = %v", err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("%s stat error = %v, want not exist", path, err)
	}
}

func TestConfirmApplyAcceptsYes(t *testing.T) {
	input := writeTempInput(t, "yes\n")
	output := writeTempInput(t, "")

	if err := confirmApply(input, output); err != nil {
		t.Fatalf("confirmApply() error = %v", err)
	}
}

func TestConfirmApplyRejectsOtherInput(t *testing.T) {
	input := writeTempInput(t, "no\n")
	output := writeTempInput(t, "")

	err := confirmApply(input, output)
	if err == nil {
		t.Fatalf("confirmApply() error = nil, want error")
	}
	if !strings.Contains(err.Error(), "was not confirmed") {
		t.Fatalf("confirmApply() error = %v, want confirmation error", err)
	}
}

func TestEnsureCleanGitWorktreeAllowsCleanRepository(t *testing.T) {
	requireGit(t)

	directory := t.TempDir()
	t.Chdir(directory)

	runTestGit(t, "init", "-b", "main")
	if err := os.WriteFile("main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	runTestGit(t, "add", ".")
	runTestGit(t, "-c", "user.name=Template", "-c", "user.email=template@example.com", "-c", "commit.gpgsign=false", "commit", "-m", "initial")

	if err := ensureCleanGitWorktree(); err != nil {
		t.Fatalf("ensureCleanGitWorktree() error = %v", err)
	}
}

func TestEnsureCleanGitWorktreeRejectsDirtyRepository(t *testing.T) {
	requireGit(t)

	directory := t.TempDir()
	t.Chdir(directory)

	runTestGit(t, "init", "-b", "main")
	if err := os.WriteFile("main.go", []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	runTestGit(t, "add", ".")
	runTestGit(t, "-c", "user.name=Template", "-c", "user.email=template@example.com", "-c", "commit.gpgsign=false", "commit", "-m", "initial")
	if err := os.WriteFile("main.go", []byte("package main\n\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	err := ensureCleanGitWorktree()
	if err == nil {
		t.Fatalf("ensureCleanGitWorktree() error = nil, want error")
	}
	if !strings.Contains(err.Error(), "clean Git working tree") {
		t.Fatalf("ensureCleanGitWorktree() error = %v, want clean Git working tree error", err)
	}
}

func hasTemplatePath(files []templateFile, path string) bool {
	for _, file := range files {
		if file.path == path {
			return true
		}
	}
	return false
}

func assertFileContent(t *testing.T, path string, want string) {
	t.Helper()

	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := string(content); got != want {
		t.Fatalf("%s = %q, want %q", path, got, want)
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
	output, err := exec.Command("git", args...).CombinedOutput()
	if err != nil {
		t.Fatalf("git %s failed: %v\n%s", strings.Join(args, " "), err, output)
	}
	return string(output)
}

func writeTempInput(t *testing.T, content string) *os.File {
	t.Helper()

	file, err := os.CreateTemp(t.TempDir(), "input-*")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := file.WriteString(content); err != nil {
		t.Fatal(err)
	}
	if _, err := file.Seek(0, 0); err != nil {
		t.Fatal(err)
	}
	return file
}

func TestWriteFileCreatesParents(t *testing.T) {
	directory := t.TempDir()
	t.Chdir(directory)

	path := filepath.Join("nested", "file.txt")
	if err := writeFile(path, []byte("content\n"), 0); err != nil {
		t.Fatalf("writeFile() error = %v", err)
	}

	assertFileContent(t, path, "content\n")
}

func assertFileMode(t *testing.T, path string, want os.FileMode) {
	t.Helper()

	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != want {
		t.Fatalf("%s mode = %o, want %o", path, got, want)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}
