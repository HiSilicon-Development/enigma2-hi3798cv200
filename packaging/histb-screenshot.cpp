// SPDX-License-Identifier: GPL-3.0-or-later
// Read-only HiSTB KMS screenshot. Never takes DRM master or changes a plane.
// HT10 row permutations match libavutil/hwcontext_v4l2request.c and the
// CV200 kernel detiler, not MV310 tiles. See uapi/drm/histb_drm.h.
#include <algorithm>
#include <array>
#include <chrono>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <fcntl.h>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <poll.h>
#include <linux/dma-buf.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <jpeglib.h>
#include <png.h>
#include "uapi/drm/histb_drm.h"

static void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

struct Fd {
    int value = -1;
    ~Fd() { if (value >= 0) close(value); }
    Fd() = default;
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
};

struct Mapping {
    Fd fd;
    uint8_t *data = nullptr;
    size_t size = 0;
    bool synced = false;
    void openBuffer(int descriptor)
    {
        fd.value = descriptor;
        off_t length = lseek(fd.value, 0, SEEK_END);
        require(length > 0 && length <= 128 * 1024 * 1024, "Invalid DMA buffer length");
        size = length;
        void *address = mmap(nullptr, size, PROT_READ, MAP_SHARED, fd.value, 0);
        require(address != MAP_FAILED, "Could not map display DMA buffer");
        data = static_cast<uint8_t *>(address);
        dma_buf_sync sync = {};
        sync.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ;
        require(ioctl(fd.value, DMA_BUF_IOCTL_SYNC, &sync) == 0, "DMA buffer read synchronization failed");
        synced = true;
    }
    void endRead()
    {
        if (!synced) return;
        dma_buf_sync sync = {};
        sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
        require(ioctl(fd.value, DMA_BUF_IOCTL_SYNC, &sync) == 0, "DMA buffer read completion failed");
        synced = false;
    }
    ~Mapping()
    {
        if (synced) {
            dma_buf_sync sync = {};
            sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
            ioctl(fd.value, DMA_BUF_IOCTL_SYNC, &sync);
        }
        if (data) munmap(data, size);
    }
    uint8_t byte(size_t index) const
    {
        require(index < size, "Display sample lies outside the DMA buffer");
        return data[index];
    }
    unsigned word(size_t index) const { return byte(index) | unsigned(byte(index + 1)) << 8; }
};

