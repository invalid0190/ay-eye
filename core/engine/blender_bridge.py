"""
Local Blender bridge client and bootstrap script.

Ay-Eye should not drive Blender by clicking menus. This bridge mirrors the
shape of Blender MCP integrations: a tiny local server runs inside Blender,
executes Python on Blender's main thread, and returns structured results.
"""

from __future__ import annotations

import json
import socket
from typing import Any


HOST = "127.0.0.1"
PORT = 8765


def build_bootstrap_script(host: str = HOST, port: int = PORT) -> str:
    """Return Python code that starts Ay-Eye's local bridge inside Blender."""
    return f"""
import bpy
import contextlib
import io
import json
import queue
import socket
import threading
import time
import traceback

HOST = {host!r}
PORT = {int(port)}
NS = bpy.app.driver_namespace

def _ayeye_scene_summary():
    try:
        objects = list(bpy.context.scene.objects)
        return {{
            'object_count': len(objects),
            'mesh_count': len([ob for ob in objects if getattr(ob, 'type', '') == 'MESH']),
            'object_names': [ob.name for ob in objects[:40]],
        }}
    except Exception as exc:
        return {{'object_count': -1, 'mesh_count': -1, 'object_names': [], 'summary_error': str(exc)}}

if NS.get('_ayeye_bridge_ready'):
    print('AYEYE_BRIDGE_READY: already running on {{}}:{{}}'.format(HOST, PORT))
else:
    request_queue = queue.Queue()

    def _ayeye_process_queue():
        while True:
            try:
                item = request_queue.get_nowait()
            except queue.Empty:
                break

            code = item.get('code') or ''
            description = item.get('description') or 'Blender Python'
            result_box = item['result_box']
            done = item['done']
            before = _ayeye_scene_summary()
            stdout_buffer = io.StringIO()

            try:
                scope = {{'bpy': bpy, '__name__': '__ayeye_blender_exec__'}}
                with contextlib.redirect_stdout(stdout_buffer):
                    exec(code, scope, scope)
                after = _ayeye_scene_summary()
                result_box['response'] = {{
                    'ok': True,
                    'description': description,
                    'stdout': stdout_buffer.getvalue()[-4000:],
                    'before': before,
                    'after': after,
                }}
            except Exception:
                after = _ayeye_scene_summary()
                result_box['response'] = {{
                    'ok': False,
                    'description': description,
                    'stdout': stdout_buffer.getvalue()[-4000:],
                    'error': traceback.format_exc()[-8000:],
                    'before': before,
                    'after': after,
                }}
            finally:
                done.set()

        return 0.05

    bpy.app.timers.register(_ayeye_process_queue, persistent=True)

    def _ayeye_send(conn, payload):
        conn.sendall((json.dumps(payload, ensure_ascii=False) + '\\n').encode('utf-8'))

    def _ayeye_handle_client(conn):
        with conn:
            try:
                raw = b''
                while not raw.endswith(b'\\n'):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > 1000000:
                        raise RuntimeError('request too large')

                if not raw:
                    return
                request = json.loads(raw.decode('utf-8'))
                op = request.get('op')

                if op == 'ping':
                    _ayeye_send(conn, {{'ok': True, 'ready': True, 'scene': _ayeye_scene_summary()}})
                    return

                if op != 'exec':
                    _ayeye_send(conn, {{'ok': False, 'error': 'unsupported op: {{}}'.format(op)}})
                    return

                done = threading.Event()
                result_box = {{}}
                request_queue.put({{
                    'code': request.get('code') or '',
                    'description': request.get('description') or 'Blender Python',
                    'done': done,
                    'result_box': result_box,
                }})

                timeout = float(request.get('timeout') or 60)
                if not done.wait(timeout):
                    _ayeye_send(conn, {{
                        'ok': False,
                        'error': 'Timed out waiting for Blender main thread after {{:.1f}}s'.format(timeout),
                        'after': _ayeye_scene_summary(),
                    }})
                    return

                _ayeye_send(conn, result_box.get('response') or {{'ok': False, 'error': 'empty response'}})
            except Exception:
                try:
                    _ayeye_send(conn, {{'ok': False, 'error': traceback.format_exc()[-8000:]}})
                except Exception:
                    pass

    def _ayeye_server_loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(8)
        NS['_ayeye_bridge_socket'] = server
        while True:
            conn, _addr = server.accept()
            threading.Thread(target=_ayeye_handle_client, args=(conn,), daemon=True).start()

    NS['_ayeye_bridge_ready'] = True
    NS['_ayeye_bridge_queue'] = request_queue
    threading.Thread(target=_ayeye_server_loop, daemon=True).start()
    print('AYEYE_BRIDGE_READY: listening on {{}}:{{}}'.format(HOST, PORT))
"""


class BlenderBridgeClient:
    """Small JSON-over-localhost client for the Blender bridge."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = int(port)

    def ping(self, timeout: float = 0.35) -> dict[str, Any] | None:
        try:
            return self._request({"op": "ping"}, timeout=timeout)
        except OSError:
            return None
        except Exception:
            return None

    def execute(self, code: str, description: str, timeout: float = 60) -> dict[str, Any]:
        return self._request(
            {
                "op": "exec",
                "code": code,
                "description": description,
                "timeout": timeout,
            },
            timeout=timeout + 5,
        )

    def _request(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            raw = b""
            while not raw.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                raw += chunk
        if not raw:
            return {"ok": False, "error": "empty response from Blender bridge"}
        return json.loads(raw.decode("utf-8"))
