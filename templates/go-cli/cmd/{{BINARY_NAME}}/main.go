package main

import "{{GO_MODULE}}/internal/cli"

var version = "dev"

func main() {
	cli.Execute(version)
}
