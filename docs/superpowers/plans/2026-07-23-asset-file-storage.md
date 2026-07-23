# Asset File Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a replaceable local storage adapter, structurally validated uploads, asset photos/documents with secure download and immutable history rules, cleanup logging, and Alembic revision 007.

**Architecture:** Business services depend on a four-operation `StorageProvider` port, while `LocalStorageProvider` owns all filesystem path handling and returns opaque random keys. `StoredFile` owns physical-object metadata; `AssetAttachment` is an explicit asset foreign-key association and versioned lifecycle. Database state is authoritative for access, physical deletion is retryable, and no storage directory is exposed as a Flask/Nginx static path.

**Tech Stack:** Flask 3, Python 3.13, SQLAlchemy 2, Marshmallow 3, Alembic, Pillow, pillow-heif, olefile, pypdf, pathlib, zipfile, hashlib, pytest, Ruff, mypy.

All `git add`, convention-guard, and `git commit` commands in this plan run from the repository root. The convention guard scans staged files only, so every commit stages its exact file set before invoking `scripts/guard-conventions.sh`.

---

## Locked boundaries

- Revision 007 depends on revision 006 and creates no second Alembic head.
- Health/readiness registration is explicitly deferred until the final health-check phase.
- No Redis, Celery worker, MinIO SDK, antivirus daemon, `python-magic`, or generic polymorphic attachment table is introduced.
- Asset access always reuses `asset_access_service`; SELF includes both the responsible manager and current holder.
- `storage_key` is random and opaque. Original/display filenames never participate in a server path.
- Every persisted file is reopened/deleted through the provider named by `StoredFile.provider`; changing the configured default affects new uploads only.
- Ordinary documents are invalidated/replaced, never physically deleted. Only logically deleted Asset photos and expired temporary artifacts are cleanup candidates.
- Upload validation checks byte count, extension, container/signature, decompression limits, and image decode. Browser-provided MIME is not trusted.
- Download is a binary response rather than a JSON envelope, but every failure still uses `BusinessException` and the global error handler.
- Repository-designated scaffold changes never travel only as a separable commit: the runtime/config set (`requirements.txt`, `config.py`, profile files, test fixture, and any narrow mypy rule) and the later `app/__init__.py` CLI registration each use their own branch and independent stacked PR carrying the `scaffolding` label. The runtime/config PR merges into `feature/remaining-backend` before storage business Task 2 starts; Tasks 2–8 business commits merge next; the CLI-registration PR then merges before the final Task 9 gate. Pillow, pillow-heif, olefile, and pypdf versions are pinned only after real Python 3.13 install/import verification; no version is guessed in this plan.
- `back/storage` content is ignored by Git; only `back/storage/README.md` is tracked.
- The local adapter rejects static symlink parents/leaves and traversal. Its root must be writable only by the service account; without `openat`/`dirfd` primitives this plan does not claim protection from a malicious local user concurrently swapping path components.

## File map

Create:

- `back/app/storage/__init__.py`
- `back/app/storage/provider.py`
- `back/app/storage/local.py`
- `back/app/storage/factory.py`
- `back/app/storage/inspection.py`
- `back/app/storage/images.py`
- `back/app/storage/cli.py`
- `back/app/models/file_storage.py`
- `back/app/models/asset_attachment.py`
- `back/app/repositories/file_repository.py`
- `back/app/repositories/asset_attachment_repository.py`
- `back/app/services/asset_attachment_service.py`
- `back/app/services/storage_cleanup_service.py`
- `back/app/schemas/asset_attachment.py`
- `back/app/api/asset_attachments.py`
- `back/migrations/versions/007_asset_file_storage.py`
- `back/storage/README.md`
- `back/tests/test_storage_provider.py`
- `back/tests/test_storage_configuration.py`
- `back/tests/test_file_inspection.py`
- `back/tests/test_asset_attachment_models.py`
- `back/tests/test_asset_attachments.py`
- `back/tests/test_storage_cleanup.py`
- `back/tests/test_file_storage_migration.py`

Modify:

- `back/requirements.txt`
- `back/config.py`
- `back/mypy.ini` only when the post-install probe proves a dependency lacks typed metadata; any suppression is module-scoped.
- `back/.env.dev`
- `back/.env.prod`
- `.gitignore`
- `back/app/enums/__init__.py`
- model/repository/service/schema/api exports
- `back/app/__init__.py`
- `back/tests/conftest.py` only to provide a temporary storage root fixture.

## Task 1: Verify and pin the image runtime in an isolated scaffolding commit

**Files:**

- Modify: `back/requirements.txt`
- Modify: `back/config.py`
- Modify: `back/mypy.ini` only if required by the empirical import-type probe
- Modify: `back/.env.dev`
- Modify: `back/.env.prod`
- Modify: `.gitignore`
- Create: `back/storage/README.md`
- Create: `back/tests/test_storage_configuration.py`
- Modify: `back/tests/conftest.py`

- [ ] **Step 0: Create the dedicated runtime-scaffolding branch/worktree**

From a clean `feature/remaining-backend` after revision 006 has passed its own six-dimensional review, use the required `superpowers:using-git-worktrees` workflow to create branch `feature/storage-runtime-scaffolding` at that exact HEAD. Perform every step in this Task only in that isolated worktree. The PR target is `feature/remaining-backend`, so its diff contains only the scaffold file set below and does not duplicate revision 006 or later storage business commits.

- [ ] **Step 1: Write the failing configuration test**

```python
from pathlib import Path

from config import TestConfig


def test_storage_defaults_are_local_and_inside_back_directory() -> None:
    assert TestConfig.STORAGE_TYPE == "local"
    root = Path(TestConfig.STORAGE_LOCAL_ROOT)
    assert root.is_absolute()
    assert root.name == "storage"


def test_app_fixture_uses_a_per_test_storage_root(app, tmp_path: Path) -> None:
    root = Path(app.config["STORAGE_LOCAL_ROOT"])
    assert root.is_relative_to(tmp_path)
    assert root != Path(TestConfig.STORAGE_LOCAL_ROOT)
```

Also launch a fresh Python subprocess with a temporary `ENV_FILE` containing non-default storage values and assert `load_config()` sees them. Launch a second fresh subprocess with conflicting real environment variables and assert the real environment wins. This exercises the actual import/bootstrap order rather than mutating an already-imported config module.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_configuration.py -q
```

Expected: failure because the storage config keys do not exist.

- [ ] **Step 3: Prove Python 3.13 binary-wheel compatibility before editing requirements**

Run with approved network access:

```bash
cd back
.venv/bin/python -m pip install --only-binary=:all: Pillow pillow-heif olefile pypdf
.venv/bin/python -c "from PIL import Image; import olefile, pillow_heif, pypdf; print(Image.__version__, pillow_heif.__version__, olefile.__version__, pypdf.__version__)"
.venv/bin/python -m pip show Pillow pillow-heif olefile pypdf
.venv/bin/mypy --config-file mypy.ini -c "from PIL import Image; import olefile, pillow_heif, pypdf"
```

Expected: installation and all imports succeed under the repository's Python 3.13 interpreter. Record the exact installed versions printed by `pip show`, then add those exact `name==version` lines under Utilities in `requirements.txt`.

If any required compatible distribution cannot be installed, stop this task and report the package, Python version, platform tag, and failing command. Do not choose an unverified version or silently omit HEIC/PDF/OLE validation.

The mypy probe must pass before Task 3 may statically import these modules. If it reports `[import-untyped]`, first check whether the installed distribution exposes a verified, compatible official or maintained stub package; if so, install it, verify the same probe, and pin its exact installed version. Otherwise add only the exact reported module section (for example `[mypy-olefile.*]` with `ignore_missing_imports = True`) to `back/mypy.ini`, record in the commit message/body that the installed runtime package has no `py.typed` marker, and re-run the probe. Never set project-wide `ignore_missing_imports` and never add `# type: ignore` to application imports.

