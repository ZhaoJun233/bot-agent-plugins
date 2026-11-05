# M0/M1 基线与首批清单

日期：2026-11-05。此文件记录实施基线，不是已部署或安全审核的证明。当前变更尚未发布；线上旧目录没有展示文件时，新宿主仍会使用兼容回退。

## 冻结基线

| 对象 | Commit / 身份 |
| --- | --- |
| 私有宿主工作树起点 | `b80d7b271bae58bf7f0b8f4261b03f6c4ffe0199` |
| 公开宿主 dev（开工时） | `dd181696afadc7a298eebda736e788f529f60b76` |
| 市场 main 起点 | `629842c1b0187523354b7877eddffc0788c56a28` |
| 既有 Release tag | `community.example.hello-1.0.0` |

宿主按 net10.0 构建、当前包契约接受 net8.0 / net10.0；首个 Hello 发布包保持 net8.0、ApiVersion 1、MinimumHostVersion 1.0.0。SDK 固定为 10.0.101。不要把编译 SDK、宿主目标框架、插件目标框架混为一谈。

既有 [CI 工作流](../.github/workflows/validate.yml) 的 SDK 契约兼容检查继续固定在旧公开宿主 `c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7`（net8.0），本次没有改写该旧基线。新宿主侧验证包括 M1 展示解析、实际 Wire 和注册表，但没有把下载的 Hello 包安装或运行在新宿主；因此不宣称已完成新旧宿主的完整插件执行兼容矩阵。

## 真实首批范围

全部版本为 1.0.0。下列内置身份来自宿主预设注册源；安装数量由运行中的注册表决定，而不是照抄静态目录。

| ID | 展示用途 | 来源 / 分发 |
| --- | --- | --- |
| `preset.feature.music` | 点歌 | 宿主内置，无独立包 |
| `preset.feature.voice` | 云端语音 | 宿主内置，无独立包 |
| `preset.feature.stickers` | 表情包 | 宿主内置，无独立包 |
| `preset.feature.poke` | 戳一戳 | 宿主内置，无独立包 |
| `preset.feature.vibes` | 氛围发言 | 宿主内置，无独立包 |
| `preset.feature.profiles` | 成员档案 | 宿主内置，无独立包 |
| `preset.feature.websearch` | 联网搜索 | 宿主内置，无独立包 |
| `preset.feature.token-quota` | Token 用量配额 | 宿主内置，无独立包 |
| `community.example.hello` | 无副作用生命周期示例 | 社区 .NET 示例包，未审核 |

Hello 的 [技术目录](../index.json)、[固定版本清单](../plugins/community.example.hello/1.0.0/manifest.json) 与 [示例源码](../examples/HelloPlugin/HelloPlugin.cs) 不因 M1 修改。它没有命令、后台任务、设置、消息回复或宿主服务调用。

已通过公开 Release 下载独立复核 ZIP：4736 字节，仅包含 HelloPlugin.dll，SHA256 为 `01dccbf848c9c9fbd5797e47a86339b79a4963eb585fc8157ff74768145c50cb`。没有执行该下载产物，也没有完成安全审核。

## 可复跑验证

~~~sh
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
python tools/package.py
python tools/validate.py --archive artifacts/release/community.example.hello-1.0.0.zip
python tools/validate_presentation.py
python -m unittest discover -s tools -p "test_*.py"
~~~

打包命令不得附带 `--write-catalog`：测试应比较既有不可变哈希，而不是重写固定版本。M1 增加 28 项展示边界测试，连同原 10 项技术契约测试共 38 项。M0/M1 不涉及真实聊天数据，也不包含部署、发布、启用外部插件或修改回复节奏策略。
