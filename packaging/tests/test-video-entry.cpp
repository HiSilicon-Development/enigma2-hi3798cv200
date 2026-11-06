#include "../histb_video_entry.h"
#include <cstdio>

static int failures;

static void check(const char *name, AVCodecID codec, const uint8_t *data, size_t size, bool expected)
{
	bool actual = histbVideoEntryPoint(codec, data, size);
	if (actual != expected)
	{
		std::fprintf(stderr, "FAIL %s: expected %d, got %d\n", name, expected, actual);
		++failures;
	}
}

template<size_t N>
static void check(const char *name, AVCodecID codec, const uint8_t (&data)[N], bool expected)
{
	check(name, codec, data, N, expected);
}

int main()
{
	const uint8_t h264AudSps[] = {0,0,0,1,9,0x50,0,0,0,1,0x67,0x64};
	const uint8_t h264SeiIdr[] = {0,0,1,6,0x80,0,0,1,0x65,0x88};
	const uint8_t h264Dependent[] = {0,0,0,1,9,0x50,0,0,1,0x41,0x9a};
	const uint8_t hevcAudVps[] = {0,0,0,1,0x46,1,0x50,0,0,1,0x40,1};
	const uint8_t hevcSeiCra[] = {0,0,1,0x4e,1,0x80,0,0,1,0x2a,1};
	const uint8_t hevcDependent[] = {0,0,1,0x46,1,0x50,0,0,1,2,1};
	const uint8_t mpegExtensionSequence[] = {0,0,1,0xb5,0x10,0,0,1,0xb3,0x2d};
	const uint8_t mpegPictureOnly[] = {0,0,1,0,0,8};
	const uint8_t cavsExtensionIntra[] = {0,0,1,0xb5,0,0,1,0xb3,0};
	const uint8_t cavsDependent[] = {0,0,1,0xb6,0};
	const uint8_t incomplete[] = {0,0,1};
	check("H264 AUD before SPS (Jade stream layout)", AV_CODEC_ID_H264, h264AudSps, true);
	check("H264 SEI before IDR", AV_CODEC_ID_H264, h264SeiIdr, true);
	check("H264 dependent pictures are not entry points", AV_CODEC_ID_H264, h264Dependent, false);
	check("HEVC AUD before VPS", AV_CODEC_ID_HEVC, hevcAudVps, true);
	check("HEVC prefix SEI before CRA", AV_CODEC_ID_HEVC, hevcSeiCra, true);
	check("HEVC dependent pictures are not entry points", AV_CODEC_ID_HEVC, hevcDependent, false);
	check("MPEG2 extension before sequence", AV_CODEC_ID_MPEG2VIDEO, mpegExtensionSequence, true);
	check("MPEG1 extension before sequence", AV_CODEC_ID_MPEG1VIDEO, mpegExtensionSequence, true);
	check("MPEG2 picture alone has no sequence", AV_CODEC_ID_MPEG2VIDEO, mpegPictureOnly, false);
	check("CAVS extension before intra picture", AV_CODEC_ID_CAVS, cavsExtensionIntra, true);
	check("CAVS dependent picture", AV_CODEC_ID_CAVS, cavsDependent, false);
	check("Truncated start code", AV_CODEC_ID_H264, incomplete, false);
	check("Empty payload", AV_CODEC_ID_H264, nullptr, 0, false);
	if (!failures) std::puts("PASS video entry scanning: leading delimiters, metadata, codec entry points and incomplete payloads");
	return failures ? 1 : 0;
}
