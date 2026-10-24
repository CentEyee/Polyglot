"""Deterministic C → Rust recipes. Preferred over the LLM when the change is mechanical."""
from __future__ import annotations

import re
from typing import Callable

Codemod = Callable[[str, dict[str, str]], str | None]


def c_null_to_option(source: str, args: dict[str, str]) -> str | None:
    """Very small mechanical pass used only as a hint inside already-Rust text."""
    if "NULL" not in source and "nullptr" not in source:
        return None
    out = source.replace("nullptr", "None").replace("NULL", "None")
    return out if out != source else None


def rename_ident(source: str, args: dict[str, str]) -> str | None:
    old, new = args.get("old"), args.get("new")
    if not old or not new:
        return None
    return re.sub(rf"\b{re.escape(old)}\b", new, source)


REGISTRY: dict[str, Codemod] = {
    "c_null_to_option": c_null_to_option,
    "rename_ident": rename_ident,
}


CRATE_TOML = """[package]
name = "{name}"
version = "0.1.0"
edition = "2021"

[lib]
path = "src/lib.rs"

[dependencies]
"""


def crate_name(instruction: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", instruction.lower()).strip("_")[:32] or "ported"
    if slug[0].isdigit():
        slug = "c_" + slug
    return slug


def ensure_rust_crate(root, modules: list[str]) -> list[str]:
    """Create rust-port scaffolding. Returns files written."""
    from pathlib import Path

    port = Path(root) / "rust-port"
    src = port / "src"
    src.mkdir(parents=True, exist_ok=True)
    written = []
    toml = port / "Cargo.toml"
    if not toml.exists():
        toml.write_text(CRATE_TOML.format(name=crate_name("c_to_rust_port")))
        written.append("rust-port/Cargo.toml")
    mods = sorted({Path(m).stem for m in modules if Path(m).stem != "lib"})
    lib = "//! Auto-generated C/C++ → Rust port crate.\n#![deny(unsafe_op_in_unsafe_fn)]\n\n"
    lib += "".join(f"pub mod {m};\n" for m in mods)
    (src / "lib.rs").write_text(lib)
    written.append("rust-port/src/lib.rs")
    return written
