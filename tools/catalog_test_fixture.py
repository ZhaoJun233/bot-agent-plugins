"""Fixed first-wave inputs for single-version catalog contract tests."""
import json
import tempfile
from pathlib import Path

from generate_catalog import ROOT, synchronize

_FIRST_WAVE_BUILTINS = (
    ("music", "点歌与音乐分享", "音频与媒体"),
    ("voice", "语音合成", "音频与媒体"),
    ("stickers", "表情包", "会话互动"),
    ("poke", "戳一戳", "会话互动"),
    ("vibes", "群聊氛围", "会话策略"),
    ("profiles", "人物画像", "记忆与隐私"),
    ("websearch", "联网研究与链接摘要", "检索与工具"),
    ("token-quota", "Token 配额", "用量与治理"),
)


def _builtin_entry(slug, name, category):
    return {
        "Id": f"preset.feature.{slug}",
        "Version": "1.0.0",
        "PackageSha256": None,
        "Metadata": {
            "Author": "Bot Agent Contributors",
            "Repository": "https://github.com/ZhaoJun233/bot-agent",
            "License": "MIT",
            "Runtime": "builtin",
            "SourceKind": "builtin",
            "Changelog": "1.0.0：随宿主内置提供；合成夹具条目。",
            "Maintenance": "随宿主维护",
            "Compatibility": "仅对当前宿主实际注册的同 ID、同版本预设展示；不可独立安装。",
            "PermissionNotes": "没有独立包权限清单；实际权限由宿主配置与工具策略控制。",
            "Review": {
                "Status": "unreviewed",
                "Version": "1.0.0",
                "Sha256": None,
                "Notes": "随宿主发布，不代表独立插件包已经通过安全审核。",
            },
            "Name": name,
            "Category": category,
            "Summary": f"{name}内置能力入口。",
            "Description": f"宿主内置 {name} 能力的配置与开关入口。",
            "Usage": f"在配置入口启用并按宿主策略使用 {name}。",
            "Configuration": f"在宿主配置界面管理 {name} 相关设置。",
            "RiskNotice": "实际行为与访问边界由宿主负责。",
            "Tags": [category, "内置"],
        },
    }


def first_wave_catalog(test_case):
    temporary = tempfile.TemporaryDirectory()
    test_case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    catalog_dir = root / "catalog"
    catalog_dir.mkdir(parents=True)
    builtins = {"SchemaVersion": 1, "Entries": [_builtin_entry(*row) for row in _FIRST_WAVE_BUILTINS]}
    (catalog_dir / "builtins.json").write_text(
        json.dumps(builtins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    submission = Path("submissions/community.example.hello/1.0.0.json")
    (root / submission).parent.mkdir(parents=True)
    (root / submission).write_text((ROOT / submission).read_text(encoding="utf-8"), encoding="utf-8")
    ledger = root / "governance/ledger.json"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({"schemaVersion": 1,
                                "generatedAt": "2026-11-06T00:00:00Z",
                                "entries": []}), encoding="utf-8")
    synchronize(root)
    return root
