from __future__ import annotations

import hashlib
import json
import os
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.godot.artifacts import web_build
from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from infrastructure.godot.artifacts.web_build import (
    current_source_fingerprint,
    current_species_catalog_digest,
    patch_web_entry_for_lan_http,
    runtime_is_current,
)


def _write_runtime(directory: Path, fingerprint: str) -> None:
    directory.mkdir()
    files = {}
    for suffix in (".html", ".js", ".wasm", ".pck"):
        path = directory / f"elfienest{suffix}"
        path.write_bytes(b"runtime")
        files[path.name] = {
            "bytes": len(b"runtime"),
            "sha256": hashlib.sha256(b"runtime").hexdigest(),
        }
    (directory / "build-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "files": files,
                "source_fingerprint": fingerprint,
                "species_catalog_digest": current_species_catalog_digest(),
                "species_package_ids": ["myelle", "saevi", "tovren"],
                "export_boundary": export_boundary_manifest(),
            }
        ),
        encoding="utf-8",
    )


def test_runtime_is_current_when_manifest_matches_source_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setattr(
        "infrastructure.godot.artifacts.web_build.GODOT_PROJECT", project
    )
    output = tmp_path / "runtime"
    _write_runtime(output, current_source_fingerprint())

    assert runtime_is_current(output) is True


@pytest.mark.parametrize("suffix", [".glb", ".instances.bin"])
def test_export_rejects_unresolved_lfs_assets_before_starting_godot(
    tmp_path: Path, monkeypatch, capsys, suffix: str
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    asset = project / ("estate" + suffix)
    asset.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 100\n"
    )
    monkeypatch.setattr(web_build, "GODOT_PROJECT", project)
    monkeypatch.setattr(
        web_build,
        "_find_godot",
        lambda *_: pytest.fail("Unresolved assets must fail before Godot starts"),
    )
    assert (
        web_build._export_runtime(tmp_path / "runtime", None, False, godot_runner=None)
        == 1
    )
    assert "git lfs pull" in capsys.readouterr().out


def test_resolved_binary_assets_are_not_lfs_pointers(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "estate.glb").write_bytes(b"glTF" + bytes(256))
    monkeypatch.setattr(web_build, "GODOT_PROJECT", tmp_path)
    assert web_build._unresolved_lfs_assets() == []


def test_runtime_is_stale_when_godot_source_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    scene = project / "main.tscn"
    scene.write_text('[node name="Nest"]\n', encoding="utf-8")
    monkeypatch.setattr(
        "infrastructure.godot.artifacts.web_build.GODOT_PROJECT", project
    )
    output = tmp_path / "runtime"
    _write_runtime(output, current_source_fingerprint())
    scene.write_text('[node name="ChangedNest"]\n', encoding="utf-8")

    assert runtime_is_current(output) is False


