from types import SimpleNamespace

from src.gui import app_bootstrap


class _RootStub:
    def __init__(self) -> None:
        self.withdrawn = False

    def withdraw(self) -> None:
        self.withdrawn = True


class _DnDWrapperStub:
    _subst_format_dnd = ("%D",)
    _subst_format_str_dnd = "%D"

    def dnd_bind(self, sequence=None, func=None, add=None):
        return ("bind", sequence, func, add)

    def drop_target_register(self, *dndtypes):
        return ("register", dndtypes)

    def drop_target_unregister(self):
        return "unregister"


class _TkinterDnDStub:
    DnDWrapper = _DnDWrapperStub
    required_roots: list[_RootStub] = []

    @classmethod
    def require(cls, root: _RootStub) -> str:
        cls.required_roots.append(root)
        return "2.10.1"


def test_install_tkdnd_root_methods_bridges_plain_tk_root(monkeypatch) -> None:
    monkeypatch.setattr(
        app_bootstrap,
        "TkinterDnD",
        SimpleNamespace(DnDWrapper=_DnDWrapperStub),
    )
    root = SimpleNamespace()

    app_bootstrap._install_tkdnd_root_methods(root)

    assert root._subst_format_dnd == ("%D",)
    assert root._subst_format_str_dnd == "%D"
    assert root.drop_target_register("DND_Files") == ("register", ("DND_Files",))
    assert root.dnd_bind("<<Drop>>", "callback", "+") == (
        "bind",
        "<<Drop>>",
        "callback",
        "+",
    )


def test_create_root_loads_tkdnd_on_standard_hidden_root(monkeypatch) -> None:
    _TkinterDnDStub.required_roots = []
    monkeypatch.setattr(app_bootstrap.tk, "Tk", _RootStub)
    monkeypatch.setattr(app_bootstrap, "TkinterDnD", _TkinterDnDStub)

    root = app_bootstrap.create_root()

    assert root.withdrawn is True
    assert _TkinterDnDStub.required_roots == [root]
    assert root._tkdnd_enabled is True
    assert root.drop_target_register("DND_Files") == ("register", ("DND_Files",))