- [ ] **Step 4: Add deterministic configuration**

```python
# back/config.py, before BaseConfig
def _storage_root(raw: str | None = None) -> str:
    configured = Path(raw or "storage").expanduser()
    if not configured.is_absolute():
        configured = _BACK_DIR / configured
    return str(configured.absolute())


# BaseConfig
STORAGE_TYPE: str = "local"
STORAGE_LOCAL_ROOT: str = _storage_root()


def load_config() -> type[BaseConfig]:
    profile = bootstrap_env()
    base_config = _PROFILES.get(profile, DevConfig)
    return type(
        f"Runtime{base_config.__name__}",
        (base_config,),
        {
            "STORAGE_TYPE": os.getenv("STORAGE_TYPE", "local").strip().lower(),
            "STORAGE_LOCAL_ROOT": _storage_root(os.getenv("STORAGE_LOCAL_ROOT")),
        },
    )
```

Storage values are deliberately bound only after `bootstrap_env()` inside `load_config`; importing `config.py` must not freeze pre-dotenv values. `_storage_root` makes the path absolute without resolving symlinks so the provider can reject a configured symlink root before fixing its resolved root.

Update the shared pytest app fixture so every test receives an isolated storage root even when a later test forgets a local override:

```python
# back/tests/conftest.py
from pathlib import Path


@pytest.fixture()
def app(tmp_path: Path):
    isolated_config = type(
        "IsolatedTestConfig",
        (TestConfig,),
        {"STORAGE_LOCAL_ROOT": str(tmp_path / "storage")},
    )
    app = create_app(config=isolated_config)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
```

Do not create or use `back/storage` in pytest. The configuration test above asserts the factory received this per-test `tmp_path` value.

Add to both tracked profile files:

```dotenv
STORAGE_TYPE=local
STORAGE_LOCAL_ROOT=storage
```

Production deployments can override `STORAGE_LOCAL_ROOT` with an absolute mounted path. Do not add a storage health check here.

- [ ] **Step 5: Ignore runtime files but retain directory documentation**

Append:

```gitignore
back/storage/*
!back/storage/README.md
```

`back/storage/README.md` states that files are runtime data, are not public static files, and must be included in production backups.

- [ ] **Step 6: Run GREEN and import checks**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_configuration.py -q
.venv/bin/python -c "from PIL import Image; import olefile, pillow_heif, pypdf"
.venv/bin/mypy --config-file mypy.ini -c "from PIL import Image; import olefile, pillow_heif, pypdf"
.venv/bin/ruff check config.py tests/test_storage_configuration.py
.venv/bin/mypy app/ config.py
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit the scaffold change on its dedicated branch**

```bash
git add back/requirements.txt back/config.py back/mypy.ini back/.env.dev back/.env.prod .gitignore back/storage/README.md back/tests/conftest.py back/tests/test_storage_configuration.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "chore(scaffolding): add local storage runtime"
```

Keep the worktree clean after this commit; do not start Task 2 on this branch.

- [ ] **Step 8: Merge the independent runtime/config PR before business work**

Push `feature/storage-runtime-scaffolding`, open an independent PR targeting `feature/remaining-backend`, apply the exact `scaffolding` label/tag required by `AGENTS.md`, and run its normal CI/review. The PR must contain exactly the Step 7 staged file list. Wait for that PR to merge, then update the `feature/remaining-backend` delivery worktree to the merged tip and verify `git status --short` is empty. Only then begin Task 2. A local cherry-pick or an unlabeled combined business PR does not satisfy this gate.

## Task 2: Implement the storage port and traversal-safe local adapter

**Files:**

- Create: `back/app/storage/provider.py`
- Create: `back/app/storage/local.py`
- Create: `back/app/storage/factory.py`
- Create: `back/app/storage/__init__.py`
- Create: `back/tests/test_storage_provider.py`

- [ ] **Step 1: Write failing provider behavior tests**

```python
def test_local_provider_round_trip_uses_random_opaque_key(tmp_path) -> None:
    provider = LocalStorageProvider(tmp_path)
    key = provider.save(BytesIO(b"asset-file"), namespace="assets")
    assert "asset-file" not in key
    assert provider.exists(key)
    with provider.open(key) as stream:
        assert stream.read() == b"asset-file"
    provider.delete(key)
    assert not provider.exists(key)


@pytest.mark.parametrize(
    "key",
    [
        "/etc/passwd",
        "../outside",
        "assets/../../outside",
        r"assets\..\outside",
        "assets//outside",
        "assets/./outside",
    ],
)
def test_local_provider_rejects_unsafe_keys(tmp_path, key) -> None:
    provider = LocalStorageProvider(tmp_path)
    with pytest.raises(InvalidStorageKey):
        provider.open(key)
```

Also test a symlinked leaf and symlinked parent cannot be opened/deleted, a failed write leaves no partial object, namespace traversal is rejected, duplicate random keys use exclusive creation, and `exists` does not suppress an invalid-key error. Add a config-to-factory integration test: set `app.config["STORAGE_LOCAL_ROOT"]` to a symlink root preserved by `_storage_root`, then assert `get_storage_provider()` rejects it before resolution. Inject `FileExistsError`, `PermissionError`, and an input stream read failure and assert each becomes a fixed `StorageOperationError` with no filesystem path. Add a one-shot unlink failure after `os.link()` succeeds: the first temporary-file `unlink()` raises, the provider returns the fixed error, and both the just-linked destination and temporary file are absent afterward. This proves failure never leaves an object that has no `StoredFile` row; the collision case must still preserve the pre-existing destination.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_provider.py -q
```

Expected: collection fails because the storage package does not exist.

- [ ] **Step 3: Define the narrow port**

```python
from typing import BinaryIO, Protocol


class StorageProvider(Protocol):
    name: str

    def save(self, stream: BinaryIO, *, namespace: str) -> str: ...
    def open(self, storage_key: str) -> BinaryIO: ...
    def delete(self, storage_key: str) -> bool: ...
    def exists(self, storage_key: str) -> bool: ...


class StorageError(Exception):
    pass


class InvalidStorageKey(StorageError, ValueError):
    pass


class StorageObjectNotFound(StorageError, FileNotFoundError):
    pass


class StorageOperationError(StorageError):
    pass
```

These ellipses are Protocol method bodies, not deferred implementation. `delete` is idempotent and returns whether a regular object actually existed and was removed; cleanup uses that result for byte accounting. Provider implementations translate low-level path/open/link errors into this finite error hierarchy without placing absolute paths in exception messages.

- [ ] **Step 4: Implement safe key resolution**

```python
def _key_parts(storage_key: str) -> tuple[str, ...]:
    if not storage_key or "\x00" in storage_key or "\\" in storage_key:
        raise InvalidStorageKey("invalid storage key")
    pure = PurePosixPath(storage_key)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in {"", ".", ".."} for part in parts):
        raise InvalidStorageKey("invalid storage key")
    if pure.as_posix() != storage_key:
        raise InvalidStorageKey("invalid storage key")
    return parts


def _reject_symlinks(root: Path, parts: tuple[str, ...]) -> Path:
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise InvalidStorageKey("symlink storage path is forbidden")
    resolved_parent = candidate.parent.resolve(strict=False)
    if not resolved_parent.is_relative_to(root):
        raise InvalidStorageKey("storage key escapes root")
    return candidate
