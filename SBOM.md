# SBOM（软件物料清单）

AIPD-OS 使用内置、确定性的 SBOM 生成器（`aipd_os/security/sbom.py`）产生
CycloneDX 风格的软件物料清单。生成过程**不访问网络**，输出可复现。

## 输出内容

- `metadata.component`：项目自身（name / version / description）；
- `components`：来自 `pyproject.toml` 的 `dependencies` 与各
  `[project.optional-dependencies]` 组声明的依赖；
- `aipd.selfModules`：`src/<pkg>/**` 下项目自身模块清单；
- `aipd.dependencies` / `aipd.optionalDependencies`：原始声明（便于审计）。

所有列表均排序，保证两次生成结果一致（确定性）。

## 如何运行

### 生成到文件

```bash
python3 -c "from aipd_os.security.sbom import generate_sbom; \
generate_sbom('.', 'dist/sbom.json')"
```

### 在 Python 中生成并校验

```python
from aipd_os.security import generate_sbom, verify_sbom

bom = generate_sbom(".")          # 项目根目录
print(verify_sbom(bom))           # True
```

### 校验现有 SBOM 文件

```python
import json
from aipd_os.security import verify_sbom

with open("dist/sbom.json") as f:
    bom = json.load(f)
assert verify_sbom(bom)
```

## 测试

`tests/test_sbom.py` 验证：
- 生成结果包含 components 与 selfModules；
- `verify_sbom` 对合法/非法结构给出正确判定；
- 两次生成结果确定性一致；
- 写入文件后读取与内存结果一致。