struct Lease {
    Fd socket;
    Mapping buffer;
    unsigned width = 0, height = 0, format = 0, pitch[2] = {}, offset[2] = {};
    unsigned codedWidth = 0, codedHeight = 0, colorspace = 0, range = 0, planes = 0;
    unsigned long long modifier = 0;
    std::chrono::steady_clock::time_point acquired;
    bool active = false;
    void acquire()
    {
        socket.value = ::socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        require(socket.value >= 0, "Could not open decoder capture socket");
        sockaddr_un address = {};
        address.sun_family = AF_UNIX;
        strcpy(address.sun_path, "/run/enigma2/histb-video-capture.sock");
        require(connect(socket.value, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0,
            "Decoder has no native screenshot lease service");
        constexpr char request[] = "HISTB_CAPTURE_V1\n";
        require(send(socket.value, request, sizeof(request) - 1, MSG_NOSIGNAL) == sizeof(request) - 1,
            "Could not request decoder screenshot lease");
        pollfd p = {socket.value, POLLIN, 0};
        require(poll(&p, 1, 1000) == 1 && (p.revents & POLLIN), "Decoder screenshot lease timed out");
        char text[512] = {}, control[CMSG_SPACE(sizeof(int) * 4)] = {};
        iovec io = {text, sizeof(text) - 1};
        msghdr message = {};
        message.msg_iov = &io; message.msg_iovlen = 1;
        message.msg_control = control; message.msg_controllen = sizeof(control);
        ssize_t bytes = recvmsg(socket.value, &message, MSG_CMSG_CLOEXEC);
        int received = -1, count = 0;
        for (cmsghdr *c = CMSG_FIRSTHDR(&message); c; c = CMSG_NXTHDR(&message, c)) {
            if (c->cmsg_level != SOL_SOCKET || c->cmsg_type != SCM_RIGHTS) continue;
            size_t n = (c->cmsg_len - CMSG_LEN(0)) / sizeof(int);
            const int *fds = reinterpret_cast<const int *>(CMSG_DATA(c));
            for (size_t i = 0; i < n; ++i) {
                if (!count++) received = fds[i]; else close(fds[i]);
            }
        }
        Fd receivedOwner;
        receivedOwner.value = received;
        require(bytes > 0 && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)), "Invalid decoder lease response");
        int error = 0;
        if (sscanf(text, "ERR %d", &error) == 1)
            throw std::runtime_error("Decoder capture unavailable (errno " + std::to_string(error) + ")");
        int consumed = 0;
        int fields = sscanf(text,
            "HISTB_CAPTURE_V1 %u %u %u %llu %u %u %u %u %u %u %u %u %u\n%n",
            &width, &height, &format, &modifier, &pitch[0], &offset[0], &codedWidth, &codedHeight,
            &colorspace, &range, &planes, &pitch[1], &offset[1], &consumed);
        require(fields == 13 && consumed == bytes && count == 1 && received >= 0,
            "Unsupported decoder lease protocol");
        require(width && height && width <= 4096 && height <= 4096 &&
            codedWidth >= width && codedHeight >= height && codedWidth <= 4096 && codedHeight <= 4096 &&
            planes >= 1 && planes <= 2, "Invalid decoder capture geometry");
        acquired = std::chrono::steady_clock::now();
        active = true;
        receivedOwner.value = -1;
        buffer.openBuffer(received);
    }
    void check() const
    {
        require(std::chrono::steady_clock::now() - acquired < std::chrono::milliseconds(1800),
            "Native screenshot exceeded decoder lease duration");
        pollfd p = {socket.value, POLLIN, 0};
        require(poll(&p, 1, 0) == 0, "Decoder screenshot lease ended during capture");
    }
    void release()
    {
        if (!active) return;
        check();
        buffer.endRead();
        require(send(socket.value, "DONE\n", 5, MSG_NOSIGNAL) == 5, "Could not release decoder screenshot lease");
        active = false;
    }
    ~Lease()
    {
        // Even exceptional exits finish the CPU read before the producer can recycle.
        if (active) {
            if (buffer.synced) {
                dma_buf_sync sync = {};
                sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
                ioctl(buffer.fd.value, DMA_BUF_IOCTL_SYNC, &sync);
                buffer.synced = false;
            }
            send(socket.value, "DONE\n", 5, MSG_NOSIGNAL);
        }
    }
};

struct Property {
    uint64_t value = 0;
    std::string name;
};
using Properties = std::map<std::string, Property>;
static Properties properties(int fd, uint32_t id, uint32_t type)
{
    Properties result;
    drmModeObjectPropertiesPtr values = drmModeObjectGetProperties(fd, id, type);
    require(values != nullptr, "Could not read KMS properties");
    for (unsigned i = 0; i < values->count_props; ++i) {
        drmModePropertyPtr p = drmModeGetProperty(fd, values->props[i]);
        if (!p) continue;
        Property value;
        value.value = values->prop_values[i];
        for (int e = 0; e < p->count_enums; ++e)
            if (p->enums[e].value == value.value) value.name = p->enums[e].name;
        result[p->name] = value;
        drmModeFreeProperty(p);
    }
    drmModeFreeObjectProperties(values);
    return result;
}
static uint64_t value(const Properties &p, const char *key, uint64_t fallback = 0)
{
    auto it = p.find(key);
    return it == p.end() ? fallback : it->second.value;
}

