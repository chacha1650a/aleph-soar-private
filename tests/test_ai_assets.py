import json
from pathlib import Path
import re
import shutil
import tomllib

import pytest
import yaml

from tools import sync_ai_assets as sync


def copy_sources(destination):
    shutil.copytree(sync.ROOT / ".agents", destination / ".agents")
    shutil.copytree(sync.ROOT / "ai/roles", destination / "ai/roles")


def test_committed_adapters_match_canonical_sources():
    assert sync.synchronize(check=True) > 0
    for role in (sync.ROOT / "ai/roles").glob("*.md"):
        name, description, body = sync.read_role(role)
        config = tomllib.loads((sync.ROOT / f".codex/agents/{name}.toml").read_text(encoding="utf-8"))
        assert config == {"name": name, "description": description, "developer_instructions": body}


def test_source_change_is_detected_and_regenerated(tmp_path):
    copy_sources(tmp_path)
    sync.synchronize(tmp_path)
    role = tmp_path / "ai/roles/aleph-backend.md"
    role.write_text(role.read_text(encoding="utf-8") + "\nAdditional scoped instruction.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="out of sync"):
        sync.synchronize(tmp_path, check=True)
    sync.synchronize(tmp_path)
    sync.synchronize(tmp_path, check=True)


def test_unmanaged_files_and_outside_paths_are_not_overwritten(tmp_path):
    copy_sources(tmp_path)
    target = tmp_path / ".claude/agents/aleph-backend.md"
    target.parent.mkdir(parents=True)
    target.write_text("User-owned content", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanaged"):
        sync.synchronize(tmp_path)
    assert target.read_text(encoding="utf-8") == "User-owned content"
    (tmp_path / sync.MANIFEST).write_text(json.dumps(["../../outside.md"]), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid managed"):
        sync.synchronize(tmp_path)


def test_removed_canonical_role_removes_only_its_managed_adapters(tmp_path):
    copy_sources(tmp_path)
    sync.synchronize(tmp_path)
    unrelated = tmp_path / ".claude/agents/user-role.md"
    unrelated.write_text("Keep this", encoding="utf-8")
    (tmp_path / "ai/roles/aleph-backend.md").unlink()
    sync.synchronize(tmp_path)
    assert not (tmp_path / ".codex/agents/aleph-backend.toml").exists()
    assert unrelated.read_text(encoding="utf-8") == "Keep this"


def test_skills_have_discoverable_metadata_and_resolvable_references():
    for skill in (sync.ROOT / ".agents/skills").glob("*/SKILL.md"):
        content = skill.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\n(.*?)\n---", content, re.S)
        assert frontmatter is not None
        metadata = yaml.safe_load(frontmatter[1])
        assert metadata["name"] == skill.parent.name
        assert metadata["description"].strip()
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            if "://" not in target:
                assert (skill.parent / target).is_file(), target
