"""Helpers for keeping incomplete downloads out of the visible destination folder."""

import ctypes
import logging
import os
import shutil


_STAGING_DIRECTORY = ".pdm-incomplete"
_logger = logging.getLogger(__name__)


def get_task_staging_dir(destination_path: str, task_id: int) -> str:
    destination_dir = os.path.dirname(os.path.abspath(destination_path))
    staging_root = os.path.join(destination_dir, _STAGING_DIRECTORY)
    task_dir = os.path.join(staging_root, str(task_id))
    os.makedirs(task_dir, exist_ok=True)

    if os.name == "nt":
        _set_hidden(staging_root)

    return task_dir


def get_staging_path(destination_path: str, task_id: int, filename: str) -> str:
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("A staging filename is required.")
    return os.path.join(get_task_staging_dir(destination_path, task_id), safe_name)


def cleanup_task_staging_dir(destination_path: str, task_id: int) -> None:
    task_dir = os.path.join(
        os.path.dirname(os.path.abspath(destination_path)),
        _STAGING_DIRECTORY,
        str(task_id),
    )
    if os.path.isdir(task_dir):
        try:
            shutil.rmtree(task_dir)
        except OSError:
            _logger.warning("Could not remove completed download staging directory: %s", task_dir, exc_info=True)


def _set_hidden(path: str) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_attributes = kernel32.GetFileAttributesW
    get_attributes.argtypes = [ctypes.c_wchar_p]
    get_attributes.restype = ctypes.c_uint32
    set_attributes = kernel32.SetFileAttributesW
    set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    set_attributes.restype = ctypes.c_int

    attributes = get_attributes(path)
    if attributes == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    if attributes & 0x2:
        return
    if not set_attributes(path, attributes | 0x2):
        raise ctypes.WinError(ctypes.get_last_error())
