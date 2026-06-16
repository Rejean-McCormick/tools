from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from ..constants import UPLOAD_HELPER_DOC_PREFIX


@dataclass(frozen=True)
class BundleWriter:
    """
    Implements upload-helper artifacts:
      - single combined upload doc (preferred)
      - legacy grouped bundles + manifest (CORE / DOCS_TOOLS / TESTS_OTHERS)
    """

    output_dir: Path
    output_format: str  # "text" or "xml"
    create_grouped_bundles: bool
    check_stop: Callable[[], None]
    log: Callable[[str], None]

    # New (preferred) mode
    create_single_upload_doc: bool = False
    repo_root: Optional[Path] = None  # used to compute repo folder name for "Code_snapshot_<repo>"
    upload_doc_prefix: str = UPLOAD_HELPER_DOC_PREFIX
    single_upload_artifact_format: str = "txt"  # "txt" or "zip"

    def bundle_extension(self) -> str:
        if (self.output_format or "").strip().lower() == "xml":
            return ".xml.txt"
        return ".txt"

    def single_upload_extension(self) -> str:
        if (self.single_upload_artifact_format or "").strip().lower() == "zip":
            return ".zip"
        return self.bundle_extension()

    def _sanitize_filename_component(self, s: str) -> str:
        if not s:
            return "Repo"
        bad = '<>:"/\\|?*'
        out = []
        for ch in str(s):
            if ch in bad or ord(ch) < 32:
                out.append("_")
            else:
                out.append(ch)
        cleaned = "".join(out).strip()
        return cleaned or "Repo"

    def default_single_doc_name(self) -> str:
        repo_name = "Repo"
        if self.repo_root is not None:
            try:
                repo_name = self.repo_root.resolve().name or "Repo"
            except Exception:
                repo_name = getattr(self.repo_root, "name", "Repo") or "Repo"

        prefix = (
            (self.upload_doc_prefix or UPLOAD_HELPER_DOC_PREFIX).strip()
            or UPLOAD_HELPER_DOC_PREFIX
        )
        repo_name = self._sanitize_filename_component(repo_name)
        return f"{prefix}{repo_name}{self.single_upload_extension()}"

    def classify_volume_group(self, meta: dict) -> str:
        s = " ".join(
            [
                str(meta.get("short_title", "")),
                str(meta.get("title", "")),
                str(meta.get("filename", "")),
            ]
        ).lower()

        if any(k in s for k in ("app", "frontend", "ui", "client", "schema", "schemas", "core")):
            return "CORE"
        if any(k in s for k in ("doc", "docs", "readme", "guide", "manual", "tool", "tools", "script", "scripts")):
            return "DOCS_TOOLS"
        return "TESTS_OTHERS"

    def write_upload_helper_artifacts(self, generated_meta: List[dict]) -> Dict[str, str]:
        """
        Preferred entrypoint: returns either {"single": "<Code_snapshot_Repo.txt>"},
        {"single_zip": "<Code_snapshot_Repo.zip>"}, or legacy grouped artifacts.
        """
        if self.create_single_upload_doc:
            if (self.single_upload_artifact_format or "").strip().lower() == "zip":
                out_name = self.write_single_upload_zip(generated_meta)
                return {"single_zip": out_name} if out_name else {}

            out_name = self.write_single_upload_doc(generated_meta)
            return {"single": out_name} if out_name else {}
        return self.write_grouped_bundles(generated_meta)

    def write_grouped_bundles(self, generated_meta: List[dict]) -> Dict[str, str]:
        """
        Returns mapping:
            {"CORE": "REPO_CORE.txt", "DOCS_TOOLS": "...", "TESTS_OTHERS": "...", "manifest": "REPO_MANIFEST_GROUPED.md"}
        """
        if self.create_single_upload_doc:
            return {}
        if not self.create_grouped_bundles or not generated_meta:
            return {}

        self.check_stop()
        self.log("Phase 3: Writing grouped bundles (upload helpers)...")

        groups: Dict[str, List[dict]] = {"CORE": [], "DOCS_TOOLS": [], "TESTS_OTHERS": []}
        for meta in generated_meta:
            self.check_stop()
            g = self.classify_volume_group(meta)
            groups.setdefault(g, []).append(meta)

        artifacts: Dict[str, str] = {}
        ext = self.bundle_extension()

        for gname, metas in groups.items():
            self.check_stop()
            metas = [m for m in metas if m.get("filename")]
            if not metas:
                continue

            out_name = f"REPO_{gname}{ext}"
            out_path = self.output_dir / out_name

            try:
                with out_path.open("w", encoding="utf-8", errors="replace") as out:
                    for m in metas:
                        self.check_stop()
                        vol_file = self.output_dir / m["filename"]
                        out.write("\n\n")
                        out.write(f"===== BEGIN VOLUME {m['filename']} :: {m.get('title','')} =====\n")
                        with vol_file.open("r", encoding="utf-8", errors="replace") as vf:
                            for line in vf:
                                self.check_stop()
                                out.write(line)
                        out.write(f"\n===== END VOLUME {m['filename']} =====\n")
                artifacts[gname] = out_name
                self.log(f"    -> Created bundle: {out_name}")
            except Exception as e:
                self.log(f"    (warn) Could not create bundle {out_name}: {e}")

        manifest_name = "REPO_MANIFEST_GROUPED.md"
        manifest_path = self.output_dir / manifest_name

        try:
            with manifest_path.open("w", encoding="utf-8") as mf:
                mf.write("# Repo bundle (grouped for file upload limits)\n\n")
                mf.write("## Upload these (recommended)\n")
                mf.write(f"- `{manifest_name}`\n")
                for k in ("CORE", "DOCS_TOOLS", "TESTS_OTHERS"):
                    if k in artifacts:
                        mf.write(f"- `{artifacts[k]}`\n")

                mf.write("\n## How to navigate\n")
                mf.write("1) Search in this manifest for the file path you need.\n")
                mf.write("2) Note the `volume` and `bundle`.\n")
                if (self.output_format or "").strip().lower() == "xml":
                    mf.write('3) Open the bundle file and search for `<file path="...">`.\n')
                else:
                    mf.write('3) Open the bundle file and search for `path="..."` under `----- FILE BEGIN -----`.\n')
                mf.write("4) Read the relevant content / chunk(s).\n\n")

                mf.write("## File locator index (path → volume → bundle)\n")
                mf.write("```text\n")
                for meta in generated_meta:
                    self.check_stop()
                    vol = meta.get("filename", "")
                    grp = self.classify_volume_group(meta)
                    bundle = artifacts.get(grp, "")
                    for p in meta.get("contained_files", []) or []:
                        self.check_stop()
                        mf.write(f"{p}\tvolume={vol}\tbundle={bundle or '(none)'}\n")
                mf.write("```\n")

            artifacts["manifest"] = manifest_name
            self.log(f"    -> Created manifest: {manifest_name}")
        except Exception as e:
            self.log(f"    (warn) Could not create manifest {manifest_name}: {e}")

        return artifacts

    def write_single_upload_zip(
        self,
        generated_meta: List[dict],
        *,
        out_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Writes ONE upload-helper archive instead of one concatenated text document.

        The archive contains the generated volume files at the archive root and a
        small manifest that lists what was included. This preserves the original
        per-volume files instead of flattening them into one large .txt/.xml.txt.

        Naming default: "Code_snapshot_<repo_folder_name>.zip".

        Returns the filename on success, else None.
        """
        if not generated_meta:
            return None

        self.check_stop()

        final_name = out_name or self.default_single_doc_name()
        if not final_name.lower().endswith(".zip"):
            final_name = f"{Path(final_name).stem}.zip"

        out_path = self.output_dir / final_name
        included: List[str] = []

        try:
            with ZipFile(out_path, "w", compression=ZIP_DEFLATED) as zf:
                manifest_lines = [
                    "# Single upload archive",
                    "",
                    f"- generated_at: {datetime.now().isoformat()}",
                    f"- output_format: {(self.output_format or '').strip().lower() or 'text'}",
                    f"- volumes: {len([m for m in generated_meta if m.get('filename')])}",
                    "",
                    "## Files in this archive",
                ]

                for m in generated_meta:
                    self.check_stop()
                    filename = str(m.get("filename") or "")
                    if not filename:
                        continue

                    vol_file = self.output_dir / filename
                    if not vol_file.exists() or not vol_file.is_file():
                        self.log(f"    (warn) Missing volume skipped in zip: {filename}")
                        continue

                    zf.write(vol_file, arcname=filename)
                    included.append(filename)
                    manifest_lines.append(f"- `{filename}` — {m.get('title', '')}")

                manifest_lines.extend([
                    "",
                    "## File locator index (path → volume)",
                    "",
                    "```text",
                ])
                for m in generated_meta:
                    self.check_stop()
                    vol = str(m.get("filename") or "")
                    if not vol:
                        continue
                    for rel_path in m.get("contained_files", []) or []:
                        self.check_stop()
                        manifest_lines.append(f"{rel_path}\tvolume={vol}")
                manifest_lines.append("```")

                manifest_text = "\n".join(manifest_lines).rstrip() + "\n"
                zf.writestr("ZIP_MANIFEST.md", manifest_text)

            self.log(f"    -> Created single upload zip: {final_name} ({len(included)} volume file(s))")
            return final_name
        except Exception as e:
            self.log(f"    (warn) Could not create single upload zip {final_name}: {e}")
            return None

    def write_single_upload_doc(
        self,
        generated_meta: List[dict],
        *,
        out_name: Optional[str] = None,
        header: Optional[str] = None,
    ) -> Optional[str]:
        """
        Writes ONE combined upload-helper file that concatenates all volume files.

        Naming default: "Code_snapshot_<repo_folder_name><ext>"
        where <repo_folder_name> comes from repo_root.name.

        Returns the filename on success, else None.
        """
        if not generated_meta:
            return None

        self.check_stop()

        final_name = out_name or self.default_single_doc_name()
        out_path = self.output_dir / final_name

        if header is None:
            header = (
                "# Single upload doc\n\n"
                f"- generated_at: {datetime.now().isoformat()}\n"
                f"- output_format: {(self.output_format or '').strip().lower() or 'text'}\n"
                f"- volumes: {len([m for m in generated_meta if m.get('filename')])}\n"
            )

        try:
            with out_path.open("w", encoding="utf-8", errors="replace") as out:
                if header:
                    out.write(header.rstrip() + "\n\n")

                for m in generated_meta:
                    self.check_stop()
                    if not m.get("filename"):
                        continue

                    vol_file = self.output_dir / m["filename"]
                    out.write("\n\n")
                    out.write(f"===== BEGIN VOLUME {m['filename']} :: {m.get('title','')} =====\n")

                    with vol_file.open("r", encoding="utf-8", errors="replace") as vf:
                        for line in vf:
                            self.check_stop()
                            out.write(line)

                    out.write(f"\n===== END VOLUME {m['filename']} =====\n")

            self.log(f"    -> Created single upload doc: {final_name}")
            return final_name
        except Exception as e:
            self.log(f"    (warn) Could not create single upload doc {final_name}: {e}")
            return None