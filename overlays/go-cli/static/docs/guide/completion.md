# Shell Completion

{{BINARY_NAME}} uses Cobra's native completion support and does not require an additional generator.

## Generate Completion Scripts

After building the binary, use the `completion` subcommand to generate completion scripts for Bash, Zsh, Fish, and PowerShell.

```bash
mise run build
./bin/{{BINARY_NAME}} completion zsh > _{{BINARY_NAME}}
./bin/{{BINARY_NAME}} completion bash > {{BINARY_NAME}}.bash
./bin/{{BINARY_NAME}} completion fish > {{BINARY_NAME}}.fish
./bin/{{BINARY_NAME}} completion powershell > {{BINARY_NAME}}.ps1
```

## Installation Examples

For Zsh, place the generated `_{{PROJECT_NAME}}` file in an existing directory from `$fpath`, or place it in a custom directory and add that directory in `~/.zshrc`.

```bash
mkdir -p ~/.zsh/completions
./bin/{{BINARY_NAME}} completion zsh > ~/.zsh/completions/_{{BINARY_NAME}}
```

```zsh
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit
compinit
```

For Bash, place the completion script in a local directory and source it manually, or let the system bash-completion directory manage it.

```bash
mkdir -p ~/.bash_completion.d
./bin/{{BINARY_NAME}} completion bash > ~/.bash_completion.d/{{BINARY_NAME}}.bash
source ~/.bash_completion.d/{{BINARY_NAME}}.bash
```

For Fish, write the script directly to the user completion directory.

```bash
mkdir -p ~/.config/fish/completions
./bin/{{BINARY_NAME}} completion fish > ~/.config/fish/completions/{{BINARY_NAME}}.fish
```
