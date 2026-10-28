"""Private Touchline snapshot listing and bounded, hash-verified dataset import."""
from contextlib import contextmanager
import os
import re
import uuid

from .cloud import available
from .importer import MAX_ZIP_BYTES, import_dataset
from .store import sha_file

SNAPSHOT = re.compile(r'touchline/([a-zA-Z0-9_-]{1,100})/([a-f0-9]{64})/dataset\.zip')


def configuration():
    account = (os.environ.get('MOVEMENT_LENS_AZURE_SOURCE_ACCOUNT_URL') or
               os.environ.get('TOUCHLINE_AZURE_ACCOUNT_URL') or os.environ.get('MOVEMENT_LENS_AZURE_ACCOUNT_URL', '')).rstrip('/')
    container = (os.environ.get('MOVEMENT_LENS_AZURE_SOURCE_CONTAINER') or
                 os.environ.get('TOUCHLINE_AZURE_CONTAINER') or os.environ.get('MOVEMENT_LENS_AZURE_CONTAINER', ''))
    configured = bool(re.fullmatch(r'https://[a-z0-9]{3,24}\.blob\.core\.windows\.net', account) and
                      re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', container) and '--' not in container)
    return {'configured':configured, 'available':configured and available('azure.storage.blob') and available('azure.identity'),
            'account':account if configured else '', 'container':container if configured else ''}


@contextmanager
def source_container():
    config = configuration()
    if not config['available']:
        raise ValueError('Configure the Azure dataset source and install the azure extra; see README')
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient
    try:
        with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
            with ContainerClient(config['account'], config['container'], credential=credential,
                                 connection_timeout=10, read_timeout=60, retry_total=1) as client:
                if client.get_container_properties().get('public_access'):
                    raise ValueError('Choose a private Azure dataset container')
                yield client
    except ValueError:
        raise
    except Exception:
        raise ValueError('Azure dataset access failed. Check sign-in, source container, network and Storage Blob Data Reader access.') from None


def list_datasets(cursor=None):
    if cursor and len(cursor) > 4000:
        raise ValueError('Invalid Azure listing cursor')
    with source_container() as client:
        pages = client.list_blobs(name_starts_with='touchline/', include=['metadata'], results_per_page=100).by_page(continuation_token=cursor)
        page = next(pages, [])
        items = []
        for blob in page:
            match = SNAPSHOT.fullmatch(blob.name)
            if not match or blob.size > MAX_ZIP_BYTES or (blob.metadata or {}).get('sha256') != match[2]:
                continue
            items.append({'blob':blob.name, 'job_id':match[1], 'sha256':match[2], 'bytes':blob.size,
                          'etag':blob.etag, 'modified':blob.last_modified.isoformat() if blob.last_modified else None})
        return {'items':items, 'cursor':pages.continuation_token, 'source':configuration()}


def import_snapshot(store, blob_name, expected_sha256, etag=None, progress=lambda *_: None):
    match = SNAPSHOT.fullmatch(blob_name)
    if not match or match[2] != expected_sha256:
        raise ValueError('Choose an immutable Touchline dataset snapshot and its exact SHA-256')
    path = store.root/'uploads'/(uuid.uuid4().hex+'.zip')
    try:
        from azure.core import MatchConditions
        with source_container() as client:
            blob = client.get_blob_client(blob_name)
            props = blob.get_blob_properties()
            if props.size > MAX_ZIP_BYTES or props.size <= 0:
                raise ValueError('Azure dataset exceeds the 1 GB import limit or is empty')
            if props.metadata.get('sha256') != expected_sha256 or etag and props.etag != etag:
                raise ValueError('Azure snapshot changed or its checksum metadata does not match; refresh the list')
            total = 0
            with path.open('wb') as f:
                for chunk in blob.download_blob(etag=props.etag, match_condition=MatchConditions.IfNotModified).chunks():
                    total += len(chunk)
                    if total > props.size or total > MAX_ZIP_BYTES:
                        raise ValueError('Azure download exceeded its declared size')
                    f.write(chunk)
                    progress('Downloading the private Touchline snapshot', total/props.size*.6)
        if total != props.size or sha_file(path) != expected_sha256:
            raise ValueError('Azure dataset download failed SHA-256/size verification')
        result = import_dataset(store, path, f'azure-{match[1]}-{expected_sha256[:12]}.zip',
                                progress=lambda stage, value: progress(stage, .6+.4*value))
        return result | {'verified_sha256':expected_sha256, 'origin':'azure_blob'}
    finally:
        path.unlink(missing_ok=True)
