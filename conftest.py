"""Repo root on sys.path for tests + test isolation.

La caché de transcodificación (utf8_copy) se redirige a un directorio
temporal: los tests nunca deben escribir en data/work del repo (una colisión
de caché corrompió hallazgos reales una vez).
"""
import os
import tempfile

os.environ.setdefault("MX_WORK_DIR", tempfile.mkdtemp(prefix="mx-test-work-"))