```

In `LocalStorageProvider.__init__`, reject a configured root that is itself a symlink, create it, then use `resolve(strict=True)` once and require a directory. `is_symlink()` must be called without an `exists()` guard so dangling symlinks are rejected. Re-run the component guard immediately before each `open`, `delete`, and `exists`, including the leaf. Catch and translate static symlink/path races to `StorageError`; document and test the service-account-only root threat boundary stated above.

- [ ] **Step 5: Implement save/open/delete/exists**

```python
def save(self, stream: BinaryIO, *, namespace: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", namespace) is None:
        raise InvalidStorageKey("invalid storage namespace")
    object_id = uuid4().hex
    key = f"{namespace}/{object_id[:2]}/{object_id}"
    destination: Path | None = None
    temporary: Path | None = None
    linked = False
    try:
        destination = self._resolve_for_write(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{uuid4().hex}.tmp"
        with temporary.open("xb") as output:
            shutil.copyfileobj(stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
        linked = True
        temporary.unlink()
    except InvalidStorageKey:
        raise
    except Exception:
        if linked and destination is not None:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise StorageOperationError("storage save failed") from None
    return key
```

Keep `_key_parts`/`InvalidStorageKey` failures unchanged, but translate every other `save` failure—including `_resolve_for_write`, parent creation, static path races, exclusive-link collision, permissions, and source-stream reads—to the fixed `StorageOperationError` above. The `linked` flag is set only after this call creates the destination, so cleanup removes the destination on a later failure without ever deleting a pre-existing collision object. `LocalStorageProvider.name` is the constant `"LOCAL"`. `open`, `delete`, and `exists` all call the same key/symlink guard and likewise translate low-level `OSError` without embedding paths. `open` directly opens a regular file and maps a missing object to `StorageObjectNotFound`; callers must not use `exists` as a precondition. `delete` directly attempts an idempotent unlink and returns `False` only for a missing valid key. `exists` remains diagnostic and returns true only for a regular non-symlink file.

- [ ] **Step 6: Add the factory**

```python
def get_storage_provider(name: str | None = None) -> StorageProvider:
    provider_type = str(name or current_app.config["STORAGE_TYPE"]).strip().upper()
    if provider_type == "LOCAL":
        return LocalStorageProvider(Path(current_app.config["STORAGE_LOCAL_ROOT"]))
    raise StorageOperationError("unsupported storage provider")
```

No MinIO placeholder class is created. Upload calls the factory without a name and persists `provider.name`; download and cleanup call `get_storage_provider(stored.provider)`, preserving historical-file routing when the default changes.

- [ ] **Step 7: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_provider.py -q
```

Expected: all local-provider tests pass.

- [ ] **Step 8: Commit**

```bash
git add back/app/storage/provider.py back/app/storage/local.py back/app/storage/factory.py back/app/storage/__init__.py back/tests/test_storage_provider.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: add secure local storage provider"
```

## Task 3: Validate file structures and normalize asset photos

**Files:**

- Create: `back/app/storage/inspection.py`
- Create: `back/app/storage/images.py`
- Create: `back/tests/test_file_inspection.py`
- Modify: `back/app/storage/__init__.py`

- [ ] **Step 1: Write failing real-byte tests**

Generate JPEG, PNG, and HEIC fixtures with Pillow/pillow-heif; valid one-page PDFs with pypdf; and deterministic minimal OOXML DOCX/XLSX and CFB DOC/XLS bytes. Verify:

```python
def test_extension_must_match_detected_container() -> None:
    with pytest.raises(UnsafeUpload, match="文件格式"):
        inspect_upload(BytesIO(b"%PDF-1.7\n"), "invoice.jpg", 20 * MIB)


def test_ooxml_macro_or_zip_bomb_is_rejected() -> None:
    with pytest.raises(UnsafeUpload):
        inspect_upload(make_docx_with_vba_project(), "contract.docx", 20 * MIB)
    with pytest.raises(UnsafeUpload):
        inspect_upload(make_high_ratio_zip(), "contract.docx", 20 * MIB)


def test_prefixed_fake_or_encrypted_pdf_is_rejected() -> None:
    with pytest.raises(UnsafeUpload):
        inspect_upload(BytesIO(b"%PDF-1.7\nnot-a-pdf\n%%EOF"), "fake.pdf", 20 * MIB)
    with pytest.raises(UnsafeUpload):
        inspect_upload(make_encrypted_pdf(), "secret.pdf", 20 * MIB)


def test_ole_vba_stream_is_rejected() -> None:
    with pytest.raises(UnsafeUpload):
        inspect_upload(make_cfb_with_streams("WordDocument", "Macros/VBA/Module1"), "macro.doc", 20 * MIB)


def test_heic_photo_is_decoded_and_normalized_to_jpeg() -> None:
    inspected = inspect_upload(make_heic(), "phone.heic", 10 * MIB)
    processed = normalize_asset_photo(inspected)
    assert processed.extension == "jpg"
    assert processed.mime_type == "image/jpeg"
    assert processed.size_bytes > 0
```

Also test exact 10/20 MiB boundaries, one byte over limit, empty file, misleading double extension, malformed PNG/JPEG/HEIC, all Pillow decode failures mapping to `UnsafeUpload`, excessive image pixels, EXIF stripped, max edge 2560, OOXML entry count/uncompressed-size limits, encrypted ZIP entry, and case-insensitive allowed extension normalization.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_file_inspection.py -q
```

Expected: imports fail because inspection and image modules are missing.

- [ ] **Step 3: Buffer with a hard byte limit and calculate SHA-256**

```python
MIB = 1024 * 1024


class UnsafeUpload(Exception):
    """Structurally invalid, unsafe, or unsupported client bytes."""


@dataclass
class InspectedUpload:
    stream: BinaryIO
    original_name: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str


def _read_limited(stream: BinaryIO, maximum: int) -> tuple[SpooledTemporaryFile[bytes], int, str]:
    buffered = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b")
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > maximum:
            buffered.close()
            raise UnsafeUpload("文件大小超过限制")
        digest.update(chunk)
        buffered.write(chunk)
    if size == 0:
        buffered.close()
        raise UnsafeUpload("文件不能为空")
    buffered.seek(0)
    return buffered, size, digest.hexdigest()
```

- [ ] **Step 4: Implement the explicit signature/container matrix**

```text
pdf  -> `%PDF-` header plus successful strict `pypdf.PdfReader`, unencrypted, at least one page, and a valid terminal `%%EOF`
jpg/jpeg -> FF D8 FF and Pillow decode
png -> 89 50 4E 47 0D 0A 1A 0A and Pillow decode
heic -> ISO-BMFF ftyp brand in {heic, heix, hevc, heim, heis, mif1, msf1}, then pillow-heif decode
doc -> valid OLE/CFB parsed by olefile with a `WordDocument` stream
xls -> valid OLE/CFB parsed by olefile with a `Workbook` or `Book` stream
docx -> ZIP with `[Content_Types].xml`, main part `word/document.xml`, and the WordprocessingML main content type
xlsx -> ZIP with `[Content_Types].xml`, main part `xl/workbook.xml`, and the SpreadsheetML main content type
```

Opening an OLE header alone is insufficient: parse its directory with `olefile`, require the format-specific stream above, and reject any `VBA`, `Macros`, `_VBA_PROJECT`, or `_VBA_PROJECT_CUR` stream/storage component case-insensitively. PDF parsing catches all pypdf parse/decryption errors and emits a fixed `UnsafeUpload`; a prefix/EOF pair alone is not accepted. OOXML inspection parses `[Content_Types].xml` and rejects a mismatched/missing main override, more than 2048 entries, any encrypted entry, total declared uncompressed size over 100 MiB, compression ratio over 100 for a non-empty entry, path traversal entries, duplicate normalized entry names, external relationships, and any `vbaProject.bin`. Return the detected MIME from a constant mapping; do not trust the request MIME.

- [ ] **Step 5: Normalize Asset photos**

```python
def normalize_asset_photo(upload: InspectedUpload) -> InspectedUpload:
    register_heif_opener()
    try:
        upload.stream.seek(0)
        with Image.open(upload.stream) as source:
            if source.width * source.height > 40_000_000:
                raise UnsafeUpload("图片像素过大")
            source.load()
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            normalized.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
            output = SpooledTemporaryFile(max_size=2 * MIB, mode="w+b")
            normalized.save(output, format="JPEG", quality=85, optimize=True)
    except UnsafeUpload:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise UnsafeUpload("图片文件无法解析") from None
    output.seek(0)
    data = output.read()
    output.seek(0)
    return InspectedUpload(
        stream=output,
        original_name=upload.original_name,
        extension="jpg",
        mime_type="image/jpeg",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
```

Export `MIB`, `UnsafeUpload`, `InspectedUpload`, `inspect_upload`, and `normalize_asset_photo` from `app.storage`. The output is a newly encoded image, so original EXIF/GPS metadata is not copied.

- [ ] **Step 6: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_file_inspection.py -q
```

Expected: all structural and image tests pass with real bytes.

- [ ] **Step 7: Commit**

```bash
git add back/app/storage/inspection.py back/app/storage/images.py back/app/storage/__init__.py back/tests/test_file_inspection.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: validate asset attachment files"
```

## Task 4: Add explicit file and AssetAttachment persistence models

**Files:**

- Create: `back/app/models/file_storage.py`
- Create: `back/app/models/asset_attachment.py`
- Create: `back/app/repositories/file_repository.py`
- Create: `back/app/repositories/asset_attachment_repository.py`
- Create: `back/tests/test_asset_attachment_models.py`
- Modify: `back/app/enums/__init__.py`
- Modify: model/repository exports

- [ ] **Step 1: Write failing metadata contracts**

```python
def test_asset_attachment_model_contract(app) -> None:
    assert StoredFile.__table__.c.storage_key.unique is True
    assert AssetAttachment.__table__.c.stored_file_id.unique is True
    assert AssetAttachment.__table__.c.replaced_by_attachment_id.unique is True
    assert AssetAttachment.__table__.c.version.nullable is False
    assert FileCleanupRun.__table__.c.deleted_bytes.nullable is False
```

Also assert all enums have the exact values below; upload/invalidation/deletion actor FKs use `RESTRICT` so audit identity survives; every named CHECK below exists in both metadata and revision 007; and repository cleanup eligibility depends only on `StoredFile` columns.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachment_models.py -q
```

Expected: collection fails because models/enums are missing.

- [ ] **Step 3: Add exact enum contracts**

```python
class AssetAttachmentType(StringEnum):
    ASSET_PHOTO = "ASSET_PHOTO"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    INVOICE = "INVOICE"
    ACCEPTANCE_FORM = "ACCEPTANCE_FORM"
    REPAIR_RECORD = "REPAIR_RECORD"
    SCRAP_PROOF = "SCRAP_PROOF"
    OTHER = "OTHER"


class AssetAttachmentStatus(StringEnum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    DELETED = "DELETED"


class FileSecurityStatus(StringEnum):
    VALIDATED = "VALIDATED"


class FileCleanupStatus(StringEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
```

- [ ] **Step 4: Add StoredFile and cleanup-run models**

```python
class StoredFile(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "stored_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    security_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    temporary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    delete_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    physically_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileCleanupRun(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "file_cleanup_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    already_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 5: Add the explicit Asset association**

```python
class AssetAttachment(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True)
    stored_file_id: Mapped[int] = mapped_column(ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    attachment_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    remark: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    replaced_by_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("asset_attachments.id", ondelete="RESTRICT"), nullable=True, unique=True, index=True)
    invalidated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

Add explicitly named, portable CHECK constraints:

```text
ck_stored_files_size_nonnegative: size_bytes >= 0
ck_stored_files_security_status: security_status IN ('VALIDATED')
ck_stored_files_temporary_expiry: temporary = false OR expires_at IS NOT NULL
ck_file_cleanup_runs_status: status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')
ck_file_cleanup_runs_counts_nonnegative: scanned/deleted/already_missing/deleted_bytes/failed are all >= 0
ck_file_cleanup_runs_missing_le_deleted: already_missing_count <= deleted_count
ck_file_cleanup_runs_finished: RUNNING has finished_at NULL; every terminal status has finished_at NOT NULL
ck_asset_attachments_type: exact seven AssetAttachmentType values
ck_asset_attachments_status: status IN ('ACTIVE','INVALIDATED','DELETED')
ck_asset_attachments_version_positive: version >= 1
ck_asset_attachments_cover: is_cover = false OR (attachment_type = 'ASSET_PHOTO' AND status = 'ACTIVE')
ck_asset_attachments_invalidation_group: INVALIDATED iff invalidated_by/at/reason are all non-NULL; otherwise all three are NULL
ck_asset_attachments_deletion_group: DELETED iff deleted_by/at/reason are all non-NULL; otherwise all three are NULL
ck_asset_attachments_replacement_not_self: replaced_by_attachment_id IS NULL OR replaced_by_attachment_id <> id
```

`replaced_by_attachment_id` follows the product direction: the old attachment points to the new attachment. The unique value prevents an attachment from being the replacement target for multiple old rows; service validation additionally permits each old row to be replaced only once.

- [ ] **Step 6: Implement only required queries**

Define and export these exact repository singletons:

```text
stored_file_repository: StoredFileRepository
file_cleanup_run_repository: FileCleanupRunRepository
asset_attachment_repository: AssetAttachmentRepository
```

`StoredFileRepository.find_cleanup_candidates(now, limit)` selects only rows with `physically_deleted_at IS NULL` and either `(temporary = true AND expires_at <= now)` or `delete_requested_at IS NOT NULL`, ordered by ID and bounded by `limit`. It never joins or inspects `AssetAttachment`. `FileCleanupRunRepository` provides `add(run)` and `get(run_id)`. `AssetAttachmentRepository` provides:

```text
list_for_asset(asset_id, include_history) -> list[tuple[AssetAttachment, StoredFile]]
find_with_file(attachment_id, for_update=False) -> tuple[AssetAttachment, StoredFile] | None
active_photos_for_asset(asset_id, for_update=False) -> list[AssetAttachment]
```

All list ordering is deterministic by attachment ID. `list_for_asset(..., False)` returns only ACTIVE rows; `include_history=True` returns ACTIVE, INVALIDATED, and DELETED metadata. Physical deletion eligibility is requested explicitly by setting `StoredFile.delete_requested_at` when a photo becomes DELETED; invalidated documents never set it.

- [ ] **Step 7: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachment_models.py -q
```

Expected: all model/repository contracts pass.

- [ ] **Step 8: Commit**

```bash
git add back/app/enums/__init__.py back/app/models/file_storage.py back/app/models/asset_attachment.py back/app/models/__init__.py back/app/repositories/file_repository.py back/app/repositories/asset_attachment_repository.py back/app/repositories/__init__.py back/tests/test_asset_attachment_models.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: add asset attachment metadata"
```

## Task 5: Add immutable Alembic revision 007 and permissions

**Files:**

- Create: `back/migrations/versions/007_asset_file_storage.py`
- Create: `back/tests/test_file_storage_migration.py`
- Modify: `back/tests/test_migrations.py`

- [ ] **Step 1: Write migration RED tests**

Assert:

```python
assert migration.revision == "007"
assert migration.down_revision == "006"
```

SQLite `006 -> 007 -> 006 -> 007` tests compare every column, nullability, FK, unique index, and regular index with metadata; seed roles exactly:

```python
EXPECTED = {
    "asset:attachment:view": {"SUPER_ADMIN", "ASSET_ADMIN", "USER"},
    "asset:attachment:manage": {"SUPER_ADMIN", "ASSET_ADMIN"},
}
```

Both permission rows use module `asset`, `enabled = true`, and names `查看资产附件` / `管理资产附件` respectively. Migration tests assert these fields as well as role mappings.

Insert complete ACTIVE photo, INVALIDATED document, DELETED photo, and cleanup-run graphs; verify every CHECK and FK rejects invalid rows; downgrade after deleting test rows; and assert 007 tables/permissions disappear while all 006 objects remain. Compile upgrade and downgrade for MySQL and assert attachment self-FK/index teardown order is valid.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_file_storage_migration.py -q
```

Expected: failure because revision 007 is missing.

- [ ] **Step 3: Implement exact table creation order**

```text
1. stored_files
2. file_cleanup_runs
3. asset_attachments
4. permission and role-permission seeds
```

Use explicitly named FKs and CHECK constraints for later batch-safe teardown. Match all Task 4 model fields and lengths—including `delete_requested_at`, `already_missing_count`, `remark`, and `replaced_by_attachment_id`—and use `sa.BigInteger` for byte counts. Create unique indexes for `stored_files.storage_key`, `asset_attachments.stored_file_id`, and `asset_attachments.replaced_by_attachment_id`. Upload/invalidation/deletion actor FKs are `RESTRICT`; only the optional cleanup-run trigger actor uses `SET NULL`.

- [ ] **Step 4: Implement downgrade in reverse dependency order**

Delete role-permission rows, delete the two permission rows, then:

```text
1. drop asset_attachments (self-FK disappears with the table)
2. drop file_cleanup_runs
3. drop stored_files
```

Do not pre-drop MySQL FK-backing indexes when dropping the whole table.

- [ ] **Step 5: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_file_storage_migration.py tests/test_migrations.py -q
export SMOKE_ROOT="$(mktemp -d /private/tmp/asset-file-007.XXXXXX)"
touch "$SMOKE_ROOT/empty.env"
mkdir "$SMOKE_ROOT/storage"
export ENV_FILE="$SMOKE_ROOT/empty.env"
export DB_URL="sqlite:///$SMOKE_ROOT/files.db"
export STORAGE_TYPE=local
export STORAGE_LOCAL_ROOT="$SMOKE_ROOT/storage"
export FLASK_ENV=dev
.venv/bin/python -c 'import os; from pathlib import Path; root=Path(os.environ["SMOKE_ROOT"]).resolve(); db=Path(os.environ["DB_URL"].removeprefix("sqlite:///")).resolve(); storage=Path(os.environ["STORAGE_LOCAL_ROOT"]).resolve(); assert db.is_relative_to(root) and storage.is_relative_to(root)'
FLASK_APP=manage.py .venv/bin/flask db upgrade
FLASK_APP=manage.py .venv/bin/flask db check
```

Expected: migration tests pass, the disposable database reaches 007, and metadata has no drift. Do not run this check against the default dev database.

- [ ] **Step 6: Commit**

```bash
git add back/migrations/versions/007_asset_file_storage.py back/tests/test_file_storage_migration.py back/tests/test_migrations.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: migrate asset file storage"
```

## Task 6: Upload, list, and securely download Asset attachments

**Files:**

- Create: `back/app/services/asset_attachment_service.py`
- Create: `back/app/schemas/asset_attachment.py`
- Create: `back/app/api/asset_attachments.py`
- Create: `back/tests/test_asset_attachments.py`
- Modify: service/schema exports and `back/app/api/__init__.py`

- [ ] **Step 1: Write failing API/service tests**

Use real temporary storage and real files. Cover:

- manager-only and holder-only SELF visibility;
- no JWT gives HTTP 401; missing functional permission gives HTTP 200 with envelope `code == 403`; out-of-scope gives HTTP 200 with envelope `code == 404`;
- first active photo automatically becomes cover;
- eleventh active photo is rejected;
- documents use 20 MiB while photos use 10 MiB;
- `ASSET_PHOTO` accepts only JPG/JPEG/PNG/HEIC; valid PDF/DOC bytes posted as a photo return a safe BAD_REQUEST, while non-photo attachment types may still use every product-whitelisted format;
- default list omits history; `include_history=true` includes INVALIDATED and DELETED metadata; neither form exposes `storage_key`;
- download bytes/hash match the stored object;
- download uses attachment disposition, safe filename, `X-Content-Type-Options: nosniff`, and `Cache-Control: private, no-store`;
- missing physical object produces a safe business error;
- a row written by provider `LOCAL` is downloaded through `get_storage_provider(stored.provider)` even after the configured default is changed in a test;
- multipart numeric strings load successfully while malformed form fields return HTTP 400;
- closing the Flask response closes the underlying download stream;
- database-commit failure triggers best-effort deletion of the just-saved orphan.
- an over-255-character/path/control client filename is stored as a safe at-most-255-character `original_name`, and unexpected persistence failures expose/log neither that name nor key/hash/SQL parameters.

The one failure-path fake replaces only the low-level `StorageProvider.delete`; all business validation, real local save, database work, and response assertions remain real.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachments.py -k "upload or list or download" -q
```

Expected: 404/import failure because the API/service is missing.

- [ ] **Step 3: Add boundary DTOs and schemas**

```python
@dataclass
class AttachmentDownload:
    stream: BinaryIO
    filename: str
    mime_type: str
    size_bytes: int


class UploadAssetAttachmentRequestSchema(Schema):
    asset_id = fields.Integer(required=True)
    attachment_type = fields.String(
        required=True,
        validate=validate.OneOf([item.value for item in AssetAttachmentType]),
    )
    display_name = fields.String(required=False, allow_none=True, validate=validate.Length(max=255))
    remark = fields.String(required=False, allow_none=True, validate=validate.Length(max=1000))


class AssetAttachmentListQuerySchema(Schema):
    asset_id = fields.Integer(required=True)
    include_history = fields.Boolean(load_default=False)
```

Multipart and query-string values are strings, so their integer fields deliberately use Marshmallow's normal coercion; `strict=True` is reserved for JSON action schemas in Task 7.

Define these helpers in `asset_attachment_service.py` rather than leaving implicit names:

```python
def safe_display_name(value: str, extension: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    leaf = re.split(r"[/\\]", normalized)[-1]
    leaf = "".join(char for char in leaf if ord(char) >= 32 and ord(char) != 127)
    leaf = leaf.strip(" .")
    stem = leaf.rsplit(".", 1)[0].strip(" .") if "." in leaf else leaf
    if not stem:
        raise BusinessException("文件名无效", result_code=ResultCode.BAD_REQUEST)
    suffix = f".{extension.lower()}"
    return f"{stem[: 255 - len(suffix)]}{suffix}"


def safe_original_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    leaf = re.split(r"[/\\]", normalized)[-1]
    leaf = "".join(char for char in leaf if ord(char) >= 32 and ord(char) != 127)
    leaf = leaf.strip(" .")
    if not leaf:
        raise BusinessException("文件名无效", result_code=ResultCode.BAD_REQUEST)
    stem, dot, suffix = leaf.rpartition(".")
    if not dot or not stem:
        return leaf[:255]
    preserved_suffix = f".{suffix[:16]}"
    return f"{stem[: 255 - len(preserved_suffix)]}{preserved_suffix}"


def _serialize(attachment: AssetAttachment, stored: StoredFile) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "asset_id": attachment.asset_id,
        "attachment_type": attachment.attachment_type,
        "status": attachment.status,
        "is_cover": attachment.is_cover,
        "remark": attachment.remark,
        "replaced_by_attachment_id": attachment.replaced_by_attachment_id,
        "display_name": stored.display_name,
        "extension": stored.extension,
        "mime_type": stored.mime_type,
        "size_bytes": stored.size_bytes,
        "uploaded_by": stored.uploaded_by,
        "created_at": attachment.created_at,
        "invalidated_by": attachment.invalidated_by,
        "invalidated_at": attachment.invalidated_at,
        "invalidation_reason": attachment.invalidation_reason,
        "deleted_by": attachment.deleted_by,
        "deleted_at": attachment.deleted_at,
        "deletion_reason": attachment.deletion_reason,
        "version": attachment.version,
    }
```

`safe_display_name` replaces the client suffix with the detected extension. `safe_original_name` preserves a bounded client suffix for metadata while removing path/control content and enforcing the MySQL `VARCHAR(255)` limit. Neither helper returns an empty name. `_serialize` is the sole service response mapper and intentionally has no `storage_key`, absolute path, or digest.

- [ ] **Step 4: Implement upload with cross-resource compensation**

```python
def upload(
    *,
    asset_id: int,
    attachment_type: str,
    display_name: str | None,
    remark: str | None,
    original_name: str,
    stream: BinaryIO,
    actor_id: int,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:attachment:manage")
    asset_access_service.get_accessible(
        asset_id, actor_id, "asset:attachment:manage"
    )
    is_photo = attachment_type == AssetAttachmentType.ASSET_PHOTO.value
    try:
        inspected = inspect_upload(
            stream, original_name, 10 * MIB if is_photo else 20 * MIB
        )
        if is_photo and inspected.extension not in {"jpg", "jpeg", "png", "heic"}:
            raise BusinessException(
                "资产照片仅支持JPG、PNG或HEIC",
                result_code=ResultCode.BAD_REQUEST,
            )
        prepared = normalize_asset_photo(inspected) if is_photo else inspected
    except UnsafeUpload as error:
        raise BusinessException(
            str(error), result_code=ResultCode.BAD_REQUEST
        ) from None

    provider = get_storage_provider()
    try:
        storage_key = provider.save(prepared.stream, namespace="assets")
    except (StorageError, OSError) as error:
        current_app.logger.error(
            "attachment storage save failed",
            extra={"exception_type": type(error).__name__},
        )
        raise BusinessException(
            "文件存储失败，请稍后重试", result_code=ResultCode.INTERNAL_ERROR
        ) from None
    try:
        assets = asset_repository.find_many_accessible_for_update(
            [asset_id], asset_access_service.access_filter(actor_id)
        )
        if not assets:
            raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
        existing_photos = asset_attachment_repository.active_photos_for_asset(
            asset_id, for_update=True
        )
        if is_photo and len(existing_photos) >= 10:
            raise BusinessException("每件资产最多上传10张照片")
        stored = stored_file_repository.add(StoredFile(
            storage_key=storage_key,
            original_name=safe_original_name(prepared.original_name),
            display_name=safe_display_name(display_name or prepared.original_name, prepared.extension),
            extension=prepared.extension,
            mime_type=prepared.mime_type,
            size_bytes=prepared.size_bytes,
            sha256=prepared.sha256,
            provider=provider.name,
            uploaded_by=actor_id,
            security_status=FileSecurityStatus.VALIDATED.value,
            temporary=False,
        ))
        attachment = asset_attachment_repository.add(AssetAttachment(
            asset_id=asset_id,
            stored_file_id=stored.id,
            attachment_type=attachment_type,
            status=AssetAttachmentStatus.ACTIVE.value,
            is_cover=is_photo and not existing_photos,
            remark=remark,
        ))
        audit_service.record_resource_change(
            action="ASSET_ATTACHMENT_UPLOAD",
            resource_type="asset_attachment",
            resource_id=str(attachment.id),
            actor_id=actor_id,
            before_data=None,
            after_data={"asset_id": asset_id, "type": attachment_type, "filename": stored.display_name},
        )
        db.session.commit()
    except BusinessException:
        db.session.rollback()
        _delete_orphan_safely(provider, storage_key)
        raise
    except Exception as error:
        db.session.rollback()
        _delete_orphan_safely(provider, storage_key)
        current_app.logger.error(
            "attachment metadata persistence failed",
            extra={"exception_type": type(error).__name__},
        )
        raise BusinessException(
            "附件保存失败，请稍后重试", result_code=ResultCode.INTERNAL_ERROR
        ) from None
    return _serialize(attachment, stored)
```

Define `_delete_orphan_safely(provider, storage_key)` once: it attempts `delete`, catches `StorageError`, and logs only a constant event plus exception class. The fixed mutation lock order is Asset row first, then attachment/photo rows. File inspection and physical save happen before the short database-lock section; every failure after save compensates the new object. Close both input/inspection buffers in `finally` (without double-closing the same object). Do not log storage keys, paths, filenames, exception text/tracebacks, file bytes, hashes, or SQL parameters. Tests use `caplog` and response JSON to prove sensitive values are absent.

- [ ] **Step 5: Implement list/download**

`list_for_asset(asset_id, include_history, actor_id)` calls `asset_access_service.get_accessible(asset_id, actor_id, "asset:attachment:view")`, maps repository pairs through `_serialize`, returns ACTIVE rows by default, and includes INVALIDATED plus DELETED metadata when requested. DELETED rows remain non-downloadable. It never returns `storage_key`.

`download(attachment_id, actor_id)` loads the pair, calls `asset_access_service.get_accessible(attachment.asset_id, actor_id, "asset:attachment:view")`, rejects `DELETED`, obtains `get_storage_provider(stored.provider)`, and directly calls `provider.open` without an `exists` precheck. Map `InvalidStorageKey`, `StorageObjectNotFound`, `StorageOperationError`, and safe low-level open failures to `BusinessException("附件文件不存在或不可用", result_code=ResultCode.NOT_FOUND)` without including an exception string. Return `AttachmentDownload(stream, safe name, detected MIME, size)`.

- [ ] **Step 6: Implement GET/POST upload/list/download routes**

```python
@bp.get("")
@jwt_required()
def list_attachments() -> dict:
    query = _list_schema.load(request.args.to_dict())
    return Result.success(
        asset_attachment_service.list_for_asset(
            query["asset_id"], query["include_history"], current_user_id()
        )
    ).to_dict()


@bp.post("")
@jwt_required()
def upload_attachment() -> dict:
    payload = _upload_schema.load(request.form.to_dict())
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise ValidationError("必须上传文件", field_name="file")
    return Result.success(
        asset_attachment_service.upload(
            asset_id=payload["asset_id"],
            attachment_type=payload["attachment_type"],
            display_name=payload.get("display_name"),
            remark=payload.get("remark"),
            original_name=uploaded.filename,
            stream=uploaded.stream,
            actor_id=current_user_id(),
        )
    ).to_dict()
```

The download route uses Flask `send_file` on the returned stream, sets `as_attachment=True`, `download_name`, `mimetype`, and the two security/cache headers, then registers `response.call_on_close(download.stream.close)`. Tests explicitly close the response and assert the stream closes. Import/register `asset_attachments.bp` in `back/app/api/__init__.py`; `back/app/__init__.py` is unchanged. No static route is added.

- [ ] **Step 7: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachments.py -k "upload or list or download" -q
```

Expected: focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add back/app/services/asset_attachment_service.py back/app/schemas/asset_attachment.py back/app/api/asset_attachments.py back/app/services/__init__.py back/app/schemas/__init__.py back/app/api/__init__.py back/tests/test_asset_attachments.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: upload and download asset attachments"
```

## Task 7: Invalidate, replace, delete photos, and select cover

**Files:**

- Modify: `back/app/services/asset_attachment_service.py`
- Modify: `back/app/schemas/asset_attachment.py`
- Modify: `back/app/api/asset_attachments.py`
- Modify: `back/tests/test_asset_attachments.py`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

- document invalidate requires reason/version and retains physical file/download history;
- ACTIVE documents and already INVALIDATED-but-unreplaced documents can each be replaced exactly once; the old row points to the new row through `replaced_by_attachment_id`;
- replace validates/saves the new object before changing DB state, and compensates on DB failure;
- photo delete requires reason/version, marks metadata DELETED, clears cover, and never allows download;
- document delete and photo invalidate/replace use the correct domain restrictions;
- deleting the cover promotes the earliest remaining active photo;
- set-cover permits only an active photo on the same accessible Asset;
- stale version, repeated action, cross-asset action, missing permission, and scope failures are rejected;
- one Asset never has two active covers after concurrent/ordered updates;
- every attachment whose status or `is_cover` changes increments version, including a cleared old cover and an automatically promoted cover; after A→B, A's pre-switch version is stale;
- whitespace-only reasons for invalidate, delete, and replace return HTTP 400 and no row/audit change;
- every action writes one safe audit log without storage_key.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachments.py -k "invalidate or replace or delete or cover" -q
```

Expected: 404 or missing service methods.

- [ ] **Step 3: Add action schemas**

```python
class AttachmentActionRequestSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    reason = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=500),
            validate.Predicate("strip", error="原因不能为空"),
        ),
    )


class SetCoverRequestSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class ReplaceAttachmentRequestSchema(Schema):
    version = fields.Integer(required=True, validate=validate.Range(min=1))
    reason = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=500),
            validate.Predicate("strip", error="原因不能为空"),
        ),
    )
    display_name = fields.String(required=False, allow_none=True, validate=validate.Length(max=255))
    remark = fields.String(required=False, allow_none=True, validate=validate.Length(max=1000))
```

Invalidate/delete/set-cover are JSON, so their numeric fields stay strict. Replacement uses multipart: its integer accepts form strings, action fields are loaded from `request.form`, and the replacement file is required from `request.files`. Routes trim validated reasons, and services defensively reject a blank normalized reason before any mutation.

- [ ] **Step 4: Implement row-locked state transitions**

Use one `_lock_accessible_attachment` helper and this fixed order for every database mutation:

1. load the pair without a lock only to discover the immutable `asset_id`, returning NOT_FOUND when absent;
2. require `asset:attachment:manage`, then lock the accessible Asset through `find_many_accessible_for_update([asset_id], asset_access_service.access_filter(actor_id))`;
3. reload the attachment pair with `FOR UPDATE` and recheck the same `asset_id`, version, status, and type;
4. apply one transition, stage one audit, and commit once;
5. explicitly roll back on every exception.

`invalidate` accepts only ACTIVE non-photo documents, sets the complete INVALIDATED actor/time/reason group, and increments the target version once. `replace` performs access/precondition discovery, structural validation, and physical save outside locks; it then locks Asset followed by attachment. It accepts a non-photo old row only when status is ACTIVE or INVALIDATED and `replaced_by_attachment_id IS NULL`. If ACTIVE, set the invalidation group from the replacement reason; if already INVALIDATED, preserve its original invalidation actor/time/reason. Insert the new ACTIVE document with the same `attachment_type`, flush it, then set `old.replaced_by_attachment_id = new.id` and increment the old version exactly once for the complete transition. `delete_photo` locks all ACTIVE photos for the Asset, accepts only ACTIVE `ASSET_PHOTO`, sets the complete DELETED group, sets its `StoredFile.delete_requested_at` to the same timestamp, clears cover, and increments the deleted row once; if it was cover, promote the lowest-ID remaining ACTIVE photo and increment that promoted row. `set_cover` locks all ACTIVE photos, clears/increments every covered row other than the selected row, then marks/increments the selected row only when it was not already cover.

Do not use an unversioned bulk `clear_cover`; mutate the locked photo rows so every changed row advances. All attachment mutations acquire the Asset lock before any attachment lock, including upload, so competing cover/replace/delete operations cannot invert lock order. If replacement DB work raises `BusinessException`, roll back, compensate only the new object, and rethrow it. For every other exception, roll back, compensate, log only the exception class, and raise the same fixed INTERNAL_ERROR used by upload from `None`. Never delete or re-read the invalidated original's physical object.

- [ ] **Step 5: Add POST-only action routes**

```text
POST /api/v1/asset-attachments/<id>/invalidate
POST /api/v1/asset-attachments/<id>/replace
POST /api/v1/asset-attachments/<id>/delete
POST /api/v1/asset-attachments/<id>/set-cover
```

- [ ] **Step 6: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_attachments.py -q
```

Expected: all attachment API/service tests pass.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/asset_attachment_service.py back/app/schemas/asset_attachment.py back/app/api/asset_attachments.py back/tests/test_asset_attachments.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: manage asset attachment lifecycle"
```

## Task 8: Add retryable physical cleanup and CLI logging

**Files:**

- Create: `back/app/services/storage_cleanup_service.py`
- Create: `back/app/storage/cli.py`
- Create: `back/tests/test_storage_cleanup.py`
- Modify: `back/app/__init__.py`
- Modify: service/storage exports

- [ ] **Step 1: Write failing cleanup tests**

With real LocalStorageProvider files, verify:

- expired temporary file is deleted and metadata receives `physically_deleted_at`;
- logically deleted Asset photo is deleted;
- active and invalidated document files are retained;
- missing physical file is treated as already deleted;
- one failing delete does not stop remaining candidates;
- SUCCESS/PARTIAL/FAILED counts, `already_missing_count`, and byte totals are correct; missing files increment deleted/missing counts but never `deleted_bytes`;
- failure summary contains safe file IDs/errors but no storage key;
- repeated cleanup is idempotent;
- cleanup routes every row through `get_storage_provider(stored.provider)` and an unknown provider fails only that row;
- an unexpected outer failure still changes the persisted run from RUNNING to FAILED with `finished_at`;
- CLI exits zero only for SUCCESS; PARTIAL and FAILED are non-zero; it prints counts and creates a `FileCleanupRun`.

Use a minimal provider test double only for the one injected delete failure; do not mock repository queries or the cleanup use case.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_cleanup.py -q
```

Expected: import failure because cleanup service/CLI are missing.

- [ ] **Step 3: Implement bounded cleanup**

```python
def cleanup(*, actor_id: int | None = None, limit: int = 500) -> dict[str, Any]:
    run = file_cleanup_run_repository.add(FileCleanupRun(
        status=FileCleanupStatus.RUNNING.value,
        triggered_by=actor_id,
        started_at=utc_now(),
        scanned_count=0,
        deleted_count=0,
        already_missing_count=0,
        deleted_bytes=0,
        failed_count=0,
    ))
    db.session.commit()
    run_id = run.id
    failures: list[str] = []
    fatal_error_type: str | None = None
    try:
        candidates = stored_file_repository.find_cleanup_candidates(utc_now(), limit)
        for stored in candidates:
            run.scanned_count += 1
            try:
                provider = get_storage_provider(stored.provider)
                removed = provider.delete(stored.storage_key)
                stored.physically_deleted_at = utc_now()
                run.deleted_count += 1
                if removed:
                    run.deleted_bytes += stored.size_bytes
                else:
                    run.already_missing_count += 1
            except (StorageError, OSError) as error:
                run.failed_count += 1
                if len(failures) < 50:
                    failures.append(f"file_id={stored.id}:{type(error).__name__}")
        run.status = (
            FileCleanupStatus.SUCCESS.value
            if run.failed_count == 0
            else FileCleanupStatus.PARTIAL.value
            if run.deleted_count > 0
            else FileCleanupStatus.FAILED.value
        )
    except Exception as error:
        db.session.rollback()
        fatal_error_type = type(error).__name__
    finally:
        run = file_cleanup_run_repository.get(run_id)
        if run is None:
            raise RuntimeError("cleanup run disappeared") from None
        if fatal_error_type is not None:
            run.status = FileCleanupStatus.FAILED.value
            run.failed_count = max(run.failed_count, 1)
            failures = [f"run:{fatal_error_type}"]
        elif run.status == FileCleanupStatus.RUNNING.value:
            run.status = FileCleanupStatus.FAILED.value
            run.failed_count = max(run.failed_count, 1)
            failures = ["run:UnexpectedIncompleteRun"]
        run.finished_at = utc_now()
        run.failure_summary = (";".join(failures)[:4000] or None)
        db.session.commit()
    return _serialize_cleanup_run(run)
```

Define `_serialize_cleanup_run(run)` in this service and return exactly `id`, `status`, `started_at`, `finished_at`, `scanned_count`, `deleted_count`, `already_missing_count`, `deleted_bytes`, `failed_count`, and `failure_summary`. Repository candidates exclude already physically deleted rows and use deterministic ID order. The per-item failure path records only database IDs and exception class names—never exception text, tracebacks, providers, keys, or paths. `delete` itself is the idempotent operation; no `exists`-then-delete TOCTOU is introduced.

- [ ] **Step 4: Register a CLI, not a worker**

```python
@click.command("storage-cleanup")
@click.option("--limit", type=click.IntRange(min=1, max=5000), default=500)
def storage_cleanup(limit: int) -> None:
    result = storage_cleanup_service.cleanup(limit=limit)
    click.echo(
        f"status={result['status']} scanned={result['scanned_count']} "
        f"deleted={result['deleted_count']} missing={result['already_missing_count']} "
        f"bytes={result['deleted_bytes']} failed={result['failed_count']}"
    )
    if result["status"] != FileCleanupStatus.SUCCESS.value:
        raise click.ClickException("storage cleanup incomplete")
```

Export the command from `app.storage`; do not register it in the app factory in this business commit, and do not register health readiness yet.

- [ ] **Step 5: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_storage_cleanup.py -q
```

Expected: service tests and direct `CliRunner` command tests pass against the test app's temporary SQLite database/storage root. No command in this step reads the tracked dev environment.

- [ ] **Step 6: Commit**

```bash
git add back/app/services/storage_cleanup_service.py back/app/storage/cli.py back/app/storage/__init__.py back/app/services/__init__.py back/tests/test_storage_cleanup.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: clean expired stored files"
```

- [ ] **Step 7: Register the CLI through a second independent scaffolding PR**

After the Task 8 business commit is present on `feature/remaining-backend`, publish that delivery-branch tip so it can be the stacked PR target. From that exact tip, use `superpowers:using-git-worktrees` to create `feature/storage-cli-scaffolding`. First add a failing assertion that `create_app(...).cli.commands` contains `storage-cleanup`. Run it and observe RED. Then import/register the exported command exactly once inside `create_app`:

```python
from app.storage.cli import storage_cleanup

if "storage-cleanup" not in app.cli.commands:
    app.cli.add_command(storage_cleanup)
```

Run the focused test, then stage only the app-factory integration and its assertion:

```bash
git add back/app/__init__.py back/tests/test_storage_cleanup.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "chore(scaffolding): register storage cleanup command"
```

Push `feature/storage-cli-scaffolding`, open an independent PR targeting `feature/remaining-backend`, and apply the exact `scaffolding` label/tag. Require the normal CI/review and merge this PR before Task 9. Then update the delivery worktree to the merged tip and confirm a clean status. The PR diff is exactly `back/app/__init__.py` plus the focused CLI-registration assertion in `back/tests/test_storage_cleanup.py`; no storage business implementation is added to it.

## Task 9: Run the file-storage phase gate and six-dimensional review

**Files:**

- Modify only files required to fix failures caused by Tasks 1–8.

- [ ] **Step 1: Run static and full tests**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest -q
cd ..
git diff --check 63fecb9
```

Expected: every command exits 0, Alembic head is 007, and test count exceeds the post-006 baseline. Convention evidence comes from the exact staged file set immediately before every commit; an empty-index guard run is not evidence.

- [ ] **Step 2: Run migration portability checks**

Run SQLite `006 -> 007 -> 006 -> 007`, MySQL offline upgrade/downgrade compilation, and—only if the configured external MySQL account can create a uniquely named disposable schema—execute `006 -> 007 -> 006 -> 007` there and drop only that schema. Never point downgrade/cleanup at an unknown or shared schema.

- [ ] **Step 3: Run a real Flask/file smoke**

Create a unique `SMOKE_ROOT` with `mktemp -d /private/tmp/asset-storage-smoke.XXXXXX`, then create `$SMOKE_ROOT/empty.env`, `$SMOKE_ROOT/storage`, and use `$SMOKE_ROOT/smoke.db`. Export `ENV_FILE=$SMOKE_ROOT/empty.env`, `DB_URL=sqlite:///$SMOKE_ROOT/smoke.db`, `STORAGE_TYPE=local`, `STORAGE_LOCAL_ROOT=$SMOKE_ROOT/storage`, a test-only JWT secret, and an unused port before migration, server startup, or CLI execution. These environment variables must override the tracked dev profile, and the harness must assert both resolved paths are descendants of `SMOKE_ROOT`. Never use the configured external MySQL or `back/storage` for this smoke.

Upgrade that isolated SQLite database, run `flask db check` there, then start Flask on the unused local port and use HTTP to:

1. authenticate;
2. upload real JPEG, HEIC, PDF, DOC, XLS, DOCX, and XLSX files;
3. reject an extension-spoofed executable/ZIP bomb;
4. list attachments without storage keys;
5. download and hash-compare a document;
6. set/delete a photo cover and confirm download becomes inaccessible;
7. invalidate/replace a document and confirm both historical downloads;
8. invoke `flask storage-cleanup` with the same isolated environment and confirm only eligible bytes disappear and PARTIAL would produce a non-zero exit;
9. attempt holder/manager/out-of-scope access.

Verify no storage root is reachable as a static URL.

- [ ] **Step 4: Commit gate-only fixes**

If corrections were needed, inspect `git status --short`, stage each repair-list path explicitly (never `git add back`, `back/tests`, or another directory), then compare `git diff --cached --name-only` with that repair list before running `scripts/guard-conventions.sh` and committing `fix: close asset storage verification gaps`. Skip this commit when no correction was needed.

- [ ] **Step 5: Execute the review loop**

After each implementation task: spec review, fixes/re-review, then code-quality review, fixes/re-review. After the complete phase, use one independent read-only reviewer to validate:

1. requirement completeness;
2. logical correctness;
3. boundary/security cases;
4. code quality;
5. test coverage;
6. actual runtime results.

The reviewer returns a repair list only. The primary thread fixes it and asks the same reviewer to revalidate until PASS or a concrete external dependency is documented.
