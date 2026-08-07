After changing Rust code or configuration, run `mise run check` before finishing and make sure the check passes. If the check fails, try `mise run fix` first, then fix any remaining issues manually.

Use Cargo through the existing mise task interface. Regenerate `Cargo.lock` with Cargo commands instead of editing it manually, and keep portable CI behavior in `mise.toml` or `mise.ci.toml` rather than duplicating it in GitHub Actions.

This project is in early development and does not require backward compatibility yet. When a cleaner long-term design requires an incompatible change, make the change deliberately instead of preserving compatibility through extra complexity.
