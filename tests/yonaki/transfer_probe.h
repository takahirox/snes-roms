// Read-only instrumentation for the pinned emulator builds. H positions are master clocks.
#include <stdint.h>
#include <stdio.h>

struct YonakiBeam {
    unsigned line, clock, line_clocks, vblank_start, hblank_start, frame;
    bool forced_blank;
};

struct YonakiTransfers {
    uint32_t forced_dma_bytes, forced_dma_max_transfer;
    uint32_t visible_dma_bytes, visible_dma_peak, visible_dma_peak_end, visible_dma_latest;
    uint32_t hdma_bytes, hdma_peak, hdma_first, hdma_last;
    uint32_t violations;
};

static YonakiTransfers yonaki_transfers = {};
static unsigned yonaki_frame = 0;
static unsigned yonaki_visible_frame_bytes = 0, yonaki_hdma_frame_bytes = 0;

extern "C" __attribute__((visibility("default")))
const YonakiTransfers* yonaki_transfer_probe() {
    return &yonaki_transfers;
}

static void yonaki_vblank() {
    ++yonaki_frame;
    yonaki_visible_frame_bytes = yonaki_hdma_frame_bytes = 0;
}

static void yonaki_violation(const char* kind, YonakiBeam first, YonakiBeam last) {
    if (++yonaki_transfers.violations == 1)
        fprintf(stderr, "%s outside transfer window: V%u H%u -> V%u H%u\n",
                kind, first.line, first.clock, last.line, last.clock);
}

static void yonaki_mdma(YonakiBeam first, YonakiBeam last, unsigned bytes) {
    auto& t = yonaki_transfers;
    if (first.forced_blank && last.forced_blank) {
        t.forced_dma_bytes += bytes;
        if (bytes > t.forced_dma_max_transfer) t.forced_dma_max_transfer = bytes;
    } else if (first.forced_blank || last.forced_blank || first.line < first.vblank_start ||
               first.frame != last.frame || last.line < first.line || last.clock >= last.line_clocks ||
               (first.line == last.line && last.clock < first.clock)) {
        yonaki_violation("PPU DMA", first, last);
    } else {
        t.visible_dma_bytes += bytes;
        yonaki_visible_frame_bytes += bytes;
        // Order completions by scanline and then by master clock.
        unsigned position = (last.line << 16) | last.clock;
        if (yonaki_visible_frame_bytes > t.visible_dma_peak ||
            (yonaki_visible_frame_bytes == t.visible_dma_peak && position > t.visible_dma_peak_end)) {
            t.visible_dma_peak = yonaki_visible_frame_bytes;
            t.visible_dma_peak_end = position;
        }
        if (position > t.visible_dma_latest) t.visible_dma_latest = position;
    }
}

static void yonaki_hdma(YonakiBeam first, YonakiBeam last, unsigned channel,
                        unsigned target, unsigned bytes) {
    auto& t = yonaki_transfers;
    // $210D mode 2, two writes to BG1 horizontal scroll on channel 7.
    if (channel != 7 || target != 0x0d || bytes != 2 ||
        first.line >= first.vblank_start || first.frame != last.frame || first.line != last.line ||
        first.clock < first.hblank_start || last.clock < first.clock ||
        last.clock >= last.line_clocks) {
        yonaki_violation("Ripple HDMA", first, last);
    }
    if (!t.hdma_bytes || first.clock < t.hdma_first) t.hdma_first = first.clock;
    if (last.clock > t.hdma_last) t.hdma_last = last.clock;
    t.hdma_bytes += bytes;
    yonaki_hdma_frame_bytes += bytes;
    if (yonaki_hdma_frame_bytes > t.hdma_peak) t.hdma_peak = yonaki_hdma_frame_bytes;
}
