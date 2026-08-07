#![forbid(unsafe_code)]

fn main() {
    println!("{}", {{RUST_CRATE_IDENT}}::greeting("{{CARGO_PACKAGE}}"));
}
