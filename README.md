# enigma2-hi3798cv200

将 [openatv/enigma2](https://github.com/openatv/enigma2)（OpenATV 8.0 GUI）移植到
HiSilicon **Hi3798CV200 / DVBIP** 的 Debian arm64 应用构建工程。

Enigma2 应用包不包含内核、hivxe-ffmpeg 或内核解码固件；已有的这些组件不应被应用安装覆盖。
CI 使用 `ubuntu-24.04-arm` 原生 runner，分别在 Debian 12 / 13 容器中构建；两个发行版的
系统库 ABI 不同，必须选用对应的 `~deb12` / `~deb13` 成品。

## 工作流

| Workflow | 内容 | 产物 |
|---|---|---|
| `kernel-dvbip1002` | `HiSilicon-Development/linux-6.12.y`，`hi3798cv200_defconfig` 基座 + `dvbip_1002_defconfig` 片段（merge_config.sh 合并） | `linux-image-*.deb`、`linux-headers-*.deb`、`linux-libc-dev-*.deb` |
| `enigma2-debian-arm64` | openatv/enigma2 + Debian 12 / 13 原生构建矩阵 | Enigma2、libdvbsi++、libtuxtxt 三个运行时 `.deb`，以及 `sources.lock.json` |

> 注意：`dvbip_1001/1002/1004/1006_defconfig` 均为 1-2 行的差异片段，不能单独使用，
> 必须叠在 `hi3798cv200_defconfig` 基座上（`scripts/kconfig/merge_config.sh -m`）。

上游参考固件（HiSilicon-Development/firmware releases）：
- `linux-headers-6.12.112-dvbip-1002_6.12.112-1_arm64.deb`（header 包命名与版本对齐参考）
- `update-1002.tar.gz`（刷机包）

触发方式：手动 `workflow_dispatch`、推送对应 workflow 文件、每周定时跟踪上游。

## 应用依赖与源码版本

- `libsigc++-3.0` 使用 Debian 的开发包 / 运行库，不重复源码安装。
- `libdvbsi++` 来自 OpenVisionE2/libdvbsi；`libtuxtxt` 和 `libtuxtxt32bpp` 来自 oe-alliance/tuxtxt。
  两个运行库包只收集真正的共享库，空 payload 直接中止打包。
- Debian 12 自带私有 Python 3.13 运行时；Debian 13 复用系统 Python 3.13。
- 共享库依赖从实际 ELF 和目标发行版的 dpkg 元数据生成，不写死 Debian 12 的 `libswscale6`。
- `source_refs` 工作流输入接受仓库名到分支、tag 或完整 commit 的 JSON 映射。
  每次构建记录解析后的 `sources.lock.json`；将其作为下次输入可固定源码版本。
  它不锁定 APT 包或 Python wheels。

## 盒子端安装

选择与盒子 Debian 主版本一致的三件套。在依赖已经齐全的盒子上：

```sh
dpkg -i ./libdvbsi++_<版本>_arm64.deb ./libtuxtxt_<版本>_arm64.deb ./enigma2-hi3798cv200_<版本>_arm64.deb
systemctl daemon-reload
systemctl start e2.service
```

缺少运行库时，用 `apt install ./三个对应版本的deb文件` 解析并补齐缺失项；不要使用
`--reinstall` 重装现有依赖。安装应用无需刷入本仓库的 1002 内核。

配置保存在 `/etc/enigma2`；升级只补缺失的默认文件，保留已有设置、频道和皮肤目录。
全新配置会继承系统 `/etc/localtime` 的时区，避免首次启动把 Debian 时区重置为柏林。
服务开机启用，不再等待一个可能根本不存在的 DVB 调谐器。

浏览器打开 `http://<盒子IP>/` 使用 OpenWebif 和虚拟遥控器。
默认未启用 Web 认证，仅应在可信局域网使用；不要直接暴露到公网。

## 维护中的源码补丁

`packaging/patches/*.patch` 在工作流已有的 Debian / HiSTB 适配之后、configure 之前按序应用：

- `0001-swig43-output-typemaps.patch`：使用 SWIG 支持的输出合并接口，兼容 4.3 的 Python 指针返回绑定。
- `0002-histb-use-actual-framebuffer-geometry.patch`：使用 fbdev 实际模式、stride 和图形上下文尺寸，
  防止被拒绝的 720p 请求把 1080p OSD 限制在左上角，或把仍在使用的 framebuffer 区域误作空闲内存。
- `0003-persist-video-wizard-exit.patch`：确认退出视频向导后记录完成状态，避免每次启动重复进入。
- `0004-decode-raw-device-labels.patch`：sysfs 的 eMMC/磁盘标识可能包含非 UTF-8 原始字节；
  设备描述读取保留有效字符并替换不可解码字节，不让硬件标签导致整个 UI 启动失败。
- `0005-histb-display-mode-geometry.patch`：以实际 KMS timing 应用视频模式，保持皮肤的
  逻辑桌面和字体比例；确认、取消和失败恢复不以模拟节点内容判断成功。
- `0006-openatv-ui-capabilities.patch`：全局设置跟踪暂时隐藏的依赖项，保存失败保留编辑值与
  原取消目标；网络、时间、语言、皮肤和硬件能力使用真实后端并传播失败。
- `0007-histb-pcm-volume.patch`：把音量和静音应用到 HDMI PCM 样本，不假定存在 Master mixer。

打包器同时修正空运行库包、私有 Python 模块的无版本 SONAME、皮肤的绝对字体路径，
并移除冒充 OE 固件镜像的分区 / 刷机元数据。`BOXTYPE` / `MACHINEBUILD` 仍使用上游 `u5` 兼容路径，
不代表目标机器是 u5，也不提供固件刷写能力。

## 实机验证与未验证边界

2026-10-31：DVBIP-1001，Debian 13.7 arm64，已有 `6.12.114-dvbip-1001` 内核及
`n9.0.1-33-g6c2ae2fd24-hivxe`。本地交叉编译后安装实机，已观察中文 UI、1080p framebuffer、
OpenWebif 与网页遥控，并实际检查首次时区初始化和升级保留配置。未声称本次运行过完整 GitHub CI。

- 该次 1001 实机未暴露 `/dev/dvb`，因此当时没有验收调谐器、搜台、DVB 直播和录制。
- 移植解码后端依赖真实 DVB demux；安装了 hivxe-ffmpeg 不等于所有文件 / IPTV 路径已接上硬解。
  类型 4097 的播放服务仍走 GStreamer，不能据此宣称已验证 HiSTB 解码器。
- 遥控接收器可被枚举；实体遥控器还需要匹配实际协议和 scancode 的 RC-core keymap，本次未验收实体按键。
- OpenWebif 页面截图未通过本次验收。图像证据取自 `/dev/fb0`，不代表已实现视频层截取。
- `/var/stb` 仍承接音量、颜色等未实现的传统 STB 节点；视频模式查询和设置现由上述
  KMS 后端接管。菜单出现选项仍不等于其他硬件控制已经实现；当前 1006 的通过项与
  仍待恢复采集卡后完成的验收，以上面的实测记录为准。
