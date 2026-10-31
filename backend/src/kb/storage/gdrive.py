"""Google Drive connector: raw sources in a folder of the macOS Google Drive for desktop mount. No OAuth.

    [storage]
    connector = "gdrive"
    [storage.options]
    folder  = "Notes to Obsedian"     # a folder under My Drive that plays the kb root (default: My Drive itself)
    account = "me@gmail.com"          # which GoogleDrive-<account> mount, when several are signed in (optional)
    mount   = "/path/to/GoogleDrive-x"  # the mount itself, overriding the search (optional; tests use this)

Keys keep their logical shape: `raw/printed-docs/a.pdf` is `<mount>/My Drive/<folder>/raw/printed-docs/a.pdf`.
The mount is found on every call, not at construction, so a kb with this connector still loads when Drive is not
running; `auth()` then says what to do. Reads, listing, hashing and immutable `put` behave as for the local folder.
"""
from __future__ import annotations

import glob
import os
import re

from .base import AuthStatus, StorageError
from .localfolder import LocalFolder

MOUNT_GLOB = "~/Library/CloudStorage/GoogleDrive-*"
MY_DRIVE = "My Drive"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class GDrive(LocalFolder):
    name = "gdrive"

    def __init__(self, root: str, folder: str = "", account: str = "", mount: str = "", **options):
        if options:
            raise StorageError(f"gdrive takes the options folder, account and mount (got {sorted(options)})")
        self.kb_root = os.path.abspath(root)
        self.folder = str(folder or "")
        self.account = str(account or "")
        self.mount = os.path.expanduser(str(mount)) if mount else ""
        if self.folder and (self.folder.startswith("/") or ".." in self.folder.split("/")):
            raise StorageError(f"gdrive folder {self.folder!r} must be a relative path without `..`")

    # -- locating the store -------------------------------------------------------------------------------

    def _locate(self) -> str:
        """The folder that plays the kb root, or StorageError saying what is missing and what to do."""
        if self.mount:
            mount = self.mount
            if not os.path.isdir(mount):
                raise StorageError(f"Google Drive mount {mount} does not exist: check the `mount` option")
        else:
            cands = sorted(p for p in glob.glob(os.path.expanduser(MOUNT_GLOB)) if os.path.isdir(p))
            if self.account:
                cands = [p for p in cands if os.path.basename(p) == f"GoogleDrive-{self.account}"]
            if not cands:
                who = f" for {self.account}" if self.account else ""
                raise StorageError(f"no Google Drive mount{who} under ~/Library/CloudStorage/GoogleDrive-*: "
                                   "install Google Drive for desktop, sign in and open Google Drive.app, then retry")
            if len(cands) > 1:
                names = ", ".join(os.path.basename(p).replace("GoogleDrive-", "") for p in cands)
                raise StorageError(f"several Google Drive accounts are mounted ({names}): "
                                   "set `account` in [storage.options]")
            mount = cands[0]
        my_drive = os.path.join(mount, MY_DRIVE)
        if not os.path.isdir(my_drive):
            raise StorageError(f"the Google Drive mount {mount} has no '{MY_DRIVE}' folder: "
                               "open Google Drive.app and check the account is signed in")
        if not self.folder:
            return my_drive
        direct = os.path.join(my_drive, *self.folder.split("/"))
        if os.path.isdir(direct):
            return direct
        want = _slug(self.folder)
        hits = sorted(n for n in os.listdir(my_drive)
                      if os.path.isdir(os.path.join(my_drive, n)) and _slug(n) == want)
        if len(hits) == 1:                         # 'Notes to Obsedian' / 'notes-to-obsedian' spell the same folder
            return os.path.join(my_drive, hits[0])
        if hits:
            raise StorageError(f"folder {self.folder!r} is ambiguous in My Drive: {', '.join(hits)}")
        raise StorageError(f"no folder {self.folder!r} in {my_drive}: create it in Drive or fix `folder`")

    @property
    def root(self) -> str:                         # LocalFolder reads self.root for every path
        return self._locate()

    @root.setter
    def root(self, value):                         # LocalFolder.__init__ is not called; keep the setter harmless
        pass

    def auth(self) -> AuthStatus:
        try:
            self._locate()
        except StorageError as e:
            return AuthStatus(False, str(e))
        return AuthStatus(True)