struct Plane {
    uint32_t id = 0, fb = 0;
    Properties props;
    bool video = false;
};
struct Framebuffer {
    int fd;
    drmModeFB2Ptr fb;
    Framebuffer(int descriptor, uint32_t id) : fd(descriptor), fb(drmModeGetFB2(fd, id))
    { require(fb != nullptr, "KMS framebuffer changed or is not readable"); }
    ~Framebuffer()
    {
        for (unsigned i = 0; i < 4; ++i) {
            if (!fb->handles[i]) continue;
            bool prior = false;
            for (unsigned j = 0; j < i; ++j) prior |= fb->handles[j] == fb->handles[i];
            if (!prior) drmCloseBufferHandle(fd, fb->handles[i]);
        }
        drmModeFreeFB2(fb);
    }
};

static const uint8_t rowY[128] = {
    0,8,1,9,2,10,3,11,4,12,5,13,6,14,7,15,
    12,0,13,1,14,2,15,3,8,4,9,5,10,6,11,7,
    4,12,5,13,6,14,7,15,0,8,1,9,2,10,3,11,
    8,4,9,5,10,6,11,7,12,0,13,1,14,2,15,3,
    8,0,9,1,10,2,11,3,12,4,13,5,14,6,15,7,
    0,12,1,13,2,14,3,15,4,8,5,9,6,10,7,11,
    12,4,13,5,14,6,15,7,8,0,9,1,10,2,11,3,
    4,8,5,9,6,10,7,11,0,12,1,13,2,14,3,15
};
static const uint8_t rowUV[64] = {
    0,4,1,5,2,6,3,7,4,0,5,1,6,2,7,3,
    4,0,5,1,6,2,7,3,0,4,1,5,2,6,3,7,
    4,0,5,1,6,2,7,3,0,4,1,5,2,6,3,7,
    0,4,1,5,2,6,3,7,4,0,5,1,6,2,7,3
};
struct SampleRows {
    size_t high[2][64], low[2][64], base[2];
    void prepare(const Lease &l, unsigned y)
    {
        if (l.modifier != DRM_FORMAT_MOD_HISTB_VDH_10BIT) {
            base[0] = l.offset[0] + size_t(y) * l.pitch[0];
            base[1] = l.offset[1] + size_t(y / 2) * l.pitch[1];
            return;
        }
        unsigned stride = l.pitch[0], cy = y / 2;
        size_t area = size_t(stride) * ((l.codedHeight + 63) & ~63U);
        for (unsigned tile = 0; tile < (l.codedWidth + 63) / 64; ++tile) {
            unsigned index = (y & 15) + 16 * (((y / 16) & 1) * 4 + (tile & 3));
            high[0][tile] = size_t(stride) * 16 * (y / 16) + 1024 * tile + 64 * rowY[index];
            unsigned group = tile & 3, row = y & 31;
            unsigned lowRow = (row >> 1) + ((group == 0 || group == 3 ? row & 1 : !(row & 1)) << 4);
            low[0][tile] = area * 3 / 2 + size_t(stride) * 8 * (y / 32) + 512 * tile + 16 * lowRow;
            index = (cy & 7) + 8 * (((cy / 8) & 1) * 4 + (tile & 3));
            high[1][tile] = area + size_t(stride) * 8 * (cy / 8) + 512 * tile + 64 * rowUV[index];
            lowRow = ((cy & 15) >> 1) + ((cy & 1) << 3);
            low[1][tile] = area * 7 / 4 + size_t(stride) * 4 * (cy / 16) + 256 * tile + 16 * lowRow;
        }
    }
    unsigned sample(const Lease &l, unsigned x, unsigned plane) const
    {
        if (l.modifier == DRM_FORMAT_MOD_HISTB_VDH_10BIT) {
            unsigned tile = x / 64, within = x & 63;
            return unsigned(l.buffer.byte(high[plane][tile] + within)) * 4 +
                ((l.buffer.byte(low[plane][tile] + within / 4) >> (2 * (within & 3))) & 3);
        }
        if (l.format == DRM_FORMAT_P010) return l.buffer.word(base[plane] + 2 * x) >> 6;
        if (l.format == DRM_FORMAT_NV15) {
            size_t at = base[plane] + x * 10 / 8;
            unsigned bits = l.buffer.byte(at) | unsigned(l.buffer.byte(at + 1)) << 8;
            return (bits >> ((x * 10) & 7)) & 1023;
        }
        return unsigned(l.buffer.byte(base[plane] + x)) * 4;
    }
};
static uint8_t clamp(int v) { return std::max(0, std::min(255, v)); }
struct ColorMatrix {
    int y = 0, rv = 0, gu = 0, gv = 0, bu = 0, black = 0;
    explicit ColorMatrix(const Lease &l)
    {
        // AVColorSpace BT709=1, BT2020_NCL=9; AVColorRange JPEG/full=2.
        double kr = l.colorspace == 9 ? .2627 : l.colorspace == 1 ? .2126 : .299;
        double kb = l.colorspace == 9 ? .0593 : l.colorspace == 1 ? .0722 : .114;
        double chroma = 4096. * 255 / (l.range == 2 ? 1023 : 896);
        black = l.range == 2 ? 0 : 64;
        y = 4096. * 255 / (l.range == 2 ? 1023 : 876);
        rv = chroma * 2 * (1 - kr); bu = chroma * 2 * (1 - kb);
        gu = chroma * 2 * kb * (1 - kb) / (1 - kr - kb);
        gv = chroma * 2 * kr * (1 - kr) / (1 - kr - kb);
    }
};
static std::array<uint8_t, 4> videoPixel(const Lease &l, const ColorMatrix &m, const SampleRows &rows, unsigned x)
{
    unsigned yy = rows.sample(l, x, 0), cx = x & ~1U;
    bool vu = l.modifier == DRM_FORMAT_MOD_HISTB_VDH_10BIT || l.format == DRM_FORMAT_NV21;
    unsigned u = rows.sample(l, cx + (vu ? 1 : 0), 1);
    unsigned v = rows.sample(l, cx + (vu ? 0 : 1), 1);
    int luminance = (int(yy) - m.black) * m.y;
    int cb = int(u) - 512, cr = int(v) - 512;
    return {clamp((luminance + m.rv * cr + 2048) >> 12),
        clamp((luminance - m.gu * cb - m.gv * cr + 2048) >> 12),
        clamp((luminance + m.bu * cb + 2048) >> 12), 255};
}

