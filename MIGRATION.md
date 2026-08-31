# stock-pattern-matcher-gpu 移植步骤

本文说明如何把 `stock-pattern-matcher-gpu` 移植到另一台 Windows 电脑，并在新的 `ai_env` 环境中运行。

## 1. 需要迁移的内容

建议迁移源代码和配置说明，不直接迁移 Python 虚拟环境：

```text
stock-pattern-matcher-gpu/
├── gpu_matcher.py
├── main.py
├── report.py
├── README.md
├── PRINCIPLES.md
├── MIGRATION.md
├── requirements.txt
├── .gitignore
└── data/
    └── README.md
```

以下内容通常不需要迁移：

```text
__pycache__/
reports/
```

`data/kline/` 目前约 641 MB。如果目标电脑磁盘和传输条件允许，可以整体复制；也可以在目标电脑按数据源条款重新获取。行情数据不应提交到 GitHub。

## 2. 复制项目目录

可以使用 U 盘、局域网或压缩包复制整个项目目录。例如源目录为：

```text
F:\project\stock-pattern-matcher-gpu
```

目标目录可以是：

```text
D:\project\stock-pattern-matcher-gpu
```

项目不要求必须使用 `F:` 盘。运行时如果数据目录不在默认位置，使用 `--data-dir` 指定实际路径。

## 3. 安装 Python 和 Conda

目标电脑安装 Miniconda 或 Anaconda，并确认 PowerShell 可以使用 `conda`：

```powershell
conda --version
```

建议 Python 使用 3.10 或 3.11，避免过新的 Python 版本与部分科学计算包不兼容。

## 4. 创建 ai_env 环境

```powershell
conda create -n ai_env python=3.11 -y
conda activate ai_env
python --version
```

确认解释器属于新环境：

```powershell
python -c "import sys; print(sys.executable)"
```

## 5. 检查 NVIDIA GPU

如果目标电脑有 NVIDIA GPU，安装对应的 NVIDIA 驱动后执行：

```powershell
nvidia-smi
```

确认能看到 GPU 型号和驱动版本。驱动版本应满足所安装 PyTorch CUDA wheel 的要求。

本项目当前机器已验证：

```text
GPU：NVIDIA Quadro T1000
PyTorch：2.7.1+cu118
CUDA runtime：11.8
```

目标电脑不一定要完全相同，但必须安装兼容的 NVIDIA 驱动和 PyTorch 版本。

## 6. 安装依赖

进入项目目录：

```powershell
cd D:\project\stock-pattern-matcher-gpu
```

安装项目依赖：

```powershell
pip install -r requirements.txt
```

如果 `requirements.txt` 中的 CUDA wheel 不适合目标机器，应先根据 PyTorch 官方安装命令安装对应版本，再安装其余依赖。

验证 PyTorch 和 CUDA：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

预期结果应包含：

```text
True
目标 NVIDIA GPU 名称
```

如果输出为 `False`，程序仍可以运行，但会回退到 CPU，不能获得 GPU 加速。

## 7. 准备数据

### 方式 A：复制已有数据

将源电脑的：

```text
F:\project\stock-pattern-matcher-gpu\data\kline\
```

复制到目标电脑项目的：

```text
D:\project\stock-pattern-matcher-gpu\data\kline\
```

检查文件数量：

```powershell
(Get-ChildItem .\data\kline -File -Filter *.json).Count
```

每个 JSON 文件应以六位股票代码命名，例如：

```text
data\kline\600879.json
```

### 方式 B：使用其他合规数据

数据文件需要包含以下字段：

```text
date, open, high, low, close, volume
```

也可以使用：

```json
{
  "code": "600879",
  "name": "航天电子",
  "kline": [
    {
      "date": "20260506",
      "open": 10.0,
      "high": 10.5,
      "low": 9.8,
      "close": 10.3,
      "volume": 1000000
    }
  ]
}
```

## 8. 运行测试

先确认测试股票文件存在：

```powershell
Test-Path .\data\kline\600879.json
```

运行 GPU 相似形态匹配：

```powershell
python .\main.py 600879 `
  --start-date 20260501 `
  --end-date 20260530 `
  --top 10 `
  --batch-size 2048
```

程序会：

1. 加载项目自身 `data\kline` 中的股票数据；
2. 提取目标日期范围内的实际交易日；
3. 排除目标股票与目标时间段重叠的候选窗口；
4. 使用 CUDA 批量计算相似距离；
5. 输出 Top10 历史相似窗口；
6. 在项目自身 `reports\代码_起始日期_结束日期\report.html` 生成报告。

## 9. 显存不足时的处理

Quadro T1000 等 4GB 显存显卡建议从较小批次开始：

```powershell
python .\main.py 600879 --start-date 20260501 --end-date 20260530 --top 10 --batch-size 512
```

可尝试的批大小：

```text
512 -> 1024 -> 2048 -> 4096
```

如果出现 CUDA out of memory，降低 `--batch-size`。批大小只影响计算批次和显存占用，不改变匹配原理。

## 10. 报告位置

报告默认生成在每次运行独立的子目录中：

```text
D:\project\stock-pattern-matcher-gpu\reports\600879_20260506_20260529\report.html
```

也可以显式指定：

```powershell
python .\main.py 600879 --start-date 20260501 --end-date 20260530 --report .\reports
```

用浏览器打开对应子目录下的 `report.html`，可查看目标窗口和 Top-N 相似窗口的 SVG K 线图。

## 11. 常见问题

### 找不到股票代码

确认对应 JSON 位于项目自身目录：

```text
项目目录\data\kline\股票代码.json
```

### CUDA 不可用

依次检查：

```powershell
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

如果驱动正常但 PyTorch 返回 `False`，通常是 PyTorch wheel 与环境或驱动不匹配，需要重新安装兼容版本。

### 报告写入了错误目录

不要在其他项目目录运行旧脚本。进入 GPU 项目后执行：

```powershell
cd D:\project\stock-pattern-matcher-gpu
python .\main.py ...
```

也可以使用绝对路径指定：

```powershell
python .\main.py 600879 --start-date 20260501 --end-date 20260530 --report D:\project\stock-pattern-matcher-gpu\reports
```

### 运行速度仍然较慢

GPU 只加速批量距离计算，JSON 读取、日期解析和特征构造仍由 CPU 完成。可检查：

```powershell
nvidia-smi
```

运行期间观察 GPU 利用率和显存占用。不要同时启动多个全量匹配任务，否则会争用 CPU、磁盘和 GPU。

## 12. GitHub 项目移植方式

如果代码已上传 GitHub，目标电脑可以这样获取：

```powershell
git clone <你的仓库地址>
cd stock-pattern-matcher-gpu
conda activate ai_env
pip install -r requirements.txt
```

然后把本地行情数据复制到：

```text
data\kline\
```

由于 `.gitignore` 会忽略行情 JSON 和报告，克隆仓库后需要单独准备数据。

## 13. 移植完成检查清单

- [ ] 项目位于目标电脑的新目录
- [ ] `ai_env` 已激活
- [ ] `python` 指向 `ai_env`
- [ ] `nvidia-smi` 可以识别 GPU
- [ ] `torch.cuda.is_available()` 返回 `True`，或已确认使用 CPU
- [ ] `data\kline` 中存在行情 JSON
- [ ] 目标股票 JSON 存在
- [ ] 匹配命令运行成功
- [ ] `reports\代码_起始日期_结束日期\report.html` 已生成
- [ ] 未把 API Key、完整行情数据和报告提交到 GitHub
