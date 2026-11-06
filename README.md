# enigma2-hi3798cv200

将 [openatv/enigma2](https://github.com/openatv/enigma2)（OpenATV 8.0 GUI）移植到
HiSilicon **Hi3798CV200 / DVBIP** 的 Debian arm64 应用构建工程。HiSTB 解码适配包含
[manhere/enigma2-hi3798cv200](https://github.com/manhere/enigma2-hi3798cv200) 的工作；
本工程在官方上游源码上应用维护补丁，不以移植分支替代官方源码来源。

`enigma2-hi3798cv200` 是应用适配的维护与构建入口：OpenATV、OpenWebif 和默认皮肤的
源码获取、平台适配、资源组装及 Debian 打包规则均保存在本仓库。独立发布的三个源码
仓库是某次选定上游 HEAD 加上本仓库适配结果的固定快照，用于审查和对应源码发布，
不是持续合并新上游的分支，也不是本工作流的源码输入。后续适配只在本仓库维护。

应用包不安装或替换内核、内核模块及 HiVXE FFmpeg。构建与运行需要配套的内核 UAPI、
FFmpeg 私有 request ABI 和设备支持，不能仅凭包名或共享库 SONAME 判断兼容。
CI 使用 `ubuntu-24.04-arm` 原生 runner，分别在 Debian 12 / 13 容器中构建；两个发行版的
系统库 ABI 不同，必须选择对应的 `~deb12` / `~deb13` 成品。

## 构建与源码获取

| Workflow | 内容 | 产物 |
|---|---|---|
| `kernel-dvbip1002` | `HiSilicon-Development/linux-6.12.y`，`hi3798cv200_defconfig` 基座 + `dvbip_1002_defconfig` 片段 | `linux-image-*.deb`、`linux-headers-*.deb`、`linux-libc-dev-*.deb` |
| `enigma2-debian-arm64` | 官方 openatv/enigma2 + 维护补丁，Debian 12 / 13 原生 arm64 构建矩阵 | Enigma2、libdvbsi++、libtuxtxt 三个运行时 `.deb`，以及 `sources.lock.json` |

工作流支持手动 `workflow_dispatch`，也配置了对应工作流文件推送和每周定时触发。
应用构建入口为 `.github/workflows/enigma2.yml`，源码仓库及默认 ref 由
`packaging/fetch-source.py` 定义，打包由 `packaging/package-runtime.py` 完成。

完整源码准备入口是 `python3 .ci/apply_patches.py enigma2`，在新获取的官方 checkout 上执行。
它按序完成 Debian 兼容与原生显示适配、解码后端安装、零频率转发器保护、维护补丁和
最后的 vendor procfs 隔离；不要重复覆盖已经适配的源码树。`.ci/**` 修改同样触发应用构建。
`cleanup-runs` 是单独手动触发的工作流，仅清理已完成的历史运行并保留最新三条，不随构建执行。

### 版本选择与可复现边界

- Enigma2 默认从官方 `openatv/enigma2` 的 `master` 获取源码；OpenWebif 和
  skindefault 默认解析各自官方仓库的 `HEAD`。不以某次源码快照的 commit 作为永久默认。
  浮动输入意味着不同时间的构建可能解析到不同 commit，不意味着新上游已通过实机验收。
- `source_refs` 工作流输入接受仓库名到分支、tag 或完整 commit 的 JSON 映射。
  `enigma2`、`openwebif` 和 `skindefault` 均可单独选择；每次构建输出解析后的
  `sources.lock.json`，应与打包仓库版本及成品一起保存。复现某次发布时使用该锁文件，
  不重新选择更新的上游。该文件不锁定 APT 包或 Python wheels。
- 对应源码快照固定在该次解析出的上游基准，并完整包含当次适配；发布快照后不自动
  拉入后续上游。补丁更新及其与新上游的兼容性检查仍由本仓库负责。
- 上游上下文变化时必须刷新补丁并重新验证；流水线在源码适配或补丁应用失败时中止，
  不静默跳过不适用的补丁。不能把默认 `master` 与旧补丁曾通过等同于任意新上游均兼容。

### 依赖与构建树

- `libsigc++-3.0` 使用 Debian 的开发包 / 运行库，不重复源码安装。
- `libdvbsi++` 来自 `OpenVisionE2/libdvbsi`；`libtuxtxt` 和 `libtuxtxt32bpp`
  来自 `oe-alliance/tuxtxt`。两个运行库包只收集实际共享库，空 payload 会中止打包。
- Debian 12 成品携带私有 Python 3.13 运行时；Debian 13 复用系统 Python 3.13。
- 共享库依赖从实际 ELF 和目标发行版的 dpkg 元数据生成，不写死另一发行版的库版本；
  构建包含上游所需的 `gstreamer-video-1.0` 等依赖。
- 必须从完整适配后的源码树构建并安装资源。仅把上游 diff 叠到旧增量构建目录，可能使
  Python 模块和平台资源与二进制不一致。已有构建树的显示适配入口为
  `packaging/apply-display.py`，但它不能替代完整流水线的其余适配与补丁。

内核工作流是独立产物，不是安装应用的前提步骤。
`dvbip_1001/1002/1004/1006_defconfig` 是差异片段，不能单独使用，必须通过
`scripts/kconfig/merge_config.sh -m` 叠在 `hi3798cv200_defconfig` 基座上。
必须使用与板型一致的内核和设备树；1006 板不能直接套用 1002 镜像。
内核与刷机包的上游参考来源为
[HiSilicon-Development/firmware](https://github.com/HiSilicon-Development/firmware) releases。

## 维护中的补丁与 Web 资源

`.ci/patches/220-maintained-source-patches.py` 在后端安装之后、procfs 隔离和 configure 之前，
按序应用 `packaging/patches/*.patch`。任一源码锚点或补丁不匹配都会中止准备：

| 补丁 | 作用 |
|---|---|
| `0001-swig43-output-typemaps.patch` | 使用 SWIG 支持的输出合并接口，兼容 4.3 的 Python 指针返回绑定。 |
| `0002-histb-use-actual-framebuffer-geometry.patch` | 使用 fbdev 实际模式、stride 和图形上下文尺寸，避免错误限制 OSD 或复用仍在使用的 framebuffer 区域。 |
| `0003-persist-video-wizard-exit.patch` | 记录确认退出视频向导的完成状态。 |
| `0004-decode-raw-device-labels.patch` | 对 sysfs 中非 UTF-8 设备标签保留有效字符并替换不可解码字节，避免 UI 启动失败。 |
| `0005-histb-display-mode-geometry.patch` | 使用真实 KMS timing，保持逻辑桌面与字体比例，支持真实离屏 backing，并保留失败恢复。 |
| `0006-openatv-ui-capabilities.patch` | 全局设置保存 / 取消事务及真实后端能力门控，包括日期时间与显示设置。 |
| `0007-histb-pcm-volume.patch` | 将音量和静音应用到实际 HDMI PCM 样本，不假定存在 Master mixer。 |
| `0008-real-platform-and-all-settings.patch` | 真实平台信息、设置入口初始化和平台操作限制。 |
| `0009-histb-hdmi-hotplug-recovery.patch` | 共享显示配置刷新、严格 EDID 筛选和 HDMI 热插拔恢复。 |

`packaging/openwebif-histb.patch` 与 `packaging/apply-openwebif.py` 维护 OpenWebif
的 HiSTB 集成。桌面与手机 JS 及相关翻译资源需要与维护源码一起重建、打包，不能只替换
盒子上的网页文件。保存调用真实 `configfile.save()`，失败不伪造成功或执行应用回调；
取消保留正确的原值与后端状态。桌面和手机按请求选择模板，不共用全局 mobile 状态。
截图请求和页面资源有独立生命周期，后端错误按实际 HTTP 状态展示，而不作为图片返回。

skindefault 的适配目前属于资源组装：安装完整的 fallback XML、模板、预览、
`skin_default/` 资源树及配套字体，并保留相对 include 关系和 Debian 字体路径。
没有仅为产生差异而修改其上游 XML 或图像；对应独立源码快照可以与选定上游 HEAD
逐字一致。相关安装规则保存在工作流和 `packaging/package-runtime.py`，不是隐藏在构建目录中。

打包器还处理私有 Python 模块的无版本 SONAME、皮肤绝对字体路径及运行库收集，
并移除冒充 OE 固件镜像的分区 / 刷机元数据。`BOXTYPE` / `MACHINEBUILD` 使用上游
`u5` 兼容路径，不代表实际机器是 u5，也不提供固件刷写能力。

## 盒子端安装与配置

选择与盒子 Debian 主版本一致的三件套。在运行依赖已经齐全的盒子上：

```sh
dpkg -i ./libdvbsi++_<版本>_arm64.deb ./libtuxtxt_<版本>_arm64.deb ./enigma2-hi3798cv200_<版本>_arm64.deb
systemctl daemon-reload
systemctl start e2.service
```

缺少依赖时，使用 `apt install` 并传入三个对应版本的本地 `.deb` 路径解析依赖；
不需要用 `--reinstall` 重装已有依赖，也无需为了安装应用刷入本仓库的 1002 内核。

配置位于 `/etc/enigma2`。升级只补充缺失的默认文件，保留已有设置、频道和皮肤目录。
全新配置继承系统 `/etc/localtime` 时区，避免首次启动重置 Debian 时区。
`e2.service` 开机启用，不等待可能不存在的 DVB 调谐器；没有调谐器不等于已经具备 DVB 播放能力。

通过 `http://<盒子IP>/` 使用 OpenWebif 和虚拟遥控器。
默认未启用 Web 认证，仅应在可信局域网使用，不要直接暴露到公网。
排障可查看 `journalctl -u e2.service -b` 和内核日志。

### 平台功能与限制

- 信息页使用 DT、uname、os-release、dpkg 和 sysfs 的实际数据；缺少驱动日期时显示未知。
  boot/RPMB 区不作为用户硬盘，根文件系统及其父盘的擦除、格式化和重分区会被拒绝。
- 设置页按真实能力提供网络、时间、语言、皮肤及硬件入口。隐藏依赖项仍参与保存和取消，
  写盘或后端应用失败保留编辑值并报错。菜单可打开不等于其中每个破坏性操作都经过实机测试。
- Debian 没有相应后端时，不假装支持 OPKG、前面板、LED、HDMI 输入录制或固件刷写。
  `/var/stb` 仍承接部分传统节点；视频模式查询和设置由真实 KMS 后端处理。
- 物理遥控器需要匹配实际协议和 scancode 的 RC-core keymap；能枚举接收器不代表实体按键已验收。
- HiSTB 解码后端依赖真实 DVB demux。类型 4097 的服务仍走 GStreamer；安装
  HiVXE FFmpeg 不等于所有文件 / IPTV 路径已接入此硬解后端。
- 前端回报频率 0 时，数据库拒绝用它替换已有有效转发器；保存 lamedb v4 / v5 时也省略
  已失效的零频率记录。这不恢复此前已被错误数据覆盖的磁盘记录，也不替代射频信号排障。

## 解码、显示与音频契约

### 匹配的内核与 FFmpeg

运行时需要与构建头文件匹配的 HiVXE FFmpeg（该适配使用 avcodec 63 / avutil 61 /
swresample 7），以及支持 V4L2 request、DMA-BUF exporter vmap、PRIME import、
P010/NV15 和原生 tiled V0 的目标板内核。共享库 SONAME 相同不足以证明私有描述符 ABI 相容。
配套 FFmpeg 和内核负责 request 解码、DPB / 重建表面及其生命周期；Enigma2 负责持有
引用、等待完成和呈现，不能用应用侧拷贝或软件回退掩盖不匹配的解码栈。

`packaging/uapi/drm/histb_drm.h` 是配套内核 UAPI 的副本，由显示适配安装。
原生 Main10 使用 `DRM_FORMAT_YUV420_10BIT` / `DRM_FORMAT_MOD_HISTB_VDH_10BIT`，
不是线性 NV15 的别名。实验性 vendor `0x7e` 未获上游分配，仅适用于配套内核 / 用户态，
不应当作通用 DRM modifier。单对象、单平面、offset 0；AddFB2WithModifiers 使用 descriptor
的精确 coded 宽高，可见宽高只用于 SRC。

私有 `AVV4L2RequestFrameDescriptor` 在 `deinterlace` 后追加 `coded_width/coded_height`，
frames context 在 `frame_rate` 后追加同名字段。读取这些扩展前必须校验 request device
类型和 native modifier；其他 DRM_PRIME producer 不读取 request 专有字段或完成回调。
Main10 仅对已支持的逐行、完整 coded 几何协商 HT10，裁剪 / 其他语法沿用 NV15/P010。
正常原生播放不 detile、不经过 VPSS、不复制视频；显式下载 / 只读软件映射才生成 P010，
并先等待 request 完成。

### 呈现与缓冲所有权

- HEVC 等 stateless 解码只接受 `DRM_PRIME`，不回退 CPU 解码，不强制 Main10 转为 NV12。
  Main10 和非线性 NV12 都不能误入线性 NV12 CPU 兼容路线。
- native presentation worker 使用两个预分配 AVFrame slot 覆盖排队与正在处理的帧，另持有
  一个 scanout frame。固定 ring 满时阻塞生产者，不随播放增长，也不是 FFmpeg 全部 capture
  分配的上限；仍须测量实际 CMA / DPB 使用。硬解保留 `thread_count=1`。
- 完成等待、PTS pacing 和 KMS 提交由 consumer 执行；共享 DRM 锁仅覆盖提交，并读取当前
  模式尺寸。`HISTB_V4L2REQUEST_DEFER_CAPTURE_WAIT=auto` 保留显式环境设置，依赖匹配的完成协议。
- scanout 的 AVFrame 引用保留到阻塞替换提交完成，仅保存 GEM handle 无法防止 capture 复用。
  stop / flush 先取消队列并唤醒生产者，再在不持 queue / DRM mutex 时 join；pending request
  先等完成。禁用 plane 失败时保留仍被扫描的对象和引用并报错，不将它们交回解码器。
- 源 cadence 优先取 request codec syntax，再取生产者传递的 codec framerate；只有均未知时
  才从连续一致的短 PTS 差估计。源解码率和 HDMI 刷新率分离：低刷新输出只在呈现侧选帧，
  不丢 DPB 参考帧、不降低 coded 分辨率或位深。日志区分 completed、presented、
  refresh-selected skips 与 queue drops。
- 线性 NV12 兼容路径按 DMA-BUF 对象大小映射，共用对象只映射一次并执行 START/END READ 同步。
  PES 保留 FFmpeg 零填充；send 返回 EAGAIN 时排空并重送同一包。
- 视频入口检测继续扫描 AUD / SEI / extension 后的合法入口，不把普通依赖帧当作入口。
  配套 FFmpeg 的 H.264 开放 GOP 处理必须拒绝没有重建像素的参考场，正确收尾失败图像，
  并排空已 HOLD 的部分请求；不能伪造参考帧、放宽内核 DPB 校验或静默软件回退。

### KMS、离屏 UI 与热插拔

UI 和解码器共用 DRM master；模式应用使用真实 connector / EDID、CRTC 回读及
`TEST_ONLY` 原子检查。可选尺寸和刷新率来自驱动与当前 EDID 的交集；单个合法 timing
也是有效能力，不因列表短而扩展为驱动全集，不接受 override 绕过 HiSTB 筛选。
无有效 EDID 时不列出假模式，但保留已保存设置；不自动切到最大分辨率。

OSD 优先保留 1920×1080 ARGB backing，使用配套 CV200 内核 GP0 缩放；只有原生请求被拒绝
才尝试完整输出尺寸的 CPU OSD 兼容路线，视频不进入该复制。确认 / 取消和失败恢复以真实
KMS 状态为准。`2160p` 是统一分组，具体刷新率仍需单独满足 EDID 与驱动约束。

无 HDMI 时可使用真实 fbdev；冷启动没有 `/dev/fb0` 时分配线性 ARGB8888 DRM dumb/GEM
backing 供原 UI 绘制，不伪造 fbdev、EDID 或输出模式。离屏 fd 不持有 DRM master，
分配 / 映射失败仍报错。没有活动 KMS 输出时，WebIF 截图返回 503，而不是替代图片。

`HistbVideoHotplug` 在 E2 主循环订阅 DRM `HOTPLUG=1`，250 ms 合并事件并重新查询状态；
恢复显示时只重开直播 DVB，不重启整个 E2，也不重开文件、IPTV、录制或正在使用的时移缓冲。
真实 HPD 断开到连接可触发正常软件待机退出；仅 EDID 改变不触发。电视关机仍保持 HPD、
板级待机或 OS 关机不由此保证唤醒。这不是 CEC 替代方案，也不改变既有 CEC 配置。

### HDMI PCM

ALSA control API 枚举真实 HDMI playback endpoint，不固定 `hw:0,0`。仅在完整枚举确认
没有 HDMI PCM 时使用系统 `default`；已发现 HDMI 却打开失败时直接报错。输出保留
48 kHz stereo 协商，MP2 用 parser 重组跨 PES 的完整帧；非零 PES 长度排除 TS stuffing。
音频时钟使用“ALSA 已接受样本的 END PTS − 当前排队时长”，feed / flush / clock 共用 mutex。
flush 清除 parser / clock 状态并在 PCM drop 后 prepare。

HiSTB 软件 PCM 音量按百分比生成 Q16 增益：50% 为 0.5，0 / 静音为零，100% 保持原幅度，
不额外增益或削波。PCM RUNNING、寄存器门控正确或非零样本都不能单独证明 HDMI 实际出声、
连续无爆音或口型同步，必须使用真实接收端验收。

## 固件来源与可选 OSCam

`packaging/firmware/hisilicon/` 包含 `histb-avsp.bin`、`histb-h264-cabac.bin` 和
`histb-hevc-cabac.bin` 三个生成文件，打包副本与配套内核生成的规范字节保持一致。
这些文件的来源说明保留在同目录已有的 `README.avsp` / `README.cabac` 中。
字节一致性只说明来源对应，不构成新的许可或再分发授权；不能由“生成文件”或本工程公开
推导对所有上游材料的发布权。发布者仍须核对各来源的版权、许可和再分发条件。
其他设备固件、内核驱动及 HiVXE FFmpeg 由外部运行环境提供和管理，应用包不替代其维护责任。

OSCam 是可选的独立运行服务，不是验证未加扰 DVB 播放的前提。Softcam 设置对接真实
`oscam.service`，异步 start / restart 后检查 is-active，再保存 / 关闭；不创建假 init 脚本，
`HAVEINITCAM` 仍只表示真实 init 脚本存在。OpenWebif 中的 OSCam 入口使用独立登录，
不共享 OpenWebif 认证，也不嵌入凭据或改写 ACL。

条件接收还依赖匹配的 SCI、CA 和 DVBAPI 驱动及独立配置。CV200 的 CSA2 密钥事务需要
完整四字寄存器事务，标准八字节 CW 必须原样处理，不能以补零或越界读取替代。
设备较晚出现时的 OSCam DVBAPI 等待属于其独立适配，不由 E2 包替代。
仅在具备合法授权的条件下使用；保留 reader 和授权配置，不发布卡片身份、CW 或密钥 trace。
现有运行时调试日志的敏感性仍须单独评估，本说明不表示日志已经脱敏或可以公开。

## 实机证据边界与验收清单

已有 DVBIP-1001 记录覆盖 UI、OpenWebif、时区初始化和升级保留配置；当时未暴露 DVB 设备，
不能据此证明该板搜台、调谐、直播或录制已通过。DVBIP-1006 的配套栈已有真实 RF DVB、
H.264、HEVC Main10 原生 tiled 输出和离屏 UI 观察；部分组合有 P010 下载 / 只读映射与
独立软件参考逐帧一致、持续 50 fps 解码以及低刷新 HDMI 呈现的记录。
这些是特定板型和软硬件组合的历史结果，不是当前浮动上游、全部板型、全部频道或全部 HDMI
模式的通用保证；文件硬解吞吐、WebIF 截图和配置模型检查不能替代物理 HDMI 验收。

每次更换上游、补丁、内核、FFmpeg 或接收端后，按所需范围重新执行：

1. 安装匹配 Debian 主版本的三件套并检查 `/etc/enigma2` 保留情况。确认实际内核、FFmpeg
   ABI、板型、DVB adapter、HDMI connector、EDID 和 ALSA endpoint，不混用其他板型镜像。
2. 在 EDID 支持的 1080p 模式下搜台、调谐已知 RF 频道，验证 OSD、H.264 / HEVC、实际
   HDMI 音频、重复换台、停止 / 启动及 flush。保留服务与内核日志，检查 request / presentation
   失败、join 卡死、解码错误、CMA 持续增长和过早复用。
3. 分别验证 3840×2160 Main / Main10 硬解与 E2 DVB/tap→V0 的真实播放。确认 DRM_PRIME
   descriptor、coded 几何、原生 modifier 和位深；不使用
   `HISTB_V4L2REQUEST_MAIN10_NV12`、`HISTB_V4L2REQUEST_MAX_CAPTURE_SIZE` 或
   `HISTB_V4L2REQUEST_CAPTURE_SIZE` 绕过问题。记录内容校验、CPU、CMA / DPB 和帧统计。
   4K 解码缩放到 1080p 与真正 2160p HDMI 输出是两项独立验收。
4. 只测试接收端 / 采集器实际支持的刷新率与色彩条件，核对 CRTC timing、全屏 OSD 和视频层；
   播放中与未播放时分别确认 / 取消。不支持的模式必须保持原画面。最大 EDID timing 不代表
   每种色深和色彩格式都可用，不能把超出采集器能力的失锁归为解码失败。
5. 验证 H.264↔HEVC / 线性↔tiled 换台、开放 GOP、源帧率高于输出刷新率和长期音画同步；
   区分正常 refresh-selected skips 与 queue drops，分别检查 MP2、AC3、音量、静音及空闲音频。
6. 分别验证无 HDMI 冷启动、无 fbdev 的真实离屏绘制、物理断开 / 重连、重新呈现和软件待机
   唤醒。受控状态转换与离屏截图不能替代物理拔插、真实节目和实际声音；这些仍是独立验收项。
7. 桌面和手机检查实际设置保存、取消、写盘失败与截图错误；网络迁移、改密码、格式化外盘、
   覆盖扫描、替换语言 / 皮肤等操作必须另行评估，不将入口检查视作破坏性动作已测试。
8. 如使用 OSCam，独立验证冷启动设备就绪、授权建立、普通 / 加密频道往返与实际解扰，
   不收集或公开 CW、密钥及卡片身份数据。CI 成功和本地安装成功均不等于这项硬件验收完成。

目前不能宣称所有硬件路径均已通过，尤其不能以历史画面关闭新组合的物理 HDMI、连续音频、
热插拔 / 待机唤醒、全部频道稳定性、实体遥控器和破坏性设置操作验收项。
