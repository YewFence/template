package main

import "github.com/example/your-cli/internal/cli"

var version = "dev"

func main() {
	cli.Execute(version)
}
