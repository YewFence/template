package cli

import (
	"bytes"
	"strings"
	"testing"
)

func TestRootCommand(t *testing.T) {
	command := NewRootCommand("test")
	buffer := &bytes.Buffer{}
	command.SetOut(buffer)
	command.SetErr(buffer)
	command.SetArgs(nil)

	if err := command.Execute(); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if got := buffer.String(); got != "Hello from your-cli\n" {
		t.Fatalf("output = %q, want greeting", got)
	}
}

func TestRootCommandCompletion(t *testing.T) {
	command := NewRootCommand("test")
	buffer := &bytes.Buffer{}
	command.SetOut(buffer)
	command.SetErr(buffer)
	command.SetArgs([]string{"completion", "bash"})

	if err := command.Execute(); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if got := buffer.String(); !strings.Contains(got, "# bash completion V2 for your-cli") {
		t.Fatalf("completion output missing CLI name:\n%s", got)
	}
}

func TestVersionCommand(t *testing.T) {
	command := NewRootCommand("test")
	buffer := &bytes.Buffer{}
	command.SetOut(buffer)
	command.SetErr(buffer)
	command.SetArgs([]string{"version"})

	if err := command.Execute(); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if got := buffer.String(); got != "your-cli test\n" {
		t.Fatalf("output = %q, want version", got)
	}
}