def test_patch_web_entry_for_lan_http_adds_scoped_godot_compatibility(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "elfienest.html"
    entry.write_text(
        '<script src="elfienest.js"></script>\n'
        "const GODOT_CONFIG = {};\n"
        "const GODOT_THREADS_ENABLED = false;\n"
        "\tconst missing = Engine.getMissingFeatures({\n"
        "\t\tthreads: GODOT_THREADS_ENABLED,\n"
        "\t});\n",
        encoding="utf-8",
    )

    patch_web_entry_for_lan_http(entry)
    patched = entry.read_text(encoding="utf-8")

    assert "elfienest:lan-http-compatibility" in patched
    assert "audioWorklet" in patched
    assert "!('audioWorklet' in window.AudioContext.prototype)" in patched
    assert "!window.AudioContext.prototype.audioWorklet" not in patched
    assert "addModule" in patched
    assert "elfienest:webgl-canvas-capture" in patched
    assert "preserveDrawingBuffer: true" in patched
    assert "powerPreference: 'high-performance'" in patched

    # A substring check alone accepts JavaScript emitted as visible body text.
    class ScriptCollector(HTMLParser):
        in_script = False

        def __init__(self) -> None:
            super().__init__()
            self.scripts: list[str] = []

        def handle_starttag(self, tag, attrs) -> None:
            if tag == "script":
                self.in_script = True

        def handle_endtag(self, tag) -> None:
            if tag == "script":
                self.in_script = False

        def handle_data(self, data) -> None:
            if self.in_script:
                self.scripts.append(data)

    parsed = ScriptCollector()
    parsed.feed(patched)
    assert any("elfienest:webgl-canvas-capture" in script for script in parsed.scripts)
    assert patched.index("patchGodotCanvasCapture") < patched.index(
        '<script src="elfienest.js">'
    )
    assert "window.location.protocol !== 'http:'" in patched
    assert (
        "feature === 'Secure Context - Check web server configuration (use HTTPS)'"
        in patched
    )
    assert ".filter((feature) =>" in patched

    patch_web_entry_for_lan_http(entry)
    assert entry.read_text(encoding="utf-8") == patched


def test_capture_patch_revision_invalidates_existing_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    monkeypatch.setattr(web_build, "GODOT_PROJECT", project)
    current_revision = web_build.CANVAS_CAPTURE_VERSION
    monkeypatch.setattr(web_build, "CANVAS_CAPTURE_VERSION", "canvas-capture-v1")
    old_fingerprint = current_source_fingerprint()
    monkeypatch.setattr(web_build, "CANVAS_CAPTURE_VERSION", current_revision)
    assert current_source_fingerprint() != old_fingerprint


def test_web_export_imports_before_species_validation_and_publishes_after_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[str] = []
    output = tmp_path / "runtime"

    def fake_export(*args, **kwargs):
        del args, kwargs
        events.append("export")
        entry = output.parent / ".runtime.staging" / "elfienest.html"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            '<script src="elfienest.js"></script>\n'
            "const GODOT_CONFIG = {};\n"
            "const engine = new Engine(GODOT_CONFIG);\n"
            "const GODOT_THREADS_ENABLED = false;\n"
            "\tconst missing = Engine.getMissingFeatures({\n"
            "\t\tthreads: GODOT_THREADS_ENABLED,\n"
            "\t});\n",
            encoding="utf-8",
        )
        for suffix in (".js", ".wasm", ".pck"):
            (entry.parent / f"elfienest{suffix}").write_bytes(b"runtime")
        entry.with_suffix(".js").write_text(
            "var GodotFS={copy_to_fs:function(path,buffer){"
            "FS.writeFile(path,new Uint8Array(buffer))}};\n"
            "me.rtenv['copyToFS'](file.path, file.buffer);\n"
            "const tr = getTrackedResponse(response, tracker[file]);\n"
        )
        return SimpleNamespace(
            exit_code=0,
            crashed=False,
            stdout="",
            stderr="",
        )

    def fake_validate(*args, **kwargs):
        del args, kwargs
        events.append("validate")
        return ("tovren", "saevi")

    monkeypatch.setattr(
        web_build,
        "build_authority_pack",
        lambda source, destination: destination.write_bytes(b"physical-pack"),
    )
    monkeypatch.setattr(web_build, "run_headless", fake_export)
    monkeypatch.setattr(web_build, "validate_source_species_packages", fake_validate)

    assert (
        web_build._export_runtime_locked(
            output,
            Path("/fake/godot"),
            "4.7",
            "4.7",
            ("tovren", "saevi"),
            lambda **kwargs: None,
        )
        == 0
    )
    assert events == ["export", "validate"]
    assert (output / "build-manifest.json").is_file()


def test_build_lock_recovers_an_unowned_stale_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "runtime"
    lock_path = tmp_path / ".runtime.lock"
    lock_path.write_text("7982", encoding="ascii")
    ticks = iter((0.0, 121.0))
    monkeypatch.setattr(web_build.time, "monotonic", ticks.__next__)

    with web_build._build_lock(output):
        assert lock_path.read_text(encoding="ascii") == str(os.getpid())


def test_build_lock_still_rejects_a_concurrent_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "runtime"

    with web_build._build_lock(output):
        ticks = iter((0.0, 121.0))
        monkeypatch.setattr(web_build.time, "monotonic", ticks.__next__)
        with pytest.raises(RuntimeError, match="build lock timeout"):
            with web_build._build_lock(output):
                pass


