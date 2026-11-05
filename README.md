# enigma2-hi3798cv200

将 [openatv/enigma2](https://github.com/openatv/enigma2)（OpenATV 8.0）移植到
HiSilicon **Hi3798CV200**（DVBIP-1002 板）+ **Debian 12 (bookworm) arm64**。

所有编译均在 GitHub Actions 公开仓库的 **ubuntu-24.04-arm 原生 arm64 runner** 上完成，
本地不需要交叉工具链。

## 工作流

| Workflow | 内容 | 产物 |
|---|---|---|
| `kernel-dvbip1002` | `HiSilicon-Development/linux-6.12.y`，`hi3798cv200_defconfig` 基座 + `dvbip_1002_defconfig` 片段（merge_config.sh 合并） | `linux-image-*.deb`、`linux-headers-*.deb`、`linux-libc-dev-*.deb` |
| `enigma2-debian12-arm64` | openatv/enigma2 master + Debian 12 原生构建 | `enigma2-hi3798cv200_*.deb`、`libdvbsi++_*.deb`、`libtuxtxt_*.deb` |

触发方式：手动 `workflow_dispatch`、推送对应 workflow 文件、每周定时跟踪上游。

> 注意：`dvbip_1001/1002/1004/1006_defconfig` 均为 1-2 行的差异片段，不能单独使用，
> 必须叠在 `hi3798cv200_defconfig` 基座上（`scripts/kconfig/merge_config.sh -m`）。

## Debian 12 源里没有的依赖（workflow 内源码补编）

| 依赖 | 来源 | 说明 |
|---|---|---|
| `sigc++-3.0` | libsigcplusplus 3.2.0 | bookworm 只有 sigc++-2.0 |
| `libdvbsi++` | OpenVisionE2/libdvbsi | autotools，随 enigma2 一并产出 .deb |
| `tuxtxt` | oe-alliance/tuxtxt | openATV enigma2 需要 `tuxtxt_enabledebug` 符号，仅 OE-A fork 有 |

## 视频管线

`packaging/decoder_histb_impl.h` 编译进 e2 的 `decoder.cpp`（`HAVE_HISTB`），
内嵌实现完整解码链，无独立 video service：

```
DVB 前端 → histb-dmx (DMX_OUT_TSDEMUX_TAP)
  → 用户态 TS/PES 解包 (HistbPesDemux)
  → avcodec 硬解（hivxe-ffmpeg v4l2request hwaccel：MPEG1/2、H.264、HEVC、AVS/+）
      兜底: MPEG-4/VC-1 走 v4l2m2m，再兜底软解
  → DRM PRIME NV12 → AddFB2 → drmModeSetPlane(V0) 零拷贝
     （VDP 缩放 + Y2R 由显示硬件完成；PTS 槽位节拍呈现）
  → 兜底: NV12 dumb 池 + presentThread flip
```

- 音频走 avcodec 软解（MP2/AC3/DTS/AAC/EAC3/LPCM/DRA）→ swresample → ALSA。
- OSD 为 ARGB dumb surface，primary + G0 双平面，GLES（Mesa llvmpipe EGL）blit 加速。
- 显示模式按内容分辨率/隔行由 `histbDrmApplyMode` 切换。

## 盒子端安装

```sh
dpkg -i linux-image-*.deb            # 内核（重启进入 6.12-dvbip-1002）
apt update
dpkg -i libdvbsi++_*.deb libtuxtxt_*.deb
apt install -y -f                    # 自动补 enigma2 的 Depends（含 libegl1/libgles2/libgbm1）
dpkg -i enigma2-hi3798cv200_*.deb
```

上游参考固件（HiSilicon-Development/firmware releases）提供
`linux-headers-*-dvbip-1002_*.deb`（header 包命名与版本对齐参考）与 `update-1002.tar.gz`（刷机包）。

## 当前状态

- [x] 内核编译并产出 .deb（6.12.y + dvbip-1002）
- [x] enigma2 configure/build 通过并产出 .deb（同批产出 libdvbsi++ / libtuxtxt）
- [x] 盒端运行：e2 服务化、DVB 前端换台、视频硬解零拷贝、OSD 双平面、音频输出、遥控
- [ ] boxtype 私有化（`BOXTYPE`/`MACHINEBUILD` 目前默认 `u5`，HiSilicon 通用路径）
- [ ] VPSS DEI 盒内去隔行 + 显示模式锁定（换台 modeset 黑屏优化）

## 已知限制

- AVS2：CV200 VDH 无 AVS2 引擎，硬解不可用。
- 4K HEVC：上游 histb-vdec 存在 HEVC 循环完成判定缺陷（`<=` 写成 `==`），
  播 4K HEVC 需在盒上以模块级补丁解决（不随本仓库内核 .deb 分发）。
- vendor demux tap 为突发投递，TS 断流阵发无法在呈现端弥补。
