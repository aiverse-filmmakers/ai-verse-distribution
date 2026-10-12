from pathlib import Path

path = Path("tests/test_infrastructure_update_gate.py")
text = path.read_text(encoding="utf-8")
old = '''def release(raw=True):
    return ReleaseSet(
        id="core-target",
        profile="core",
        status="released",
        components=(
            ComponentRef(
                "ai-verse-example",
                "https://github.com/aiverse-filmmakers/AI-Verse-Example.git",
                REVISION,
                10,
            ),
        ),
        blockers=(),
        raw={"fixture": True} if raw else {},
    )
'''
new = '''def release(raw=True):
    component = ComponentRef(
        "ai-verse-example",
        "https://github.com/aiverse-filmmakers/AI-Verse-Example.git",
        REVISION,
        10,
    )
    raw_payload = (
        {
            "id": "core-target",
            "profile": "core",
            "status": "released",
            "components": [
                {
                    "id": component.id,
                    "repository": component.repository,
                    "revision": component.revision,
                    "install_order": component.install_order,
                }
            ],
            "blockers": [],
        }
        if raw
        else {}
    )
    return ReleaseSet(
        id="core-target",
        profile="core",
        status="released",
        components=(component,),
        blockers=(),
        raw=raw_payload,
    )
'''
if new in text:
    raise SystemExit(0)
if text.count(old) != 1:
    raise SystemExit(f"expected exactly one release helper anchor, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
