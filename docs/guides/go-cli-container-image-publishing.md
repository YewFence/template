# Publishing Container Images (Go CLI)

The `container-image-publish` template capability of the `go-cli` profile is disabled by default. When enabled, the generated project builds an image from `./cmd/<binary-name>` with `ko` — no Dockerfile or `ko.yaml` needed.

## One-Time Setup

Before the first release, make sure the repository allows GitHub Actions to write packages with `GITHUB_TOKEN`. The workflow grants only `contents: read` and `packages: write` to the image publishing job; it never reads long-lived registry secrets.

After the first image publish, check the GHCR package's visibility as needed, and confirm the package is linked to the source repository. If organization policies restrict package creation or visibility, an organization admin has to grant the permission.

## Local Build

After bootstrapping the project and installing the tools from `mise.ci.toml`, run the local build task in the CI environment:

```bash
MISE_ENV=ci mise run container:build
```

The task uses `ko build --local` to load a single-platform image into the local Docker-compatible daemon; it does not log in to or push to any registry. It defaults to the `ko.local` repository and the current platform. Set `CONTAINER_IMAGE_PLATFORM` to pick a platform:

```bash
MISE_ENV=ci CONTAINER_IMAGE_PLATFORM=linux/arm64 mise run container:build
```

## Release Behavior

The release workflow publishes the GitHub Release first, then calls `mise run container:publish` with the tag, checkout ref, and prerelease state resolved in the same run. The default repository is the lowercased `ghcr.io/<owner>/<repository>` after instantiation; the publish task builds a multi-platform manifest with `--platform=all`.

Version `v1.2.3` publishes `:v1.2.3`; stable releases also update `:latest`, while prereleases only publish their own tag. Workflow dispatch can retry the image publish for the same release tag without recreating the tag.

The generated project can override the full registry/repository with `CONTAINER_IMAGE_REPOSITORY`, but the template provides no authentication or compatibility contract for Docker Hub, private registries, or custom Dockerfiles.
