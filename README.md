# Timbre Distillation

**音色蒸馏** — 从多源音频数据中提取、精炼并训练特定人声音色模型的完整方法论。

## 概述

本项目不是模型仓库，而是一套**训练方法**。通过三轨数据源组合策略，将来自公开歌唱数据集、视频平台翻唱素材和社区预训练模型的音频，经过系统化的清洗、分离、分段流程，最终训练出高质量 RVC 音色模型。

### 核心理念

```
原始多源音频 → UVR5 人声分离 → Audition 清洗 → 智能分段 → RVC v2 训练 → 目标音色模型
```

不做「收集-丢进去训练」的粗放模式，而是每一段训练数据都经过人工质检。

## 三轨数据源策略

| 轨道 | 来源 | 占比 | 作用 |
|------|------|:----:|------|
| **A** | HuggingFace/B站 社区RVC模型 | 底模 | 音色方向初始化 |
| **B** | Opencpop / M4Singer / Kising 公开数据集 | ~30% | 纯净干声基线，保证音准和基础音质 |
| **C** | B站翻唱区UP主素材 | ~70% | 音色个性来源：咬字、气息、情感表达 |

### 为什么不是抖音？

抖音/字节跳动的反爬体系包含 X-Bogus/X-Khronos 等协议层加密签名，Scrapling 的 StealthyFetcher 针对的是 Cloudflare Turnstile 而非字节自研反爬。B站有开放 API + wbi 签名，yt-dlp 社区维护成熟，是同类素材更高效的获取渠道。

## 采集流水线

```
B站 API(wbi) → yt-dlp 批量下载纯音频 → UVR5 MDX-Net 人声分离 → Audition 清洗质检 → librosa 静音分段 3-15s → RVC v2 48K 训练
```

| 阶段 | 工具 | 产出 |
|:----:|------|------|
| 发现 | Python + B站 API + wbi 签名 | UP主翻唱列表 |
| 下载 | yt-dlp `-f ba --concurrent-fragments 8` | 原始音频 AAC/Opus |
| 分离 | UVR5 MDX-Net | 干声 WAV 48K mono |
| 清洗 | Adobe Audition | 去空白/噪音/念白 |
| 分段 | Python + librosa | 3-15s 训练就绪片段 |
| 训练 | RVC v2 (48K) | 目标音色模型 |

## 音色数据质量标准

- **格式**：WAV, 48KHz, mono
- **片段长度**：3-15 秒（过短无上下文，过长训练不稳定）
- **内容**：纯干声演唱，无伴奏残留、无念白、无环境噪音
- **信噪比**：UVR5 MDX-Net 分离后人工抽检，残留伴奏 > -30dB 的片段丢弃
- **音域覆盖**：确保高中低音区均有足够样本

## 项目结构

```
Timbre_distillation/
├── README.md                     # 本文件
├── VP音色数据源方案.md            # 项目计划书
├── .gitignore                    # 排除数据和模型文件
├── tools/                        # 采集和处理脚本
│   ├── discover_up主.py          # B站API UP主发现
│   ├── batch_download.py         # yt-dlp批量下载
│   ├── segment_audio.py          # 静音检测分段
│   └── requirements.txt
├── w/                            # 数据下载目录 (gitignored)
│   ├── A_community_rvc/          # 社区RVC模型
│   ├── B_open_datasets/          # 公开歌唱数据集
│   └── C_bilibili/               # B站翻唱素材
├── models/                       # 训练输出模型 (gitignored)
│   └── rvc/
└── output/                       # 翻唱成品 (gitignored)
```

## 依赖

```bash
pip install -r tools/requirements.txt
# 额外需要手动安装:
# - UVR5 (Ultimate Vocal Remover GUI)
# - RVC WebUI (B站搜 秋葉aaaki 整合包)
# - Adobe Audition (或 Audacity 免费替代)
```

## 参考声线

VP (Virtual Person) 目标音色：成年女声，可御可甜，清亮通透有厚度

参考：咻咻满、真栗、傲寒同学、忘归人

## License

BSD 3-Clause — 方法论开源，数据不在此仓库内。

## 致谢

- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 检索式声音转换引擎
- [UVR5](https://github.com/Anjok07/ultimatevocalremovergui) — 人声分离
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 音视频下载
- [Scrapling](https://github.com/D4Vinci/Scrapling) — Python 爬虫框架（本项目备选工具）
