"""Local immutable artifacts. No connection to Touchline's live database."""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get('MOVEMENT_LENS_STATE', Path(__file__).resolve().parents[1] / 'runtime')).resolve()
        self.lock = threading.RLock()
        for name in ('datasets', 'analyses', 'jobs', 'reports', 'uploads', 'explorations', 'reviews', 'explanations', 'cluster_workspaces'):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def path(self, kind, identity):
        if kind not in {'datasets', 'analyses', 'jobs', 'reports', 'explorations', 'reviews', 'explanations', 'cluster_workspaces'} or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', identity):
            raise ValueError('Invalid artifact identifier')
        return self.root / kind / identity

    def read(self, kind, identity):
        p = self.path(kind, identity) / 'record.json'
        if not p.is_file():
            raise KeyError('Artifact not found')
        return json.loads(p.read_text())

    def write(self, kind, identity, value):
        p = self.path(kind, identity)
        with self.lock:
            p.mkdir(parents=True, exist_ok=True)
            temp = p / f'.{uuid.uuid4().hex}.json'
            temp.write_text(json.dumps(value, allow_nan=False))
            temp.replace(p / 'record.json')
        return value

    def list(self, kind):
        records = []
        for p in (self.root / kind).glob('*/record.json'):
            records.append(json.loads(p.read_text()))
        return sorted(records, key=lambda x: x.get('created', 0), reverse=True)

    def job(self, action):
        jid = uuid.uuid4().hex[:20]
        self.write('jobs', jid, {'id': jid, 'action': action, 'status': 'queued', 'stage': 'Queued', 'progress': 0, 'created': time.time()})
        return jid

    def progress(self, jid, stage, progress):
        self.write('jobs', jid, self.read('jobs', jid) | {'status': 'working', 'stage': stage, 'progress': progress})

    def run(self, jid, fn, *args):
        try:
            result = fn(*args, progress=lambda stage, pct: self.progress(jid, stage, pct))
            self.write('jobs', jid, self.read('jobs', jid) | {'status': 'done', 'stage': 'Complete', 'progress': 1, 'result': result})
        except Exception as error:
            # SDK exceptions are handled at their boundary; never expose credentials.
            message = str(error) if isinstance(error, (ValueError, KeyError)) else 'This job failed. Check the local server log and input files.'
            self.write('jobs', jid, self.read('jobs', jid) | {'status': 'error', 'stage': 'Stopped', 'error': message})
            if not isinstance(error, (ValueError, KeyError)):
                import logging
                logging.getLogger(__name__).exception('Movement Lens job failed')
