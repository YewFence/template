# {{PROJECT_NAME}}

[![Release](https://img.shields.io/github/v/release/{{GITHUB_OWNER}}/{{REPO_NAME}}?sort=semver)](https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}/releases)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://{{GITHUB_OWNER}}.github.io/{{REPO_NAME}}/)
[![License](https://img.shields.io/github/license/{{GITHUB_OWNER}}/{{REPO_NAME}})](LICENSE)

{{PROJECT_DESCRIPTION}}

> [!NOTE]
> This project is in an early development stage. Core features may be missing, and backward compatibility is not guaranteed.

## Quick Start

### Installation

#### Mise

```bash
mise use --global github:{{GITHUB_OWNER}}/{{REPO_NAME}}
```

#### Go

```bash
go install github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}/cmd/{{PROJECT_NAME}}@latest
```

#### Build and install from source locally

```bash
git clone https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}.git
cd {{REPO_NAME}}
mise trust
mise install
mise run cli:install
```

### Usage

```bash
{{PROJECT_NAME}}
{{PROJECT_NAME}} version
```

## Documentation

See the [documentation site](https://{{GITHUB_OWNER}}.github.io/{{REPO_NAME}}) for more information.

## Contributing

If you have suggestions or find a bug, please [open an issue](https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}}/issues).

Pull requests are welcome. See the [Contributing Guide](CONTRIBUTING.md).

## License

[MIT License](LICENSE)
