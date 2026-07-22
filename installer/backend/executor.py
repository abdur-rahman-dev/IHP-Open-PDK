import os
import signal
import shutil
import subprocess
import tempfile
import time

from PySide6.QtCore import QThread, Signal

from .models import InstallPlan, ExecStep, ExecStepStatus
from .checker import (
    OSDI_MODELS,
    XYCE_MODELS,
    get_sg13g2_install_source,
    get_sg13g2_local_source_dir,
    get_github_repo_url,
    get_install_destination_check,
    get_sg13g2_destination_check,
    is_program_installed,
)
from .pdk_registry import get_pdk_definition


class InstallExecutor(QThread):
    step_started = Signal(int, str)
    step_finished = Signal(int, str, bool)
    all_done = Signal(bool)
    log_line = Signal(str)

    def __init__(self, plan: InstallPlan):
        super().__init__()
        self.plan = plan
        self.steps: list[ExecStep] = []
        self._cancelled = False
        self._current_proc: subprocess.Popen | None = None
        self._temp_source_root: str | None = None
        self._resolved_source_pdk_dir: str | None = None
        self._temp_dependency_root: str | None = None
        self._resolved_dependency_pdk_dir: str | None = None

    def cancel(self):
        self._cancelled = True
        self._terminate_current_proc()

    def _terminate_current_proc(self):
        proc = self._current_proc
        if not proc:
            return
        try:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                for _ in range(10):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        finally:
            self._current_proc = None

    def run(self):
        try:
            self._build_steps()
            for i, step in enumerate(self.steps):
                if self._cancelled:
                    break
                self.step_started.emit(i, step.label)
                self.log_line.emit("")
                self.log_line.emit(f"Step {i + 1}: {step.label}")
                step.status = ExecStepStatus.RUNNING
                try:
                    ok = self._exec_step(i, step)
                    step.status = ExecStepStatus.DONE if ok else ExecStepStatus.FAILED
                    self.step_finished.emit(i, step.label, ok)
                    if not ok:
                        step.detail = step.detail or "Failed"
                except Exception as e:
                    step.status = ExecStepStatus.FAILED
                    step.detail = str(e)
                    self.step_finished.emit(i, step.label, False)
        finally:
            self._terminate_current_proc()
            self._cleanup_temp_source()
        any_fail = any(s.status == ExecStepStatus.FAILED for s in self.steps)
        self.all_done.emit((not any_fail) and (not self._cancelled))

    def _using_github_source(self) -> bool:
        return self.plan.config.pdk_source_type.value == "github"

    def _github_needs_submodules(self) -> bool:
        cfg = self.plan.config
        return cfg.pdk.value == "ihp-sg13g2" and cfg.get_effective_github_ref() == "dev"

    def _default_source_pdk_dir(self) -> str:
        cfg = self.plan.config
        if cfg.pdk_source_type.value == "local":
            return cfg.get_local_source_pdk_dir()
        return os.path.join(cfg.get_source_pdk_root(), cfg.pdk.value)

    def _resolved_source_pdk_path(self) -> str:
        return self._resolved_source_pdk_dir or self._default_source_pdk_dir()

    def _resolve_cloned_source_pdk_dir(self, clone_dir: str, pdk: str | None = None) -> str | None:
        def looks_like_pdk_dir(path: str) -> bool:
            return os.path.isdir(os.path.join(path, "libs.tech"))

        pdk = pdk or self.plan.config.pdk.value
        nested = os.path.join(clone_dir, pdk)
        if looks_like_pdk_dir(nested):
            return nested
        if looks_like_pdk_dir(clone_dir):
            return clone_dir
        return None

    def _cleanup_temp_source(self):
        for temp_root in (self._temp_source_root, self._temp_dependency_root):
            if temp_root and os.path.exists(temp_root):
                try:
                    shutil.rmtree(temp_root)
                except OSError as exc:
                    self.log_line.emit(f"  Warning: failed to remove temp source: {exc}")
        self._temp_source_root = None
        self._resolved_source_pdk_dir = None
        self._temp_dependency_root = None
        self._resolved_dependency_pdk_dir = None

    def _fetch_github_source(self) -> bool:
        cfg = self.plan.config
        repo = get_github_repo_url(cfg)
        ref = cfg.get_effective_github_ref()
        clone_dir = tempfile.mkdtemp(prefix="ihp-pdk-src-")
        self._temp_source_root = clone_dir

        if cfg.github_source_mode.value == "branch":
            recurse = " --recurse-submodules" if self._github_needs_submodules() else ""
            cmd = f"git clone --branch {ref}{recurse} {repo} {clone_dir}"
            self.log_line.emit(f"  Running: {cmd}")
            ok, _ = self._run_cmd(cmd)
            if not ok:
                return False
        else:
            cmd = f"git clone {repo} {clone_dir}"
            self.log_line.emit(f"  Running: {cmd}")
            ok, _ = self._run_cmd(cmd)
            if not ok:
                return False
            commit = (cfg.resolved_github_commit or cfg.github_commit or "").strip()
            if commit:
                cmd = f"git checkout {commit}"
                self.log_line.emit(f"  Running: {cmd}")
                ok, _ = self._run_cmd(cmd, cwd=clone_dir)
                if not ok:
                    return False
                if cfg.pdk.value == "ihp-sg13g2":
                    cmd = "git submodule update --init --recursive"
                    self.log_line.emit(f"  Running: {cmd}")
                    ok, _ = self._run_cmd(cmd, cwd=clone_dir)
                    if not ok:
                        return False
            elif self._github_needs_submodules():
                cmd = "git submodule update --init --recursive"
                self.log_line.emit(f"  Running: {cmd}")
                ok, _ = self._run_cmd(cmd, cwd=clone_dir)
                if not ok:
                    return False

        resolved = self._resolve_cloned_source_pdk_dir(clone_dir)
        if not resolved:
            self.log_line.emit(f"  Cloned repository does not contain expected PDK structure for {cfg.pdk.value}")
            return False
        self._resolved_source_pdk_dir = resolved
        self.log_line.emit(f"  Prepared GitHub source: {resolved}")
        return True

    def _fetch_sg13g2_dependency(self) -> bool:
        pdk_id = "ihp-sg13g2"
        pdk_def = get_pdk_definition(pdk_id)
        clone_dir = tempfile.mkdtemp(prefix="ihp-sg13g2-src-")
        self._temp_dependency_root = clone_dir
        cmd = (
            f"git clone --branch {pdk_def.default_branch} --recurse-submodules "
            f"{pdk_def.repo_url} {clone_dir}"
        )
        self.log_line.emit(f"  Running: {cmd}")
        ok, _ = self._run_cmd(cmd)
        if not ok:
            return False

        resolved = self._resolve_cloned_source_pdk_dir(clone_dir, pdk_id)
        if not resolved:
            self.log_line.emit("  Cloned repository does not contain expected PDK structure for ihp-sg13g2")
            return False
        self._resolved_dependency_pdk_dir = resolved
        self.log_line.emit(f"  Prepared SG13G2 GitHub source: {resolved}")
        return True

    def _dependency_source_pdk_path(self) -> str:
        return (
            self._resolved_dependency_pdk_dir
            or get_sg13g2_local_source_dir(self.plan.config)
        )

    def _requires_destination_override(self, dest_pdk_dir: str) -> bool:
        rows = list(self.plan.env_checks)
        for row in (
            get_install_destination_check(self.plan.config),
            get_sg13g2_destination_check(self.plan.config),
        ):
            if row is not None and row not in rows:
                rows.append(row)
        return any(
            row.requires_confirmation
            and row.reason_code == "install_destination_override"
            and row.expected_value == dest_pdk_dir
            for row in rows
        )

    def _remove_existing_path(self, path: str):
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)

    def _copy_pdk_dir(self, src_pdk_dir: str, dest_pdk_dir: str) -> bool:
        try:
            os.makedirs(os.path.dirname(dest_pdk_dir), exist_ok=True)
            if self._requires_destination_override(dest_pdk_dir) and os.path.lexists(dest_pdk_dir):
                self.log_line.emit("  Destination PDK already exists, replacing contents")
                self._remove_existing_path(dest_pdk_dir)
            elif os.path.exists(dest_pdk_dir):
                self.log_line.emit("  Destination PDK already exists, merging contents")
            shutil.copytree(src_pdk_dir, dest_pdk_dir, symlinks=True, dirs_exist_ok=True)
            self.log_line.emit(f"  Copied {src_pdk_dir} -> {dest_pdk_dir}")
            return True
        except Exception as exc:
            self.log_line.emit(f"  Copy failed: {exc}")
            return False

    def _build_steps(self):
        cfg = self.plan.config
        pdk_root = self.plan.pdk_root or cfg.get_target_pdk_root()
        pdk = cfg.pdk.value

        source_root = cfg.get_source_pdk_root()
        target_root = cfg.get_target_pdk_root()
        dependency_source, _ = get_sg13g2_install_source(cfg)

        if self._using_github_source():
            self.steps.append(ExecStep("Fetch PDK source from GitHub"))
        if dependency_source == "github":
            self.steps.append(ExecStep("Fetch SG13G2 dependency from GitHub"))

        copy_selected = self._using_github_source() or (
            bool(cfg.install_dir) and target_root != source_root
        )
        if copy_selected:
            self.steps.append(ExecStep(f"Copy PDK to {cfg.get_target_pdk_dir()}"))
        if dependency_source in ("local", "github"):
            dependency_target = cfg.get_target_pdk_dir_for("ihp-sg13g2")
            self.steps.append(ExecStep(f"Copy SG13G2 to {dependency_target}"))
        if cfg.install_dir and (copy_selected or dependency_source in ("local", "github")):
            self.steps.append(ExecStep("Update PDK_ROOT"))

        self.steps.append(ExecStep("Set environment variables in .bashrc"))
        self.steps.append(ExecStep("Create .spiceinit symlink"))

        if cfg.compile_verilog_a:
            openvaf_tool = next(
                (t for t in self.plan.tools if t.name in ("openvaf", "openvaf-r")),
                None,
            )
            if openvaf_tool and openvaf_tool.installed:
                for model in OSDI_MODELS:
                    osdi_path = os.path.join(
                        pdk_root, pdk, "libs.tech", "ngspice", "osdi", f"{model['name']}.osdi"
                    )
                    if not os.path.exists(osdi_path):
                        self.steps.append(ExecStep(f"Compile OSDI: {model['name']}.osdi"))

            from .checker import Simulator
            if Simulator.XYCE in cfg.get_effective_simulators():
                xyce_ok = any(t.name == "Xyce" and t.installed for t in self.plan.tools)
                bxp_ok = any(t.name == "buildxyceplugin" and t.installed for t in self.plan.tools)
                if xyce_ok and bxp_ok:
                    for model in XYCE_MODELS:
                        self.steps.append(ExecStep(f"Compile Xyce plugin: {model['name']}"))

            if Simulator.GNUCAP in cfg.get_effective_simulators():
                gnucap_ok = any(t.name == "gnucap" and t.installed for t in self.plan.tools)
                mg_ok = any(t.name == "gnucap-mg-vams" and t.installed for t in self.plan.tools)
                if gnucap_ok and mg_ok:
                    for model in OSDI_MODELS:
                        self.steps.append(ExecStep(f"Compile gnucap plugin: {model['name']}"))

        from .checker import SchematicEditor
        if SchematicEditor.QUCS_S in cfg.schematic_editors:
            qucs_ok = any(t.name == "qucs-s" and t.installed for t in self.plan.tools)
            if qucs_ok:
                self.steps.append(ExecStep("Setup Qucs-S libraries and examples"))

    def _exec_step(self, idx: int, step: ExecStep) -> bool:
        label = step.label
        cfg = self.plan.config
        pdk_root = self.plan.pdk_root or cfg.get_target_pdk_root()
        pdk = cfg.pdk.value
        home = os.environ.get("HOME", "")

        if label == "Fetch PDK source from GitHub":
            return self._fetch_github_source()

        if label == "Fetch SG13G2 dependency from GitHub":
            return self._fetch_sg13g2_dependency()

        if label.startswith("Copy PDK to"):
            return self._copy_pdk_dir(
                self._resolved_source_pdk_path(),
                cfg.get_target_pdk_dir(),
            )

        if label.startswith("Copy SG13G2 to"):
            return self._copy_pdk_dir(
                self._dependency_source_pdk_path(),
                cfg.get_target_pdk_dir_for("ihp-sg13g2"),
            )

        if label == "Update PDK_ROOT":
            target_root = cfg.get_target_pdk_root()
            os.environ["PDK_ROOT"] = target_root
            self.plan.pdk_root = target_root
            self.log_line.emit(f"  PDK_ROOT updated to {target_root}")
            pdk_root = target_root
            return True

        if label == "Set environment variables in .bashrc":
            return self._write_env(pdk_root, pdk)

        if label == "Create .spiceinit symlink":
            src = os.path.join(pdk_root, pdk, "libs.tech", "ngspice", ".spiceinit")
            dst = os.path.join(home, ".spiceinit")
            if os.path.islink(dst):
                try:
                    if os.path.exists(src) and os.path.exists(os.readlink(dst)):
                        if os.path.samefile(os.readlink(dst), src):
                            self.log_line.emit("  .spiceinit already valid")
                            return True
                except OSError:
                    pass
                os.remove(dst)
            elif os.path.exists(dst):
                self.log_line.emit("  .spiceinit exists but is not a symlink, skipping")
                return True
            try:
                os.symlink(src, dst)
                self.log_line.emit(f"  Created symlink: {dst} -> {src}")
                return True
            except OSError as e:
                self.log_line.emit(f"  Failed: {e}")
                return False

        if label.startswith("Compile OSDI:"):
            model_name = label.split(": ")[1].replace(".osdi", "")
            return self._compile_osdi(pdk_root, pdk, model_name)

        if label.startswith("Compile Xyce plugin:"):
            model_name = label.split(": ")[1]
            return self._compile_xyce(pdk_root, pdk, model_name)

        if label.startswith("Compile gnucap plugin:"):
            model_name = label.split(": ")[1]
            return self._compile_gnucap(pdk_root, pdk, model_name)

        if label == "Setup Qucs-S libraries and examples":
            return self._setup_qucs(pdk_root, pdk)

        return True

    def _write_env(self, pdk_root: str, pdk: str) -> bool:
        home = os.environ.get("HOME", "")
        bashrc = os.path.join(home, ".bashrc")
        if not os.path.exists(bashrc):
            self.log_line.emit("  .bashrc not found")
            return False

        with open(bashrc, "r") as f:
            content = f.read()

        marker = "# >>> IHP-Open-PDK >>>"
        end_marker = "# <<< IHP-Open-PDK <<<"
        if marker in content:
            self.log_line.emit("  IHP-Open-PDK block already in .bashrc")
            return True

        lines = [f'export PDK_ROOT="{pdk_root}"']
        lines.append(f'export PDK="{pdk}"')

        from .checker import LayoutEditor
        if LayoutEditor.KLAYOUT in self.plan.config.layout_editors:
            klayout_path = f"$HOME/.klayout:{pdk_root}/{pdk}/libs.tech/klayout"
            lines.append(f'export KLAYOUT_PATH="{klayout_path}"')
            lines.append(f'export KLAYOUT_HOME="$HOME/.klayout"')

        block = f"\n{marker}\n" + "\n".join(lines) + f"\n{end_marker}\n"

        with open(bashrc, "a") as f:
            f.write(block)

        os.environ["PDK_ROOT"] = pdk_root
        os.environ["PDK"] = pdk

        self.log_line.emit(f"  Appended {len(lines)} env vars to .bashrc")
        return True

    def _run_cmd(self, cmd: str, cwd: str | None = None) -> tuple[bool, str]:
        proc = None
        try:
            popen_kwargs = {
                "shell": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "start_new_session": True,
            }
            if cwd is not None:
                popen_kwargs["cwd"] = cwd
            proc = subprocess.Popen(cmd, **popen_kwargs)
            self._current_proc = proc

            waited = 0.0
            while proc.poll() is None:
                if self._cancelled:
                    self.log_line.emit("  Command cancelled")
                    self._terminate_current_proc()
                    return False, "cancelled"
                time.sleep(0.1)
                waited += 0.1
                if waited >= 600.0:
                    self.log_line.emit("  Command timed out")
                    self._terminate_current_proc()
                    return False, "timeout"

            output = (proc.stdout.read() if proc.stdout else "").strip()
            if output:
                for line in output.split("\n")[:5]:
                    self.log_line.emit(f"  {line}")
            return proc.returncode == 0, output
        except Exception as e:
            self.log_line.emit(f"  Error: {e}")
            return False, str(e)
        finally:
            self._current_proc = None

    def _compile_osdi(self, pdk_root: str, pdk: str, model_name: str) -> bool:
        va_dir = os.path.join(pdk_root, pdk, "libs.tech", "verilog-a")
        osdi_dir = os.path.join(pdk_root, pdk, "libs.tech", "ngspice", "osdi")
        os.makedirs(osdi_dir, exist_ok=True)

        model_map = {m["name"]: m for m in OSDI_MODELS}
        model = model_map.get(model_name)
        if not model:
            self.log_line.emit(f"  Unknown model: {model_name}")
            return False

        compiler = "openvaf-r" if is_program_installed("openvaf-r") else "openvaf"
        src_dir = os.path.join(va_dir, model["src_dir"])
        cmd = f"{compiler} -D__NGSPICE__ {model['va_file']} --output {osdi_dir}/{model_name}.osdi"
        self.log_line.emit(f"  Running: {cmd}")
        ok, _ = self._run_cmd(cmd, cwd=src_dir)
        if ok:
            self.log_line.emit(f"  Compiled {model_name}.osdi")
        return ok

    def _compile_xyce(self, pdk_root: str, pdk: str, model_name: str) -> bool:
        va_dir = os.path.join(pdk_root, pdk, "libs.tech", "verilog-a")
        xyce_dir = os.path.join(pdk_root, pdk, "libs.tech", "xyce", "plugins")
        os.makedirs(xyce_dir, exist_ok=True)

        model_map = {m["name"]: m for m in XYCE_MODELS}
        model = model_map.get(model_name)
        if not model:
            return False

        src_dir = os.path.join(va_dir, model["src_dir"])
        cmd = f"buildxyceplugin {model['va_file']} ../../xyce/plugins"
        self.log_line.emit(f"  Running: {cmd}")
        ok, _ = self._run_cmd(cmd, cwd=src_dir)
        return ok

    def _compile_gnucap(self, pdk_root: str, pdk: str, model_name: str) -> bool:
        va_dir = os.path.join(pdk_root, pdk, "libs.tech", "verilog-a")
        gnucap_dir = os.path.join(pdk_root, pdk, "libs.tech", "gnucap")
        os.makedirs(gnucap_dir, exist_ok=True)

        model_map = {m["name"]: m for m in OSDI_MODELS}
        model = model_map.get(model_name)
        if not model:
            return False

        src_dir = os.path.join(va_dir, model["src_dir"])
        out_so = os.path.join(gnucap_dir, f"{model_name}.so")
        cmd = (f"gnucap-mg-vams --cc {model['va_file']} | "
               f"g++ -xc++ $(gnucap-conf --cppflags) -fPIC -shared - -o {out_so}")
        self.log_line.emit(f"  Running: {cmd}")
        ok, _ = self._run_cmd(cmd, cwd=src_dir)
        return ok

    def _setup_qucs(self, pdk_root: str, pdk: str) -> bool:
        home = os.environ.get("HOME", "")
        lib_src = os.path.join(pdk_root, pdk, "libs.tech", "qucs-s", "user_lib")
        examples_src = os.path.join(pdk_root, pdk, "libs.tech", "qucs-s", "examples")
        overall_ok = True

        for ws in ["/.qucs/", "/QucsWorkspace/"]:
            ws_dir = os.path.join(home, ws.strip("/"))
            user_lib_dst = os.path.join(ws_dir, "user_lib")

            if os.path.isdir(lib_src):
                os.makedirs(user_lib_dst, exist_ok=True)
                for fname in os.listdir(lib_src):
                    src = os.path.join(lib_src, fname)
                    dst = os.path.join(user_lib_dst, fname)
                    if os.path.isfile(src) and not os.path.lexists(dst):
                        try:
                            os.symlink(src, dst)
                        except OSError:
                            pass
                self.log_line.emit(f"  Linked user_lib -> {user_lib_dst}")

            examples_dst = os.path.join(ws_dir, "IHP-Open-PDK-SG13G2-Examples_prj")
            if os.path.isdir(examples_src) and not os.path.lexists(examples_dst):
                try:
                    shutil.copytree(examples_src, examples_dst)
                    if is_program_installed("sed"):
                        ws_name = ws.strip("/")
                        subprocess.run(
                            f"sed -i 's/<qucs_workspace>/{ws_name}/' *.sch",
                            cwd=examples_dst, shell=True, check=False,
                        )
                    self.log_line.emit(f"  Copied examples -> {examples_dst}")
                except Exception as e:
                    self.log_line.emit(f"  Examples copy failed: {e}")
                    overall_ok = False

            pdk_symlink = os.path.join(ws_dir, "IHP-Open-PDK")
            if not os.path.lexists(pdk_symlink):
                try:
                    os.symlink(pdk_root, pdk_symlink)
                    self.log_line.emit(f"  Created PDK symlink: {pdk_symlink}")
                except OSError:
                    pass

        return overall_ok