def test_pack_loader_transfers_only_immutable_startup_pack(tmp_path: Path) -> None:
    import subprocess

    engine = tmp_path / "elfienest.js"
    engine.write_text(
        "var GodotFS={copy_to_fs:function(path,buffer){"
        "FS.writeFile(path,new Uint8Array(buffer))}};\n"
        "var me={rtenv:{copyToFS:GodotFS.copy_to_fs}};\n"
        "function preload(file){me.rtenv['copyToFS'](file.path, file.buffer);}\n"
    )
    web_build.patch_web_pack_ownership(engine)
    patched = engine.read_text()
    web_build.patch_web_pack_ownership(engine)
    assert engine.read_text() == patched
    script = (
        "const assert=require('node:assert/strict');\n"
        "const files={};const FS={writeFile(path,data,options={}){"
        "files[path]=options.canOwn?data:new Uint8Array(data);}};\n"
        + patched
        + "const pack=new Uint8Array([1,2,3]);"
        "preload({path:'elfienest.pck',buffer:pack.buffer});"
        "assert.equal(files['elfienest.pck'].buffer,pack.buffer);"
        "assert.deepEqual(Array.from(files['elfienest.pck']),[1,2,3]);"
        "const input=new Uint8Array([4,5]);"
        "preload({path:'save.dat',buffer:input.buffer});input[0]=9;"
        "assert.deepEqual(Array.from(files['save.dat']),[4,5]);"
        "GodotFS.copy_to_fs('manual.pck',input.buffer);input[0]=8;"
        "assert.deepEqual(Array.from(files['manual.pck']),[9,5]);"
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


def test_pack_loader_rejects_unknown_template_without_partial_write(
    tmp_path: Path,
) -> None:
    engine = tmp_path / "elfienest.js"
    engine.write_text("unknown template")
    with pytest.raises(RuntimeError, match="pack ownership"):
        web_build.patch_web_pack_ownership(engine)
    assert engine.read_text() == "unknown template"


def test_pack_download_streams_into_one_exact_buffer(tmp_path: Path) -> None:
    import subprocess

    engine = tmp_path / "elfienest.js"
    engine.write_text(
        "function download(response,tracker,file,fileSize,raw){\n"
        "const tr = getTrackedResponse(response, tracker[file]);\n"
        "return tr.arrayBuffer();\n}"
    )
    web_build.patch_web_pack_download(engine)
    patched = engine.read_text()
    web_build.patch_web_pack_download(engine)
    assert engine.read_text() == patched
    script = (
        "const assert=require('node:assert/strict');\n"
        + patched
        + r"""
function response(chunks) {
 let released=false, cancelled=false;
 return {get released(){return released}, get cancelled(){return cancelled},
 body:{getReader(){return {async read(){return chunks.length ?
 {value:new Uint8Array(chunks.shift()),done:false}:{done:true}},
 releaseLock(){released=true},async cancel(){cancelled=true}}}}};
}
(async()=>{
 const tracker={'scene.pck':{loaded:0,done:false}};
 const input=response([[1,2],[3],[4,5]]);
 const result=await download(input,tracker,'scene.pck',5,false);
 assert.deepEqual(Array.from(new Uint8Array(result)),[1,2,3,4,5]);
 assert.equal(input.released,true);assert.equal(tracker['scene.pck'].loaded,5);
 assert.equal(tracker['scene.pck'].done,true);
 for(const chunks of [[[1,2]],[[1,2,3,4]]]){
  const bad=response(chunks);
  await assert.rejects(download(bad,{'bad.pck':{loaded:0}},'bad.pck',3,false),/size/);
  assert.equal(bad.released,true);assert.equal(bad.cancelled,true);
 }
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


def test_authority_pack_selection_preserves_observer_package(tmp_path: Path) -> None:
    import subprocess

    entry = tmp_path / "elfienest.html"
    entry.write_text("const engine = new Engine(GODOT_CONFIG);")
    web_build.patch_web_authority_pack(entry, 123)
    script = (
        "const assert=require('node:assert/strict');"
        "function run(search){const window={location:{search}};"
        "const GODOT_CONFIG={fileSizes:{'elfienest.pck':456}};"
        "function Engine(config){Object.assign(this,config)};"
        + entry.read_text()
        + "return engine;}"
        "assert.equal(run('?mode=authority').mainPack,'elfienest-authority.pck');"
        "assert.equal(run('?mode=authority').fileSizes['elfienest-authority.pck'],123);"
        "assert.equal(run('?observer=product').mainPack,undefined);"
        "assert.equal(run('').fileSizes['elfienest.pck'],456);"
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
