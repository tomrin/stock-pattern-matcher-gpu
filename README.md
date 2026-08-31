# stock-pattern-matcher-gpu

保留原项目 `stock-pattern-matcher` 不变，GPU 版本直接复用其现有数据：

```text
F:\project\stock-pattern-matcher\data\kline
```

不会重新下载数据，也不会修改原项目。

## 运行

```powershell
conda activate ai_env
cd F:\project\stock-pattern-matcher-gpu
python .\main.py 600703 --start-date 20260501 --end-date 20260530 --top 10
```

报告默认输出到项目自己的 `reports\代码_起始日期_结束日期\` 子目录（例如 `reports\600703_20260720_20260820\report.html`），每次运行独立归档，不会互相覆盖。默认数据读取项目自己的 `data\kline`。也就是说，本项目不依赖 `F:\project\stock-pattern-matcher` 的目录或文件。

日期可以使用 `YYYYMMDD` 或 `YYYY-MM-DD` 格式。起止日期定义目标形态的自然日范围，范围内只使用实际交易日。

可调 GPU 批大小：

```powershell
python .\main.py 600703 --start-date 20260501 --end-date 20260530 --top 10 --batch-size 2048
```

可调 K 线图展示长度（默认 30 个自然日）：

```powershell
python .\main.py 600703 --start-date 20260501 --end-date 20260530 --top 10 --chart-days 45
```

## GPU 加速原理

CPU 读取 JSON、按自然日截取窗口并把每个窗口转换为相对特征序列；GPU 对批量特征向量执行距离计算：

```text
收益率、振幅、实体比例、相对成交量
        -> 窗口内 Z-score 标准化
        -> 拼成特征向量
        -> CUDA 批量计算欧氏距离
        -> 保留 Top-N 最相似窗口
```

GPU 主要加速距离计算，磁盘读取和 JSON 解析仍由 CPU 完成。Quadro T1000 只有 4GB 显存，因此程序使用批处理，不会一次把全部历史窗口放入显存。若显存不足，降低 `--batch-size`。

## 发布前说明

- `data\kline\` 中的行情 JSON 和 `reports\` 中的生成报告默认不提交到 Git。
- 项目不保存 Tushare Token 或其他 API Key；需要更新数据时，应使用环境变量或本地未跟踪配置。
- `requirements.txt` 中的 PyTorch CUDA 依赖适合本机已验证的 CUDA 11.8 wheel；其他机器可按本机驱动调整 PyTorch 版本。
- 如果没有可用 CUDA，程序会回退到 CPU，但不会获得 GPU 加速。
- 相似度只表示历史形态距离，不代表未来走势或投资建议。
