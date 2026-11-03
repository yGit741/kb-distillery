"""`ops view pin|unpin|rename`: the one writer of meta/views.json.

Each call changes the file and commits it as one knowledge step (`kb(refine): pin view <name> (kb-x.y.z)`, the same
op the scopes use, through `core.commit_op`, so it is linted, versioned, logged and pushed like any other step). The
HTTP routes call these functions; nothing else writes the file and nothing here runs a raw VCS command.

All three refuse while an ops session is open (409) and put the file back as it was when the step fails.
Each returns `{ok, sha, version, view}`: `sha` is None when the call changed nothing (renaming to the same name).
"""
from __future__ import annotations

from kb_distillery.git import commit_policy as cp
from kb_distillery.ops import core
from kb_distillery.vault import views as vv
from kb_distillery.vault.views import ViewsError

OP = "refine"


def _head(root):
    return core._git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()


def _undo_attempt(root, before, head):
    """A step that did not land: unstage the file and put it back as it was. A step that DID land (HEAD moved, e.g. only
    the push or the autodeploy request failed afterwards) is left alone."""
    if _head(root) != head:
        return
    core._git(root, "reset", "-q", "--", vv.VIEWS_REL)
    vv.write_text(root, before)


def _step(root, view_id, summary, before, view, lint, push):
    """Commit meta/views.json as the one step; if it does not land the file goes back to `before` and the error is relayed
    (409 for a refusal of the ops rules such as lint or not-on-main, 500 for anything unexpected)."""
    head = _head(root)
    try:
        sha = core.commit_op(OP, view_id, summary, paths=[vv.VIEWS_REL], lint=lint, root=root, push=push,
                             _locked=True)
    except core.OpsError as e:
        _undo_attempt(root, before, head)
        raise ViewsError(409, "knowledge step refused: " + str(e)) from e
    except Exception as e:  # noqa: BLE001 - any failure leaves the working tree as it was
        if _head(root) == head:
            _undo_attempt(root, before, head)
            raise ViewsError(500, "knowledge step failed: " + str(e)) from e
        sha = _head(root)                           # the step landed; only a late side effect (push, deploy request) failed
    if not sha:                                     # a real change that no step took: never report it as done
        _undo_attempt(root, before, head)
        raise ViewsError(409, "the change was not committed (the file is owned by another open session); nothing changed")
    version = cp.last_version(root)
    return {"ok": True, "sha": sha, "view": view, "version": ("kb-" + cp.fmt_version(version)) if version else None}


def _change(root, mutate, lint, push):
    """Under the ops lock: read the list, let `mutate(views)` return (new views, the affected view, summary, target), write, commit."""
    try:
        with core.ops_lock(root):
            s = core.current_session(root)
            if s:
                raise ViewsError(409, "an ops session is open (" + s["op"] + " " + s["target"] + ") - finish it first")
            before = vv.read_text(root)
            views = vv.parse(before)
            new, view, summary, target = mutate(views)
            if new == views:                  # nothing to say: no empty step, no log line
                return {"ok": True, "sha": None, "view": view, "version": None}
            vv.write_text(root, vv.render(new) if new else None)
            return _step(root, target, summary, before, view, lint, push)
    except core.OpsError as e:                # the lock, or a session check: a state conflict, not a crash
        raise ViewsError(409, str(e)) from e


def pin(name, spec=None, view_id=None, root=core.ROOT, lint=True, push=True):
    """Pin a view. The id is `view_id` (409 if taken) or a slug of the name made unique."""
    name, spec = vv.clean_name(name), vv.clean_spec(spec)
    wanted = vv.clean_id(view_id) if view_id else None

    def mutate(views):
        if wanted and any(v["id"] == wanted for v in views):
            raise ViewsError(409, f"a view with id {wanted!r} is already pinned")
        view = {"id": wanted or vv.unique_id(views, vv.slugify(name)), "name": name, "created": vv.now_iso(), "spec": spec}
        return views + [view], view, f"pin view {name}", view["id"]
    return _change(root, mutate, lint, push)


def unpin(view_id, root=core.ROOT, lint=True, push=True):
    def mutate(views):
        view = vv.find(views, view_id)
        return [v for v in views if v["id"] != view_id], view, f"unpin view {view['name']}", view_id
    return _change(root, mutate, lint, push)


def rename(view_id, name, root=core.ROOT, lint=True, push=True):
    name = vv.clean_name(name)

    def mutate(views):
        old = vv.find(views, view_id)
        view = {**old, "name": name}
        return [view if v["id"] == view_id else v for v in views], view, f"rename view {old['name']} to {name}", view_id
    return _change(root, mutate, lint, push)
