from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import lmdb

logger = logging.getLogger(__name__)

_NODE_PREFIX = b"n:"
_EDGE_PREFIX = b"e:"
_META_PREFIX = b"m:"


class LMDBStore:
    """LMDB-backed key-value store for the volatile case graph.

    The case graph is **not** permanent: each session opens its own LMDB
    environment which is destroyed when the session is explicitly closed.
    This honours the forensic requirement that client data never becomes
    permanent system memory, while LMDB gives us fast ACID reads/writes
    with zero daemon process (unlike Redis).
    """

    def __init__(self, path: str | Path, readonly: bool = False, max_dbs: int = 5) -> None:
        self._path = str(path)
        Path(self._path).mkdir(parents=True, exist_ok=True)
        self._env = lmdb.open(
            self._path,
            map_size=256 * 1024 * 1024,
            max_dbs=max_dbs,
            subdir=True,
            readonly=readonly,
            lock=True,
        )
        self._db_nodes = self._env.open_db(b"nodes")
        self._db_edges = self._env.open_db(b"edges")
        self._db_meta = self._env.open_db(b"meta")
        self._closed = False

    # ---- low-level node ops ----

    def put_node(self, key: str, data: dict[str, Any]) -> None:
        k = _NODE_PREFIX + key.encode()
        v = json.dumps(data, default=str).encode()
        with self._env.begin(db=self._db_nodes, write=True) as txn:
            txn.put(k, v)

    def get_node(self, key: str) -> dict[str, Any] | None:
        k = _NODE_PREFIX + key.encode()
        with self._env.begin(db=self._db_nodes) as txn:
            raw = txn.get(k)
        if raw is None:
            return None
        return json.loads(raw)

    def delete_node(self, key: str) -> None:
        k = _NODE_PREFIX + key.encode()
        with self._env.begin(db=self._db_nodes, write=True) as txn:
            txn.delete(k)

    def iter_nodes(self) -> Iterator[tuple[str, dict[str, Any]]]:
        with self._env.begin(db=self._db_nodes) as txn:
            cursor = txn.cursor()
            for raw_key, raw_val in cursor:
                k = raw_key.decode()
                if k.startswith("n:"):
                    yield k[2:], json.loads(raw_val)

    # ---- low-level edge ops ----

    def put_edge(self, key: str, data: dict[str, Any]) -> None:
        k = _EDGE_PREFIX + key.encode()
        v = json.dumps(data, default=str).encode()
        with self._env.begin(db=self._db_edges, write=True) as txn:
            txn.put(k, v)

    def get_edge(self, key: str) -> dict[str, Any] | None:
        k = _EDGE_PREFIX + key.encode()
        with self._env.begin(db=self._db_edges) as txn:
            raw = txn.get(k)
        if raw is None:
            return None
        return json.loads(raw)

    def iter_edges(self) -> Iterator[tuple[str, dict[str, Any]]]:
        with self._env.begin(db=self._db_edges) as txn:
            cursor = txn.cursor()
            for raw_key, raw_val in cursor:
                k = raw_key.decode()
                if k.startswith("e:"):
                    yield k[2:], json.loads(raw_val)

    # ---- meta / case-level storage ----

    def put_meta(self, key: str, data: Any) -> None:
        k = _META_PREFIX + key.encode()
        v = json.dumps(data, default=str).encode()
        with self._env.begin(db=self._db_meta, write=True) as txn:
            txn.put(k, v)

    def get_meta(self, key: str) -> Any | None:
        k = _META_PREFIX + key.encode()
        with self._env.begin(db=self._db_meta) as txn:
            raw = txn.get(k)
        if raw is None:
            return None
        return json.loads(raw)

    # ---- lifecycle ----

    def destroy(self) -> None:
        """Close the environment and delete all on-disk data."""
        if not self._closed:
            self._env.close()
            self._closed = True
        import shutil
        if os.path.exists(self._path):
            shutil.rmtree(self._path, ignore_errors=True)
        logger.info("LMDB store destroyed at %s", self._path)

    def close(self) -> None:
        if not self._closed:
            self._env.close()
            self._closed = True

    def __enter__(self) -> "LMDBStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def stats(self) -> dict[str, int]:
        with self._env.begin(db=self._db_nodes) as txn:
            node_count = txn.stat(self._db_nodes)["entries"]
        with self._env.begin(db=self._db_edges) as txn:
            edge_count = txn.stat(self._db_edges)["entries"]
        with self._env.begin(db=self._db_meta) as txn:
            meta_count = txn.stat(self._db_meta)["entries"]
        return {"nodes": node_count, "edges": edge_count, "meta": meta_count}
