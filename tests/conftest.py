"""共用夹具：在 node 里跑 docs/analysis.js。

浏览器版的算法是纯 JavaScript，测试把同一段信号分别喂给 Python 和 node，比对结果。
本地没装 node 时这些测试跳过；CI 设置 SPF_REQUIRE_NODE=1，缺 node 直接失败，
免得一致性测试在 CI 里悄悄全部跳过。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"
ANALYSIS_JS = DOCS / "analysis.js"

RunJs = Callable[..., Any]


@pytest.fixture(scope="session")
def node() -> str:
    exe = shutil.which("node")
    if exe is None:
        if os.environ.get("SPF_REQUIRE_NODE"):
            pytest.fail("SPF_REQUIRE_NODE is set but node is not on PATH")
        pytest.skip("node not installed")
    return exe


@pytest.fixture
def run_js(node: str) -> RunJs:
    """run_js(body, **arrays) → body 的 JSON 输出。

    body 里可以用 SPF（docs/analysis.js 导出的全部函数）、按名字取到的
    Float64Array 输入，以及 out(obj) 把结果交回 Python。
    """

    def run(body: str, **arrays: np.ndarray) -> Any:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            loads = []
            for name, arr in arrays.items():
                (d / f"{name}.f64").write_bytes(
                    np.ascontiguousarray(arr, dtype=np.float64).tobytes()
                )
                loads.append(
                    f"const {name} = load({json.dumps(str(d / f'{name}.f64'))});"
                )
            script = "\n".join(
                [
                    '"use strict";',
                    'const fs = require("fs");',
                    f"const SPF = require({json.dumps(str(ANALYSIS_JS))});",
                    "const load = p => { const b = fs.readFileSync(p);"
                    " return new Float64Array(b.buffer, b.byteOffset, b.length / 8); };",
                    "const out = o => process.stdout.write(JSON.stringify(o));",
                    *loads,
                    body,
                ]
            )
            (d / "run.cjs").write_text(script, encoding="utf-8")
            proc = subprocess.run(
                [node, str(d / "run.cjs")],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    return run
