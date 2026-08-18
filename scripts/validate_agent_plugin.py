#!/usr/bin/env python3
"""Validate the reviewed Codex-safe Caveman Agent Plugins package."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "agent-plugins" / "caveman"
ROLLBACK_SKILL_ROOT = REPO_ROOT / "codex-skills" / "caveman"
UPSTREAM_PLUGIN_ROOT = REPO_ROOT / "plugins" / "caveman"
PLUGIN_NAME = "caveman"
SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
MANIFEST_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
REQUIRED_MANIFEST_FIELDS = MANIFEST_FIELDS
AUTHOR_FIELDS = {"name", "email", "url"}
INTERFACE_FIELDS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "defaultPrompt",
    "brandColor",
    "composerIcon",
    "logo",
    "logoDark",
    "screenshots",
}
REQUIRED_INTERFACE_FIELDS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "defaultPrompt",
}

# Reviewed against upstream plugins/caveman at Git tree
# 88a7d2d2e76e57c37e5275a9040ae7abc44837bf. A changed digest requires a new
# adapter review; the portable package must never silently inherit upstream's
# auto-trigger and progress-suppression behavior.
UPSTREAM_PLUGIN_TREE_SHA256 = "261c12a4d0046dc9a8a75f3670979f5327b4a499ffc047103035eae1ef6be21d"


class ValidationError(Exception):
    """A package invariant failed."""


def fail(message: str) -> None:
    raise ValidationError(message)


def display(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid JSON from {display(path)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{display(path)} must contain a JSON object")
    return value


def require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    return value


def require_https(value: Any, field: str) -> None:
    text = require_nonempty_string(value, field)
    if not text.startswith("https://"):
        fail(f"{field} must be an https URL")


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    fields = set(manifest)
    unknown = fields - MANIFEST_FIELDS
    missing = REQUIRED_MANIFEST_FIELDS - fields
    if unknown:
        fail(f"plugin.json has unsupported fields: {sorted(unknown)}")
    if missing:
        fail(f"plugin.json is missing required fields: {sorted(missing)}")
    if manifest["$schema"] != SCHEMA_URL:
        fail("plugin.json must target the Agent Plugins 1.0.0 schema")
    if manifest["name"] != PLUGIN_NAME:
        fail(f"plugin.json name must be {PLUGIN_NAME!r}")
    version = require_nonempty_string(manifest["version"], "version")
    if not SEMVER.fullmatch(version):
        fail("version must be valid semantic versioning")
    require_nonempty_string(manifest["description"], "description")
    if manifest["license"] != "MIT":
        fail("license must remain MIT and match the packaged LICENSE text")
    require_https(manifest["homepage"], "homepage")
    require_https(manifest["repository"], "repository")

    author = manifest["author"]
    if not isinstance(author, dict) or not set(author) <= AUTHOR_FIELDS:
        fail("author must be a closed object containing only name, email, and url")
    require_nonempty_string(author.get("name"), "author.name")
    if "email" in author:
        require_nonempty_string(author["email"], "author.email")
    if "url" in author:
        require_https(author["url"], "author.url")

    keywords = manifest["keywords"]
    if (
        not isinstance(keywords, list)
        or not keywords
        or any(not isinstance(item, str) or not item.strip() for item in keywords)
        or len(set(keywords)) != len(keywords)
    ):
        fail("keywords must be a non-empty list of unique, non-empty strings")

    extensions = manifest["extensions"]
    if not isinstance(extensions, dict) or set(extensions) != {"com.openai"}:
        fail("extensions must contain only com.openai")
    openai_extension = extensions["com.openai"]
    if not isinstance(openai_extension, dict) or set(openai_extension) != {"interface"}:
        fail("extensions.com.openai must contain only interface")
    interface = openai_extension["interface"]
    if not isinstance(interface, dict):
        fail("extensions.com.openai.interface must be an object")
    unknown_interface = set(interface) - INTERFACE_FIELDS
    missing_interface = REQUIRED_INTERFACE_FIELDS - set(interface)
    if unknown_interface:
        fail(f"interface has unsupported fields: {sorted(unknown_interface)}")
    if missing_interface:
        fail(f"interface is missing required fields: {sorted(missing_interface)}")
    for field in REQUIRED_INTERFACE_FIELDS - {"capabilities", "defaultPrompt"}:
        require_nonempty_string(interface[field], f"interface.{field}")
    if interface["developerName"] != author["name"]:
        fail("interface.developerName must exactly match author.name")
    capabilities = interface["capabilities"]
    if not isinstance(capabilities, list) or not capabilities or any(
        not isinstance(item, str) or not item.strip() for item in capabilities
    ) or len(set(capabilities)) != len(capabilities):
        fail("interface.capabilities must be a non-empty list of unique strings")
    prompts = interface["defaultPrompt"]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3 or any(
        not isinstance(item, str) or not item.strip() or len(item) > 128 for item in prompts
    ) or len(set(prompts)) != len(prompts):
        fail("interface.defaultPrompt must contain one to three strings of at most 128 characters")
    if not any(f"${PLUGIN_NAME}" in item for item in prompts):
        fail(f"interface.defaultPrompt must explicitly mention ${PLUGIN_NAME}")
    for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        if field in interface:
            require_https(interface[field], f"interface.{field}")
    return interface


def validate_legacy_overlay(manifest: dict[str, Any], interface: dict[str, Any]) -> None:
    overlay_path = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
    overlay = load_object(overlay_path)
    expected = {
        key: value
        for key, value in manifest.items()
        if key not in {"$schema", "extensions"}
    }
    expected["skills"] = "./skills/"
    expected["interface"] = interface
    if overlay != expected:
        fail(f"{display(overlay_path)} is not the full deterministic legacy overlay")
    expected_bytes = (json.dumps(expected, indent=2, ensure_ascii=False) + "\n").encode()
    if overlay_path.read_bytes() != expected_bytes:
        fail(f"{display(overlay_path)} serialization drifted from the deterministic overlay")


def frontmatter_value(skill_path: Path, key: str) -> str:
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        fail(f"{display(skill_path)} must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"{display(skill_path)} has unterminated YAML frontmatter")
    matches = [
        line.split(":", 1)[1].strip()
        for line in lines[1:end]
        if line.startswith(f"{key}:")
    ]
    if len(matches) != 1 or not matches[0]:
        fail(f"{display(skill_path)} must define one non-empty {key}")
    return matches[0]


def explicit_policy_value(yaml_path: Path) -> str | None:
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    in_policy = False
    values: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if indent == 0:
            in_policy = stripped == "policy:"
            continue
        if in_policy and stripped.startswith("allow_implicit_invocation:"):
            values.append(stripped.split(":", 1)[1].strip().split(" #", 1)[0])
    if len(values) > 1:
        fail(f"{display(yaml_path)} defines allow_implicit_invocation more than once")
    return values[0] if values else None


def validate_skill_layout() -> None:
    skills_root = PLUGIN_ROOT / "skills"
    if not skills_root.is_dir():
        fail(f"{display(skills_root)} must be a directory")
    children = sorted(skills_root.iterdir(), key=lambda path: path.name)
    if [child.name for child in children] != [PLUGIN_NAME] or not children[0].is_dir():
        fail(f"{display(skills_root)} must contain exactly the direct {PLUGIN_NAME}/ skill directory")
    skill_root = children[0]
    skill_path = skill_root / "SKILL.md"
    if not skill_path.is_file():
        fail(f"{display(skill_path)} is required")
    if frontmatter_value(skill_path, "name") != PLUGIN_NAME:
        fail(f"{display(skill_path)} name must match its directory")
    description = frontmatter_value(skill_path, "description")
    if not description.startswith("Explicit invocation only."):
        fail(f"{display(skill_path)} must retain the explicit-only activation contract")
    skill_text = skill_path.read_text(encoding="utf-8")
    if "Activating Caveman changes response style only" not in skill_text:
        fail(f"{display(skill_path)} must retain the side-effect authority boundary")
    if "Never add words or break correct grammar merely to sound caveman." not in skill_text:
        fail(f"{display(skill_path)} must require compression rather than performative expansion")
    if "follow that request outside Caveman mode" not in skill_text:
        fail(f"{display(skill_path)} must preserve explicit user override authority")
    if "defect, ticket, or bug-report text" not in skill_text:
        fail(f"{display(skill_path)} must keep all durable issue artifacts in normal prose")
    if "no reviewed aggregate output-reduction figure" not in skill_text or "65%" in skill_text:
        fail(f"{display(skill_path)} must not restore the withdrawn aggregate savings claim")
    if "This is an unofficial Codex adaptation" not in skill_text:
        fail(f"{display(skill_path)} must retain the unofficial-adapter disclosure")
    trademark_notice = skill_root / "TRADEMARK_NOTICE.md"
    if not trademark_notice.is_file():
        fail(f"{display(trademark_notice)} is required")
    notice_text = trademark_notice.read_text(encoding="utf-8")
    if "not endorsed by, affiliated" not in notice_text or "logos are not distributed" not in notice_text:
        fail(f"{display(trademark_notice)} must retain the trademark and no-endorsement notice")
    assets_root = skill_root / "assets"
    if assets_root.exists() and any(assets_root.rglob("*")):
        fail(f"{display(assets_root)} must remain empty; upstream logos are not licensed for adapter branding")
    agents_path = skill_root / "agents" / "openai.yaml"
    if not agents_path.is_file():
        fail(f"{display(agents_path)} is required")
    if explicit_policy_value(agents_path) != "false":
        fail(f"{display(agents_path)} must set policy.allow_implicit_invocation to false")
    if f"${PLUGIN_NAME}" not in agents_path.read_text(encoding="utf-8"):
        fail(f"{display(agents_path)} default prompt must mention ${PLUGIN_NAME}")


def validate_license() -> None:
    package_license = PLUGIN_ROOT / "LICENSE"
    try:
        resolved = package_license.resolve(strict=True)
        resolved.relative_to(PLUGIN_ROOT.resolve())
    except (FileNotFoundError, RuntimeError, ValueError):
        fail(f"{display(package_license)} must resolve inside the plugin root")
    if not resolved.is_file() or not resolved.read_bytes().strip():
        fail(f"{display(package_license)} must be a non-empty regular file")
    repo_license = REPO_ROOT / "LICENSE"
    if not repo_license.is_file() or package_license.read_bytes() != repo_license.read_bytes():
        fail(f"{display(package_license)} must be byte-for-byte identical to the repository LICENSE")


def validate_provenance() -> None:
    provenance = load_object(PLUGIN_ROOT / "PROVENANCE.json")
    expected = {
        "schema_version": 1,
        "package": "caveman",
        "relationship": "reviewed_codex_adapter",
        "adapter_maintainer": "Andrew Fai",
        "upstream": {
            "repository": "https://github.com/JuliusBrussee/caveman",
            "reviewed_commit": "766dce6b1394ebb56a3090748d5a0240a5aefb36",
            "source_path": "plugins/caveman/skills/caveman",
            "source_license": "MIT",
        },
        "scope": {
            "included": "Response-style skill instructions and Codex interface metadata only.",
            "excluded": "All Caveman Engine, proxy, cache, rewriter, browser, MCP, telemetry, cloud, binary, and other BSL-1.1 runtime surfaces.",
        },
        "review_policy": "Upstream changes are reviewed selectively and never merged into this adapter automatically.",
    }
    if provenance != expected:
        fail(f"{display(PLUGIN_ROOT / 'PROVENANCE.json')} must retain the reviewed MIT-only source boundary")


def validate_no_symlinks(root: Path) -> None:
    candidates = [root, *root.rglob("*")]
    for path in candidates:
        if path.is_symlink():
            fail(f"symlinks are not permitted in the package: {display(path)}")


def directory_entries(root: Path) -> dict[str, tuple[str, bytes]]:
    entries: dict[str, tuple[str, bytes]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries[relative] = ("symlink", path.readlink().as_posix().encode())
        elif path.is_file():
            entries[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            entries[relative] = ("directory", b"")
        else:
            fail(f"unsupported filesystem entry in package: {display(path)}")
    return entries


def validate_rollback_parity() -> None:
    packaged_skill = PLUGIN_ROOT / "skills" / PLUGIN_NAME
    packaged_entries = directory_entries(packaged_skill)
    rollback_entries = directory_entries(ROLLBACK_SKILL_ROOT)
    if packaged_entries != rollback_entries:
        packaged_paths = set(packaged_entries)
        rollback_paths = set(rollback_entries)
        details = []
        if packaged_paths - rollback_paths:
            details.append(f"package-only={sorted(packaged_paths - rollback_paths)}")
        if rollback_paths - packaged_paths:
            details.append(f"rollback-only={sorted(rollback_paths - packaged_paths)}")
        changed = sorted(
            path
            for path in packaged_paths & rollback_paths
            if packaged_entries[path] != rollback_entries[path]
        )
        if changed:
            details.append(f"changed={changed}")
        fail("packaged and rollback Caveman skills are not byte-for-byte identical: " + "; ".join(details))


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, (kind, content) in directory_entries(root).items():
        digest.update(kind[0].upper().encode())
        digest.update(b"\0")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_reviewed_upstream_assumptions() -> None:
    if not UPSTREAM_PLUGIN_ROOT.is_dir() or UPSTREAM_PLUGIN_ROOT.is_symlink():
        fail("plugins/caveman must remain the independent, regular upstream plugin directory")
    actual_digest = tree_digest(UPSTREAM_PLUGIN_ROOT)
    if actual_digest != UPSTREAM_PLUGIN_TREE_SHA256:
        fail(
            "plugins/caveman changed after the Codex-safe adapter review; "
            "review upstream behavior before updating the pinned tree digest"
        )
    upstream_skill = UPSTREAM_PLUGIN_ROOT / "skills" / PLUGIN_NAME
    if directory_entries(upstream_skill) == directory_entries(PLUGIN_ROOT / "skills" / PLUGIN_NAME):
        fail("the portable package must remain the reviewed Codex adapter, not upstream plugins/caveman")
    upstream_agents = upstream_skill / "agents" / "openai.yaml"
    if explicit_policy_value(upstream_agents) == "false":
        fail("upstream activation assumptions changed; re-review before updating the adapter")


def validate_no_mcp() -> None:
    for path in (PLUGIN_ROOT / "mcp.json", PLUGIN_ROOT / ".mcp.json"):
        if path.exists() or path.is_symlink():
            fail(f"MCP configuration is not permitted: {display(path)}")
    for path in PLUGIN_ROOT.rglob("*"):
        if path.name.lower() in {"mcp.json", ".mcp.json"}:
            fail(f"MCP configuration is not permitted: {display(path)}")


def main() -> int:
    try:
        manifest = load_object(PLUGIN_ROOT / "plugin.json")
        interface = validate_manifest(manifest)
        validate_legacy_overlay(manifest, interface)
        validate_no_symlinks(PLUGIN_ROOT)
        validate_skill_layout()
        validate_license()
        validate_provenance()
        validate_rollback_parity()
        validate_reviewed_upstream_assumptions()
        validate_no_mcp()
    except ValidationError as exc:
        print(f"agent plugin validation failed: {exc}", file=sys.stderr)
        return 1
    print("agent plugin validation passed: caveman")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
