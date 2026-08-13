"""图像生成适配器测试：不可用时诚实降级为外部任务包，绝不假装生成。"""
from __future__ import annotations

import json

import pytest

from aipd_os.imggen.adapter import ImageGenAdapter, ImageGenUnavailable


def test_unavailable_generate_raises(tmp_path) -> None:
    a = ImageGenAdapter()  # 未配置后端/密钥
    assert a.available() is False
    with pytest.raises(ImageGenUnavailable):
        a.generate("一张产品图", (1024, 1024), str(tmp_path / "fig.png"), seed=1)


def test_unavailable_write_external_task_package(tmp_path) -> None:
    a = ImageGenAdapter()
    out = tmp_path / "figures" / "cover.png"
    pkg = a.write_external_task_package("封面产品图", (1024, 1024), str(out))
    assert pkg["status"] == "external_pending"
    assert pkg["prompt"] == "封面产品图"
    assert pkg["expected_path"] == str(out)
    # 任务包 JSON 文件已写出
    task = out.with_suffix(".png.task.json")
    assert task.exists()
    loaded = json.loads(task.read_text(encoding="utf-8"))
    assert loaded["job_type"] == "image_generation"
    assert loaded["size"]["width"] == 1024
    # 绝不生成假图片
    assert not out.exists()
