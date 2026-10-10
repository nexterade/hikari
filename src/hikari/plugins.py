"""Opt-in local plugin loader. Only load plugins whose code you trust."""
from __future__ import annotations
import importlib.util, logging, os
from pathlib import Path
log = logging.getLogger(__name__)
class Plugin:
    name = "plugin"; version = "0.0.0"; description = ""
    def register(self, cli): raise NotImplementedError

def load_plugins(cli, directory: str | Path | None = None) -> list[Plugin]:
    if os.environ.get("HIKARI_NO_PLUGINS") == "1": return []
    folder = Path(directory) if directory else Path(os.environ.get("HIKARI_HOME", Path.home() / ".hikari")) / "plugins"
    loaded = []
    if not folder.is_dir(): return loaded
    for file in sorted(folder.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"hikari_user_plugin_{file.stem}", file)
            if not spec or not spec.loader: continue
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            plugin = getattr(module, "PLUGIN", None)
            if isinstance(plugin, Plugin): plugin.register(cli); loaded.append(plugin)
            else: log.warning("Plugin %s has no PLUGIN instance", file.name)
        except Exception as exc: log.warning("Could not load plugin %s: %s", file.name, exc)
    return loaded
