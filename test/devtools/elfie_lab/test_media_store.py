import os
from pathlib import Path

import pytest

from devtools.elfie_lab.media_store import (
    MAX_MEDIA_BYTES,
    ElfieLabMediaStore,
    InvalidElfieIdError,
    MediaNotFoundError,
    MediaTooLargeError,
    UnsupportedMediaError,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"fixture"
JPEG = b"\xff\xd8\xff\xe0" + b"fixture"
WEBP = b"RIFF\x0b\x00\x00\x00WEBP" + b"fixture"


@pytest.mark.parametrize(
    ("content", "expected_suffix", "expected_mime"),
    [
        (PNG, ".png", "image/png"),
        (JPEG, ".jpg", "image/jpeg"),
        (WEBP, ".webp", "image/webp"),
        (b"%PDF-1.7\nfixture", ".pdf", "application/pdf"),
        (b"plain text", ".txt", "text/plain"),
    ],
)
def test_store_identifies_supported_media_from_content(
    tmp_path: Path,
    content: bytes,
    expected_suffix: str,
    expected_mime: str,
) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)

    # When
    descriptor = store.store("elfie_alpha", content)

    # Then
    assert descriptor.mime_type == expected_mime
    assert descriptor.uri.endswith(expected_suffix)
    assert descriptor.size_bytes == len(content)
    assert descriptor.media_id == f"media_{descriptor.sha256}"
    assert str(tmp_path) not in descriptor.uri
    assert store.path_for("elfie_alpha", descriptor.media_id).read_bytes() == content


def test_store_deduplicates_repeated_content_by_sha256(tmp_path: Path) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)

    # When
    first = store.store("elfie_alpha", PNG)
    second = store.store("elfie_alpha", PNG)

    # Then
    assert second == first
    assert list((tmp_path / "media" / "elfie_alpha").iterdir()) == [
        store.path_for("elfie_alpha", first.media_id)
    ]


@pytest.mark.parametrize(
    "content",
    [
        b"data:image/png;base64,iVBORw0KGgo=",
        b"RIFF\x00\x00\x00\x00NOPE",
    ],
)
def test_store_rejects_malformed_or_encoded_input(
    tmp_path: Path, content: bytes
) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)

    # When / Then
    with pytest.raises(UnsupportedMediaError):
        store.store("elfie_alpha", content)
    assert not (tmp_path / "media" / "elfie_alpha").exists()


def test_store_rejects_content_above_five_mib(tmp_path: Path) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)
    content = b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_MEDIA_BYTES - 7)

    # When / Then
    with pytest.raises(MediaTooLargeError) as caught:
        store.store("elfie_alpha", content)
    assert caught.value.actual_bytes == MAX_MEDIA_BYTES + 1
    assert not (tmp_path / "media" / "elfie_alpha").exists()


def test_store_accepts_content_at_five_mib_boundary(tmp_path: Path) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)
    content = b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_MEDIA_BYTES - 8)

    # When
    descriptor = store.store("elfie_alpha", content)

    # Then
    assert descriptor.size_bytes == MAX_MEDIA_BYTES


@pytest.mark.parametrize("elfie_id", ["", "..", "../outside", "elfie/a", "精灵"])
def test_store_rejects_unsafe_elfie_ids(tmp_path: Path, elfie_id: str) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)

    # When / Then
    with pytest.raises(InvalidElfieIdError):
        store.store(elfie_id, PNG)
    assert not (tmp_path / "media").exists()


def test_store_ignores_spoofable_filename_and_mime_metadata(tmp_path: Path) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)
    content_claimed_as_jpeg = PNG

    # When
    descriptor = store.store("elfie_alpha", content_claimed_as_jpeg)

    # Then
    assert descriptor.mime_type == "image/png"
    assert descriptor.uri.endswith(".png")


def test_path_for_does_not_allow_cross_elfie_media_access(tmp_path: Path) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)
    descriptor = store.store("elfie_alpha", PNG)

    # When / Then
    with pytest.raises(MediaNotFoundError):
        store.path_for("elfie_beta", descriptor.media_id)


def test_atomic_write_removes_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    store = ElfieLabMediaStore(tmp_path)

    def fail_replace(_source: str, _destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    # When / Then
    with pytest.raises(OSError, match="injected replace failure"):
        store.store("elfie_alpha", PNG)
    assert list((tmp_path / "media" / "elfie_alpha").iterdir()) == []
