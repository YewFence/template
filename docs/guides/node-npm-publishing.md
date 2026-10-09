# Publishing to npm (Node)

This guide applies to Node projects with the `npm-publish` template capability enabled. After the first release, the project publishes to npm using trusted publishing (GitHub Actions OIDC): aube exchanges the workflow's OIDC token for a short-lived registry token and attaches a Sigstore provenance attestation, so no long-lived npm token is stored anywhere.

The npm package name is the `name` field in `package.json`, which the template sets to the repository name. If that name is taken on npm, change `name` before the first release. For a scoped package such as `@owner/name`, add `"publishConfig": { "access": "public" }` to `package.json`, or the registry creates it as restricted.

## First Release

1. Commit and push all changes from applying the template to `main`.

2. The Prepare Release workflow automatically opens a release PR. Based on the commits on `main`, it updates:
   - the version in `package.json`;
   - `CHANGELOG.md`.

   For the first release, treat the `package.json` version in this release PR as the source of truth. Publishing `0.1.0` directly from the current `main` is not recommended — the GitHub Release and npm versions can drift out of sync.

3. Wait for the release PR's regular CI to pass and confirm the content is ready to merge, but do not merge yet. Check out the release branch locally:

   ```bash
   git fetch origin release
   git switch --detach origin/release
   ```

4. Authenticate aube against npm. `aube login` stores the session in user-level npm configuration and completes any two-factor challenge during login:

   ```bash
   aube login
   ```

5. Run the full package check locally without uploading:

   ```bash
   mise -E ci run npm:package:check
   ```

6. Set the environment and publish the first release with the project's existing mise task:

   ```bash
   export RELEASE_TAG='v0.1.0'      # the tag from the release PR; usually v0.1.0 for a new project
   export RELEASE_VERSION='0.1.0'   # the version from the release PR, without the v
   mise -E ci run npm:publish
   ```

   The publish script skips the provenance attestation outside CI, because no OIDC token exists locally. If the account requires an OTP for publishes and the publish step asks for one, publish the already-verified checkout directly with `aube publish --otp <code> --no-git-checks`.

7. Clean up and return to `main`:

   ```bash
   unset RELEASE_TAG RELEASE_VERSION
   git switch main
   ```

8. On [npmjs.com](https://www.npmjs.com/), open the package → Settings → Trusted Publisher → GitHub Actions, and fill in:

   ```text
   Repository owner: YourName
   Repository name: YourRepo
   Workflow filename: release.yml
   Environment: npm
   ```

   npm only offers trusted publishing configuration for a package that already exists, which is why the first release above uses a local login instead.

9. Merge the release PR into `main`.

The Release workflow triggers on `main`, publishes the GitHub Release, detects the already-published package version, and skips the npm upload.

## Later Releases

The Release workflow publishes the GitHub Release first, then publishes the package to npm. It derives the prerelease status from the SemVer tag and requires the `package.json` version to match the tag version exactly.

If the npm publish fails after the GitHub Release has been created, fix the problem reported by the workflow and re-run the same Release workflow. An identical, already-published package version counts as done — re-running does not upload it again.