static void writeImage(const std::vector<uint8_t> &image, unsigned w, unsigned h, const std::string &format)
{
    if (format == "jpg") {
        jpeg_compress_struct c = {};
        jpeg_error_mgr errors;
        c.err = jpeg_std_error(&errors);
        jpeg_create_compress(&c);
        jpeg_stdio_dest(&c, stdout);
        c.image_width = w; c.image_height = h; c.input_components = 3; c.in_color_space = JCS_RGB;
        jpeg_set_defaults(&c); jpeg_set_quality(&c, 95, TRUE);
        jpeg_start_compress(&c, TRUE);
        while (c.next_scanline < h) {
            JSAMPROW row = const_cast<uint8_t *>(image.data() + size_t(c.next_scanline) * w * 3);
            jpeg_write_scanlines(&c, &row, 1);
        }
        jpeg_finish_compress(&c); jpeg_destroy_compress(&c);
    } else if (format == "png") {
        png_image p = {};
        p.version = PNG_IMAGE_VERSION; p.width = w; p.height = h; p.format = PNG_FORMAT_RGB;
        require(png_image_write_to_stdio(&p, stdout, 0, image.data(), 0, nullptr), "PNG encoding failed");
    } else {
        unsigned pitch = (w * 3 + 3) & ~3U;
        uint8_t header[54] = {'B', 'M'};
        auto le32 = [&](unsigned at, uint32_t n) {
            for (unsigned i = 0; i < 4; ++i) header[at + i] = n >> (8 * i);
        };
        le32(2, 54 + pitch * h); le32(10, 54); le32(14, 40); le32(18, w); le32(22, h);
        header[26] = 1; header[28] = 24;
        require(fwrite(header, 1, sizeof(header), stdout) == sizeof(header), "BMP header write failed");
        std::vector<uint8_t> row(pitch);
        for (unsigned y = h; y--;) {
            for (unsigned x = 0; x < w; ++x)
                for (unsigned c = 0; c < 3; ++c) row[x * 3 + c] = image[(size_t(y) * w + x) * 3 + 2 - c];
            require(fwrite(row.data(), 1, row.size(), stdout) == row.size(), "BMP image write failed");
        }
    }
    require(fflush(stdout) == 0 && !ferror(stdout), "Screenshot output failed");
}

