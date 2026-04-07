"""Automated SQLite backups to Cloudflare R2 (S3-compatible).

Runs a daily backup on a background thread. Enabled via BACKUP_ENABLED=true.
Requires: BACKUP_R2_ENDPOINT, BACKUP_R2_ACCESS_KEY, BACKUP_R2_SECRET_KEY, BACKUP_R2_BUCKET
"""

import logging
import os
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

BACKUP_INTERVAL = 86400  # 24 hours in seconds
RETENTION_DAYS = 30


def _get_client():
    """Create an S3 client for R2."""
    import boto3
    return boto3.client(
        's3',
        endpoint_url=os.environ['BACKUP_R2_ENDPOINT'],
        aws_access_key_id=os.environ['BACKUP_R2_ACCESS_KEY'],
        aws_secret_access_key=os.environ['BACKUP_R2_SECRET_KEY'],
        region_name='auto',
    )


def _run_backup(db_path):
    """Copy the live SQLite DB safely and upload to R2."""
    try:
        # Atomic copy using sqlite3.backup()
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp.name)
        src.backup(dst)
        dst.close()
        src.close()

        # Upload to R2
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
        key = f'backups/arima-{timestamp}.db'
        client = _get_client()
        client.upload_file(tmp.name, os.environ['BACKUP_R2_BUCKET'], key)
        logger.info('Backup uploaded: %s', key)

        # Clean up temp file
        os.unlink(tmp.name)

        # Retention: delete backups older than 30 days
        _cleanup_old_backups(client)

    except Exception:
        logger.exception('Backup failed')
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _cleanup_old_backups(client):
    """Delete backups older than RETENTION_DAYS."""
    bucket = os.environ['BACKUP_R2_BUCKET']
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    try:
        response = client.list_objects_v2(Bucket=bucket, Prefix='backups/')
        for obj in response.get('Contents', []):
            if obj['LastModified'].replace(tzinfo=timezone.utc) < cutoff:
                client.delete_object(Bucket=bucket, Key=obj['Key'])
                logger.info('Deleted old backup: %s', obj['Key'])
    except Exception:
        logger.exception('Backup cleanup failed')


def _backup_loop(db_path):
    """Run backup and schedule the next one."""
    _run_backup(db_path)
    t = threading.Timer(BACKUP_INTERVAL, _backup_loop, args=[db_path])
    t.daemon = True
    t.start()


def start_backup_scheduler(app):
    """Start the backup scheduler if enabled. Call after migrations."""
    if os.environ.get('BACKUP_ENABLED', '').lower() != 'true':
        return

    for var in ('BACKUP_R2_ENDPOINT', 'BACKUP_R2_ACCESS_KEY', 'BACKUP_R2_SECRET_KEY', 'BACKUP_R2_BUCKET'):
        if not os.environ.get(var):
            logger.warning('Backup disabled: missing %s', var)
            return

    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if not db_path.startswith('/'):
        db_path = os.path.join(app.root_path, '..', db_path)

    logger.info('Starting backup scheduler (every %ds, %dd retention)', BACKUP_INTERVAL, RETENTION_DAYS)

    # Run first backup on a background thread (don't block startup)
    t = threading.Timer(5, _backup_loop, args=[db_path])
    t.daemon = True
    t.start()
