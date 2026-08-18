# Publishing to crates.io (Rust)

This guide applies to Rust projects with the `crates-io-publish` template capability enabled. After the first release, the project publishes to crates.io using trusted publishing (GitHub Actions OIDC).

## First Release

1. Commit and push all changes from applying the template to `main`.

2. The Prepare Release workflow automatically opens a release PR. Based on the commits on `main`, it updates:
   - the version in `Cargo.toml`;
   - `Cargo.lock`;
   - `CHANGELOG.md`.

   For the first release, treat the `Cargo.toml` version in this release PR as the source of truth. Publishing `0.1.0` directly from the current `main` is not recommended — the GitHub Release and crates.io versions can drift out of sync.

3. Wait for the release PR's regular CI to pass and confirm the content is ready to merge, but do not merge yet. Check out the release branch locally:

   ```bash
   git fetch origin release
   git switch --detach origin/release
   ```

4. Log in to [crates.io](https://crates.io/), open the [API Tokens](https://crates.io/settings/tokens) page, and create a short-lived token. It needs permission to publish a new crate; name it something like `<crate-name>-bootstrap` and keep the expiry as short as possible.

5. Run the full package check locally without uploading:

   ```bash
   mise -E ci run crates-io:package:check
   ```

6. Put the token into the current terminal safely, without writing it into the shell history:

   ```bash
   printf 'crates.io token: '
   read -rs CARGO_REGISTRY_TOKEN
   printf '\n'
   export CARGO_REGISTRY_TOKEN
   ```

7. Set the environment and publish the first release with the project's existing mise task:

   ```bash
   export RELEASE_TAG='v0.1.0'      # the tag from the release PR; usually v0.1.0 for a new project
   export RELEASE_VERSION='0.1.0'   # the version from the release PR, without the v
   mise -E ci run crates-io:publish
   ```

8. Clean up the shell environment:

   ```bash
   unset CARGO_REGISTRY_TOKEN
   git switch main
   ```

9. On crates.io, open `<crate-name>` → Settings → Trusted Publishing → Add → GitHub, and fill in:

   ```text
   Repository owner: YourName
   Repository name: YourRepo
   Workflow filename: release.yml
   Environment: crates-io
   ```

   Optionally enable `Require trusted publishing for all new versions` so every later version must be published through the GitHub Release workflow.

10. Merge the release PR into `main`.

The Release workflow triggers on `main`, publishes the GitHub Release, detects the already-published crate version, and skips the crates.io upload.

## Later Releases

The Release workflow publishes the GitHub Release first, then publishes the crate to crates.io. It derives the prerelease status from the SemVer tag and requires the crate version to match the tag version exactly.

If the crates.io publish fails after the GitHub Release has been created, fix the problem reported by the workflow and re-run the same Release workflow. An identical, already-published crate version counts as done — re-running does not upload it again.