int main(int argc, char **argv)
{
    try {
        std::string format = "jpg", mode = "all";
        unsigned requestedWidth = 0;
        for (int i = 1; i < argc; i += 2) {
            require(i + 1 < argc, "Expected --format, --mode or --width value");
            std::string key = argv[i];
            if (key == "--format") format = argv[i + 1];
            else if (key == "--mode") mode = argv[i + 1];
            else if (key == "--width") {
                char *end = nullptr;
                unsigned long n = strtoul(argv[i + 1], &end, 10);
                require(end && !*end && n >= 64 && n <= 4096, "Invalid screenshot width");
                requestedWidth = n;
            } else require(false, "Unknown screenshot option");
        }
        require(format == "jpg" || format == "png" || format == "bmp", "Unsupported image format");
        require(mode == "all" || mode == "video" || mode == "osd", "Unsupported screenshot mode");
        Fd drm;
        uint32_t crtcId = 0;
        unsigned modeWidth = 0, modeHeight = 0;
        for (int card = 0; card < 8 && drm.value < 0; ++card) {
            std::string path = "/dev/dri/card" + std::to_string(card);
            Fd candidate;
            candidate.value = open(path.c_str(), O_RDWR | O_CLOEXEC);
            if (candidate.value < 0) continue;
            drmVersionPtr v = drmGetVersion(candidate.value);
            bool histb = v && std::string(v->name, v->name_len) == "histb-vdp";
            if (v) drmFreeVersion(v);
            if (!histb || drmSetClientCap(candidate.value, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) < 0 ||
                drmSetClientCap(candidate.value, DRM_CLIENT_CAP_ATOMIC, 1) < 0) continue;
            drmModeResPtr resources = drmModeGetResources(candidate.value);
            if (!resources) continue;
            for (int c = 0; c < resources->count_crtcs; ++c) {
                drmModeCrtcPtr crtc = drmModeGetCrtc(candidate.value, resources->crtcs[c]);
                if (crtc && crtc->mode_valid) {
                    crtcId = crtc->crtc_id; modeWidth = crtc->mode.hdisplay; modeHeight = crtc->mode.vdisplay;
                }
                if (crtc) drmModeFreeCrtc(crtc);
                if (crtcId) break;
            }
            drmModeFreeResources(resources);
            if (crtcId) { drm.value = candidate.value; candidate.value = -1; }
        }
        require(drm.value >= 0 && modeWidth && modeHeight && modeWidth <= 4096 && modeHeight <= 4096,
            "No active HiSTB KMS display");
        std::vector<Plane> planes;
        drmModePlaneResPtr resources = drmModeGetPlaneResources(drm.value);
        require(resources != nullptr, "Could not enumerate HiSTB display planes");
        for (unsigned i = 0; i < resources->count_planes; ++i) {
            Properties p = properties(drm.value, resources->planes[i], DRM_MODE_OBJECT_PLANE);
            if (value(p, "CRTC_ID") != crtcId || !value(p, "FB_ID") || !value(p, "alpha", 65535)) continue;
            Framebuffer fb(drm.value, value(p, "FB_ID"));
            bool video = fb.fb->pixel_format != DRM_FORMAT_ARGB8888 && fb.fb->pixel_format != DRM_FORMAT_XRGB8888;
            if ((mode == "osd" && video) || (mode == "video" && !video)) continue;
            planes.push_back({resources->planes[i], uint32_t(value(p, "FB_ID")), std::move(p), video});
        }
        drmModeFreePlaneResources(resources);
        require(!planes.empty(), "No active display plane for requested screenshot mode");
        std::sort(planes.begin(), planes.end(), [](const Plane &a, const Plane &b) {
            return value(a.props, "zpos") < value(b.props, "zpos");
        });
        unsigned width = requestedWidth ? requestedWidth : modeWidth;
        unsigned height = std::max(1U, unsigned(uint64_t(width) * modeHeight / modeWidth));
        require(height <= 4096, "Screenshot output height exceeds limit");
        std::vector<uint8_t> image(size_t(width) * height * 3, 0);
        bool capturedVideo = false;
        for (const Plane &plane : planes) {
            require(value(plane.props, "rotation", 1) == 1, "Rotated planes cannot be captured");
            unsigned sw = value(plane.props, "SRC_W") >> 16, sh = value(plane.props, "SRC_H") >> 16;
            unsigned sx = value(plane.props, "SRC_X") >> 16, sy = value(plane.props, "SRC_Y") >> 16;
            int dx = int32_t(value(plane.props, "CRTC_X")), dy = int32_t(value(plane.props, "CRTC_Y"));
            unsigned dw = value(plane.props, "CRTC_W"), dh = value(plane.props, "CRTC_H");
            require(sw && sh && dw && dh, "Invalid KMS plane geometry");
            Lease lease;
            Mapping osd;
            std::unique_ptr<Framebuffer> fb;
            unsigned pitch = 0, offset = 0, pixelFormat = 0;
            if (plane.video) {
                require(!capturedVideo, "Multiple video planes need separate decoder capture leases");
                lease.acquire();
                require(sx + sw <= lease.width && sy + sh <= lease.height, "KMS crop changed during decoder capture");
                if (lease.modifier == DRM_FORMAT_MOD_HISTB_VDH_10BIT) {
                    require(lease.format == DRM_FORMAT_YUV420_10BIT && lease.planes == 1 && !lease.offset[0] &&
                        lease.pitch[0] == ((lease.codedWidth + 255) & ~255U), "Invalid native HT10 layout");
                    size_t area = size_t(lease.pitch[0]) * ((lease.codedHeight + 63) & ~63U);
                    require(lease.buffer.size >= area * 15 / 8, "Truncated native HT10 surface");
                } else {
                    require(lease.modifier == DRM_FORMAT_MOD_LINEAR && lease.planes == 2 &&
                        (lease.format == DRM_FORMAT_NV12 || lease.format == DRM_FORMAT_NV21 ||
                        lease.format == DRM_FORMAT_P010 || lease.format == DRM_FORMAT_NV15), "Unsupported leased video format");
                    unsigned rowBytes = lease.format == DRM_FORMAT_P010 ? lease.codedWidth * 2 :
                        lease.format == DRM_FORMAT_NV15 ? (lease.codedWidth * 10 + 7) / 8 : lease.codedWidth;
                    require(lease.pitch[0] >= rowBytes && lease.pitch[1] >= rowBytes && !(lease.width & 1) &&
                        size_t(lease.offset[0]) + size_t(lease.pitch[0]) * lease.codedHeight <= lease.buffer.size &&
                        size_t(lease.offset[1]) + size_t(lease.pitch[1]) * ((lease.codedHeight + 1) / 2) <= lease.buffer.size,
                        "Invalid leased video plane layout");
                }
                capturedVideo = true;
            } else {
                fb.reset(new Framebuffer(drm.value, plane.fb));
                require(fb->fb->modifier == DRM_FORMAT_MOD_LINEAR && fb->fb->handles[0] &&
                    sx + sw <= fb->fb->width && sy + sh <= fb->fb->height, "Unsupported OSD layout");
                int prime = -1;
                require(drmPrimeHandleToFD(drm.value, fb->fb->handles[0], DRM_CLOEXEC | DRM_RDWR, &prime) == 0,
                    "Could not export OSD DMA buffer");
                osd.openBuffer(prime);
                pitch = fb->fb->pitches[0]; offset = fb->fb->offsets[0]; pixelFormat = fb->fb->pixel_format;
                require(pitch >= fb->fb->width * 4 && size_t(offset) + size_t(pitch) * fb->fb->height <= osd.size,
                    "Invalid OSD framebuffer pitch");
            }
            auto blend = plane.props.find("pixel blend mode");
            std::string blendMode = blend == plane.props.end() ? "Pre-multiplied" : blend->second.name;
            unsigned globalAlpha = value(plane.props, "alpha", 65535);
            ColorMatrix matrix(lease);
            SampleRows samples;
            std::array<int, 4096> sourceX;
            for (unsigned x = 0; x < width; ++x) {
                int mx = uint64_t(x) * modeWidth / width;
                sourceX[x] = mx < dx || uint64_t(mx - dx) >= dw ? -1 :
                    int(sx + uint64_t(mx - dx) * sw / dw);
            }
            for (unsigned y = 0; y < height; ++y) {
                if (plane.video && !(y & 15)) lease.check();
                int my = uint64_t(y) * modeHeight / height;
                if (my < dy || uint64_t(my - dy) >= dh) continue;
                unsigned py = sy + uint64_t(my - dy) * sh / dh;
                if (plane.video) samples.prepare(lease, py);
                for (unsigned x = 0; x < width; ++x) {
                    if (sourceX[x] < 0) continue;
                    unsigned px = sourceX[x];
                    std::array<uint8_t, 4> pixel;
                    if (plane.video) pixel = videoPixel(lease, matrix, samples, px);
                    else {
                        size_t at = offset + size_t(py) * pitch + px * 4;
                        pixel = {osd.byte(at + 2), osd.byte(at + 1), osd.byte(at),
                            uint8_t(pixelFormat == DRM_FORMAT_XRGB8888 || blendMode == "None" ? 255 : osd.byte(at + 3))};
                    }
                    unsigned alpha = unsigned(pixel[3]) * globalAlpha / 65535;
                    size_t at = (size_t(y) * width + x) * 3;
                    bool premultiplied = !plane.video && blendMode == "Pre-multiplied";
                    for (unsigned c = 0; c < 3; ++c) {
                        unsigned source = premultiplied ? unsigned(pixel[c]) * globalAlpha / 65535 : unsigned(pixel[c]) * alpha / 255;
                        image[at + c] = clamp(source + unsigned(image[at + c]) * (255 - alpha) / 255);
                    }
                }
            }
            if (plane.video) lease.release();
            Properties after = properties(drm.value, plane.id, DRM_MODE_OBJECT_PLANE);
            for (const char *key : {"CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H"})
                require(value(after, key) == value(plane.props, key), "KMS geometry changed during screenshot");
            if (!plane.video) require(value(after, "FB_ID") == plane.fb, "OSD framebuffer changed during screenshot");
        }
        require(mode == "osd" || capturedVideo, "No active video frame; choose OSD-only capture");
        drmModeCrtcPtr finalCrtc = drmModeGetCrtc(drm.value, crtcId);
        bool sameMode = finalCrtc && finalCrtc->mode_valid && finalCrtc->mode.hdisplay == modeWidth && finalCrtc->mode.vdisplay == modeHeight;
        if (finalCrtc) drmModeFreeCrtc(finalCrtc);
        require(sameMode, "Display mode changed during screenshot");
        writeImage(image, width, height, format);
        return 0;
    } catch (const std::exception &e) {
        fprintf(stderr, "histb-screenshot: %s\n", e.what());
        return 1;
    }
}
