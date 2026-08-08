# crates.io Publishing

This project uses crates.io trusted publishing after its first release.

## First Release

1. Create the crate on crates.io with a one-time manual `cargo publish` using a temporary or fine-grained crates.io API token.
2. Configure the crates.io trusted publisher with GitHub owner `{{GITHUB_OWNER}}`, repository `{{REPO_NAME}}`, workflow file `release.yml`, and environment `crates-io`.
3. Create the GitHub `crates-io` environment. Choose its protection rules for this project.

Do not add a long-lived crates.io token secret to GitHub after bootstrap.

## Later Releases

The Release workflow publishes a GitHub Release first, then publishes the matching crate version to crates.io. It derives prerelease status from the SemVer tag and requires the crate version to match that tag exactly.

When a crates.io publish fails after the GitHub Release exists, fix the reported cause and rerun the same Release workflow. An already published exact crate version is treated as complete, so reruns do not upload it again.
