"""Receives JPEGs uploaded by the camera's FTP-transfer feature and hands each one to the main
app as it completes, via a thread-safe queue - the same "background thread signals the main
thread" shape used throughout custard_cream_camera.py for publish/print/AI-edit work.
"""

from pathlib import Path
from threading import Thread

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class _ReceiverHandler(FTPHandler):
    """pyftpdlib creates one handler instance per connection itself, with no hook to pass extra
    constructor args through - so FTPReceiver.__init__ sets save_dir/incoming_queue as class
    attributes once, before the server starts, and every connection's on_file_received() sees
    the same shared state via self.
    """
    save_dir = None
    incoming_queue = None

    def on_file_received(self, file_path):
        """Flattens the just-completed upload into save_dir (renaming on collision), ignoring
        whatever subfolder the camera's FTP client placed it under, and lower-cases the
        extension - cameras write e.g. `DSC01234.JPG`, and the shared Play-mode code globs
        `*.jpg`, which is case-sensitive on Linux; without this the photos would silently never
        show up. Non-JPEG uploads (e.g. a simultaneous RAW file) are left where they landed,
        untouched and un-previewed.
        """
        src = Path(file_path)
        if src.suffix.lower() not in (".jpg", ".jpeg"):
            print(f"FTP: received non-JPEG {src.name}, leaving it where it landed")
            return

        dest = self.save_dir / (src.stem + ".jpg")
        counter = 2
        while dest.exists():
            dest = self.save_dir / f"{src.stem}_{counter}.jpg"
            counter += 1

        src.replace(dest)
        print(f"FTP: received {src.name}, saved as {dest}")
        self.incoming_queue.put(dest)


class FTPReceiver:
    """Runs an FTP server on a background thread. The camera can log in, optionally create/`CWD`
    into a dated subfolder (some cameras always do this - it doesn't matter which), and upload
    JPEGs; each completed upload is flattened into `save_dir` and queued on `incoming_queue` for
    the main thread to pick up and preview.
    """

    def __init__(self, settings, save_dir, incoming_queue):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        incoming_dir = Path(settings.get("incoming_dir", "ftp_incoming"))
        incoming_dir.mkdir(parents=True, exist_ok=True)

        authorizer = DummyAuthorizer()
        # "elmw": list, cwd-into-subfolder, makedir, write - enough for a camera to log in,
        # optionally create a dated folder, and upload; no read/rename/delete needed since
        # nothing here ever needs to fetch or remove a file back off the server.
        authorizer.add_user(
            settings.get("username", "sony"),
            settings.get("password", "changeme"),
            str(incoming_dir),
            perm="elmw",
        )

        _ReceiverHandler.authorizer = authorizer
        _ReceiverHandler.save_dir = self.save_dir
        _ReceiverHandler.incoming_queue = incoming_queue

        self.server = FTPServer((settings.get("host", "0.0.0.0"), settings.get("port", 2121)), _ReceiverHandler)
        self.thread = None

    def start(self):
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.close_all()
