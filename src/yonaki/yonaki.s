; 夜鳴き鐘 -- SFC sound novel (65816, ca65).  docs/yonaki/ENGINE.md describes the whole engine.
;
; Mode 4: BG1 = 8bpp photo 256x192 (768 tiles, screen y 16-207; the bands above and below are the blank
; tile 768), BG2 = 2bpp text bitmap 240x192 (30 x 24 tiles from screen x 8, y 16) drawn by the CPU in WRAM.
; The photo tiles live in WRAM ($7F:0000-$BFFF) too: silhouettes are composited there and the changed
; tiles are uploaded again.  Colour math subtracts a fixed colour from BG1 (the dim under the text, dark)
; or adds one to everything (white / red flash, white transitions).
;
; Frame protocol: the game runs as one straight thread that calls WaitFrame once per frame.  WaitFrame
; advances the effects (Tick), turns pending uploads into DMA jobs within DMA_BUDGET bytes (PumpUploads),
; sends one sound command, sets frame_ready and waits for the NMI.  The NMI runs the jobs only when
; frame_ready is set (the thread is parked in WaitFrame then), writes the PPU registers from their
; shadows and records the V counter at its end (nmi_end_line_max, vblank_overrun_count).
; Long CPU work (picture loads) is done in forced blank or under a full dim, a slice per frame.
;
; Conventions: native mode, X/Y 16 bit, A 16 bit except around byte work, DB = $00, D = $0000.
; Code and tables in bank $00 (SlowROM mirror); the data banks are read at $81-$FF (FastROM, MEMSEL = 1).

.setcpu "65816"
.smart -
.macpack longbranch
.include "const.inc"            ; build/yonaki/ (or the test build) via ca65 -I

; ---------------------------------------------------------------- hardware
INIDISP = $2100
OBJSEL  = $2101
BGMODE  = $2105
MOSAIC  = $2106
BG1SC   = $2107
BG2SC   = $2108
BG3SC   = $2109
BG12NBA = $210B
BG1HOFS = $210D
BG1VOFS = $210E
BG2HOFS = $210F
BG2VOFS = $2110
VMAIN   = $2115
VMADDL  = $2116
VMDATAL = $2118
CGADD   = $2121
CGDATA  = $2122
W12SEL  = $2123
TM      = $212C
TS      = $212D
TMW     = $212E
CGWSEL  = $2130
CGADSUB = $2131
COLDATA = $2132
SETINI  = $2133
SLHV    = $2137
STAT78  = $213F
OPVCT   = $213D
APUIO0  = $2140
APUIO1  = $2141
APUIO2  = $2142
APUIO3  = $2143
WMDATA  = $2180
WMADDL  = $2181
WMADDM  = $2182
WMADDH  = $2183
NMITIMEN = $4200
MDMAEN  = $420B
HDMAEN  = $420C
MEMSEL  = $420D
RDNMI   = $4210
HVBJOY  = $4212
JOY1L   = $4218
DMAP0   = $4300
BBAD0   = $4301
A1T0L   = $4302
A1B0    = $4304
DAS0L   = $4305
DMAP1   = $4310
BBAD1   = $4311
A1T1L   = $4312
A1B1    = $4314
DAS1L   = $4315
DMAP7   = $4370
BBAD7   = $4371
A1T7L   = $4372
A1B7    = $4374

PAD_B      = $8000
PAD_Y      = $4000
PAD_SELECT = $2000
PAD_START  = $1000
PAD_UP     = $0800
PAD_DOWN   = $0400
PAD_LEFT   = $0200
PAD_RIGHT  = $0100
PAD_A      = $0080
PAD_X      = $0040
PAD_L      = $0020
PAD_R      = $0010
PAD_DIRS   = $0F00

; VRAM (word addresses)
VRAM_BG1TILES = $0000           ; 768 x 32 words
VRAM_BG2TILES = $6000           ; tiles 0-3 zero (= BG1 tile 768, the blank), 4.. the bitmap
VRAM_TEXT     = $6020
VRAM_BG1MAP   = $7800
VRAM_BG2MAP   = $7C00
BLANK_TILE    = 768

; WRAM
BMP       = $7E2000             ; text bitmap: 24 tile rows x 30 tiles x 16 bytes
BMP_COLS  = 30
BMP_ROW   = 480
BMP_SIZE  = 11520
MAPBUF    = $7E5000             ; BG2 map shadow (32 x 32 words)
BMPSAVE   = $7E5800             ; the bitmap under the START menu
PHOTO     = $7F0000             ; photo tiles (49152 bytes)

BOOT_FRAMES = 150
GLYPHS_PER_FRAME = 5
TILES_PER_FRAME = 12
DMA_BUDGET = 3072               ; bytes per V-blank (4096 in wide photo-row jobs ran past line 261; see nmi_end_line_max in the tests)
JOB_MAX   = 24

; text layout (bitmap coordinates: x 0-239 = screen 8-247, y 0-191 = screen 16-207)
TX0       = 12                  ; screen x 20
TY0       = 2                   ; line n at TY0 + 16 n (screen 18 + 16 n)
PAGE_LINES = 12
CHOICE_X  = 26                  ; option letter (cursor at TX0)
OPT_TEXT_X = CHOICE_X + 16      ; option text (tools/yonaki/script.py CHOICE_PX)
DIM_TEXT  = 0                   ; BG1 minus this much under text (of 31; tools/yonaki/build.py reads it)
DIM_MENU  = 15

; ui_state (for the tests)
ST_BOOT = 0
ST_TITLE = 1
ST_TYPE = 2
ST_WAIT = 3
ST_CHOICE = 4
ST_MENU = 5
ST_SLOTS = 6
ST_ENDLIST = 7
ST_ENDING = 8
ST_CHAPTER = 9
ST_BUSY = 10
ST_CONFIRM = 11
ST_NAME = 12

; ---------------------------------------------------------------- variables
.segment "ZEROPAGE"
p0:       .res 4               ; long pointers
p1:       .res 4
p2:       .res 4
vp:       .res 4               ; script pointer
t0:       .res 2
t1:       .res 2
t2:       .res 2
t3:       .res 2
t4:       .res 2
t5:       .res 2
t6:       .res 2
t7:       .res 2
g_glyph:  .res 2
g_x:      .res 2
g_y:      .res 2
g_col:    .res 2               ; 1 white, 3 grey, 0 erase
g_w:      .res 2
g_addr:   .res 2
g_shift:  .res 2
g_row:    .res 2
g_prev:   .res 2
g_cur:    .res 2
g_w0:     .res 1               ; white mask, 3 bytes
g_w1:     .res 1
g_w2:     .res 1
g_s0:     .res 1               ; shadow mask
g_s1:     .res 1
g_s2:     .res 1
g_pad:    .res 2
g_space:  .res 2               ; extra pixels after each glyph (letter spacing)
s_m0:     .res 2               ; silhouette colour masks
s_m1:     .res 2
s_tr:     .res 2               ; 1: the silhouette is translucent

.segment "BSS"
; statistics for the tests
nmi_count:        .res 2
lag_count:        .res 2
main_count:       .res 2
frame_ready:      .res 2
dma_bytes:        .res 2
dma_bytes_max:    .res 2
dma_deferred:     .res 2
nmi_end_line:     .res 2
nmi_end_line_max: .res 2
vblank_overrun_count: .res 2
spc_ready:        .res 2
text_clip:        .res 2
ui_state:         .res 2
; register shadows (written by the NMI)
inidisp:   .res 2
reg_tm:    .res 2
reg_mosaic: .res 2
reg_cgadsub: .res 2
reg_col_r: .res 2
reg_col_g: .res 2
reg_col_b: .res 2
reg_hofs:  .res 2
reg_vofs:  .res 2
reg_hdma:  .res 2
reg_hdma_src: .res 2
; input
pad:      .res 2
pad_prev: .res 2
pad_new:  .res 2
pad_rep:  .res 2
pad_carry: .res 2
rep_timer: .res 2
; DMA jobs (8 bytes: dest, type (0 VRAM, 1 CGRAM) | bank << 8, source, length)
job_head: .res 2
job_tail: .res 2
jobs:     .res JOB_MAX*8
; pending uploads
text_dirty: .res 4             ; text bitmap tile rows 0-23 (bit n = row n)
photo_dirty: .res 4            ; photo tile rows 0-23
photo_c0:  .res 2              ; tile columns [photo_c0, photo_c1) of the dirty photo rows
photo_c1:  .res 2
pal_dirty: .res 2
pal_src:   .res 4              ; long address of the 240 photo colours
tint_dirty: .res 2
tint_up:   .res 4              ; long address of the 112 translucent-figure colours to upload (CGRAM 144)
ui_dirty:  .res 2
map_dirty: .res 2
ui_pal:    .res 32
; effects
bright:    .res 2              ; master brightness 0-15
blanked:   .res 2              ; 1: forced blank
dim_cur:   .res 2
dim_step:  .res 2
text_on:   .res 2              ; text on the page: the photo is dimmed
dark_on:   .res 2              ; @fx dark
hide_bg1:  .res 2              ; dimmed out fully (silhouette updates)
menu_dim:  .res 2
add_level: .res 2              ; colour addition (flash / white)
add_red:   .res 2
add_decay: .res 2
shake:     .res 2
ripple_on: .res 2
ripple_phase: .res 2
mosaic:    .res 2
blink:     .res 2
; text page
page_line: .res 2              ; lines used on the page
cur_line:  .res 2
str_x0:    .res 2
hl_line:   .res 2              ; highlighted line (palette 1) or $FFFF
hl_count:  .res 2
speed:     .res 2              ; 0 slow, 1 normal, 2 fast, 3 instant
type_budget: .res 2
type_timer: .res 2
instant:   .res 2
ff:        .res 2              ; fast-forward (B held over read text)
cur_read:  .res 2
mark_x:    .res 2
mark_y:    .res 2
mark_on:   .res 2
mark_glyph: .res 2
; VM
vm_sp:     .res 2
cur_text:  .res 2              ; text id of the paragraph being shown / waited on
last_text: .res 2              ; last paragraph on the page ($FFFF none)
save_kind: .res 2              ; 1 waiting on a paragraph, 2 on a choice
save_id:   .res 2
lflags:    .res 64             ; local flags (512)
gflags:    .res 4              ; global flags (SRAM copy)
gendings:  .res 4              ; endings seen (SRAM copy)
chapter_cur: .res 2            ; $FFFF none
paragraphs: .res 2             ; paragraphs shown (tests)
endings_reached: .res 2        ; last ending index + 1 (tests)
redraw:    .res 2              ; 1: OpText draws instantly and does not wait (loading a choice)
; choices
opt_count: .res 2
opt_sel:   .res 2
opt_addr:  .res 16             ; target low words
opt_bank:  .res 16
opt_text:  .res 16             ; text pointer low words (bank = opt_tbank)
opt_tbank: .res 16
opt_lines: .res 16
opt_line:  .res 16             ; first page line of each option
choice_id: .res 2
; pictures and silhouettes
pic_cur:   .res 2
pic_entry: .res 2              ; PicTable offset of pic_cur
sil_key:   .res 8              ; 4 slots: key ($FF free), silhouette, x tile, colour
sil_id:    .res 8
sil_x:     .res 8
sil_col:   .res 8
sil_dirty: .res 2
tint_ok:   .res 2              ; 1: the picture has translucent-figure colours
tint_col:  .res 2              ; the colour drawn translucent (0 blue, 1 white, 2 red)
reg_c0:    .res 2              ; columns / top row composited last time
reg_c1:    .res 2
reg_top:   .res 2
new_c0:    .res 2
new_c1:    .res 2
new_top:   .res 2
rs_top:    .res 2              ; RestoreRows arguments and state
rs_c0:     .res 2
rs_c1:     .res 2
rs_row:    .res 2
rs_len:    .res 2
rs_bytes:  .res 2
c_x:       .res 2              ; Composite state
c_w:       .res 2
c_h:       .res 2
c_row:     .res 2
c_tx:      .res 2
c_ty:      .res 2
c_n:       .res 2
; sound
snd_queue: .res 16
snd_count: .res 2
spc_toggle: .res 2
snd_sent:  .res 2
music_cur: .res 2
amb_cur:   .res 2
; menus
menu_sel:  .res 2
menu_count: .res 2
menu_item: .res 16
menu_kind: .res 16
menu_cx:   .res 2
menu_hlc:  .res 2
menu_cancel: .res 2
list_first: .res 2
list_k:    .res 2
list_i:    .res 2
slot_mode: .res 2
slot_k:    .res 2
slot_any:  .res 2
end_index: .res 2
menu_last_text: .res 2
debug_vp:  .res 4              ; (review builds) start address of はじめから
sil_comp:  .res 2
glyph_count: .res 2            ; glyphs drawn in this frame (DrawGlyph paces itself)
work_count: .res 2             ; silhouette tiles composited in this frame
boot_frames: .res 2            ; frames the sound driver upload took              ; brightness added to the silhouette colours (8-13) against the dim
slot_valid: .res 6
list_page: .res 2
saved_line: .res 2
saved_hl:  .res 2
saved_hlc: .res 2
saved_text_on: .res 2
num_buf:   .res 8
save_seq:  .res 2
save_ok:   .res 2
loads_done: .res 2
saves_done: .res 2
sram_resets: .res 2            ; bit 0 global, bit 1 read marks were reset at boot
save_buf:  .res 256
; the names the player set (NameEntry): the hero's family name at +0, the heroine's given name at +10, each a length word and NAME_MAX glyphs
names:     .res 20
name_left: .res 2              ; glyphs of a name still to come from ReadCode
name_pos:  .res 2              ; offset in names of the next one
ne_field:  .res 2              ; name entry: 0 主人公, 1 ヒロイン
ne_page:   .res 2
ne_row:    .res 2              ; 0..NAME_ROWS-1 the characters, NAME_ROWS the commands
ne_col:    .res 2
ne_i:      .res 2              ; name entry: position in a name
ne_g:      .res 2              ; glyph being typed

; ---------------------------------------------------------------- header
.segment "HEADER"
    .byte "YONAKIGANE      "               ; $FFB0: (unused extended header area)
    .byte "YONAKIGANE           "          ; 21 bytes
    .byte $30                          ; LoROM, FastROM
    .byte $02                          ; ROM + RAM + battery
    .byte ROM_SIZE_BYTE
    .byte $03                          ; 8 KiB SRAM
    .byte $00                          ; Japan
    .byte $00                          ; licensee
    .byte $00                          ; version
    .word $FFFF, $0000                 ; checksum complement / checksum (tools/yonaki/romfix.py)
    .word 0, 0                         ; $FFE0
    .word EmptyVector                  ; COP
    .word EmptyVector                  ; BRK
    .word EmptyVector                  ; ABORT
    .word Nmi                          ; NMI
    .word 0
    .word EmptyVector                  ; IRQ
    .word 0, 0                         ; $FFF0
    .word EmptyVector                  ; COP (emulation)
    .word 0
    .word EmptyVector                  ; ABORT
    .word EmptyVector                  ; NMI (emulation)
    .word Reset                        ; RESET
    .word EmptyVector                  ; IRQ/BRK (emulation)

; ---------------------------------------------------------------- reset
.segment "CODE"
EmptyVector:
    rti

.a8
.i16
Reset:
    sei
    clc
    xce
    rep #$38
    .a16
    .i16
    ldx #$1FFF
    txs
    lda #$0000
    tcd
    sep #$20
    .a8
    pha
    plb                         ; DB = $00
    lda #$80
    sta INIDISP
    stz NMITIMEN
    stz HDMAEN
    stz MDMAEN
    lda #$01
    sta MEMSEL                  ; FastROM for the data banks $80-$FF
    ldx #$2101
@clr:
    stz $00,x
    inx
    cpx #$2134
    bne @clr
    lda #$80
    sta INIDISP
    rep #$20
    .a16
    ; low WRAM (not the stack page in use) and $7E:2000-$7F:FFFF
    ldx #$0000
:   stz $0000,x
    inx
    inx
    cpx #$1E00
    bne :-
    lda #$7E
    jsr ClearWramBank
    lda #$7F
    jsr ClearWramBank
    jsr ClearVram
    lda #$80
    sta inidisp
    lda #1
    sta blanked
    sep #$20
    .a8
    lda #$80
    sta NMITIMEN                ; NMI only while the sound driver goes up
    rep #$20
    .a16
    jsr InitSpc
    lda nmi_count
    sta boot_frames
:   lda nmi_count               ; the boot takes BOOT_FRAMES whatever the upload took: the first frame of the
    cmp #BOOT_FRAMES            ; game is the same on every core
    bcc :-
    sep #$20
    .a8
    stz NMITIMEN
    rep #$20
    .a16
    jsr InitPpu
    jsr InitState
.if DEBUG_START
    lda f:$701FF0
    cmp #$4244                  ; "DB"
    bne :+
    lda f:$701FF2
    sta debug_vp
    lda f:$701FF4
    and #$00FF
    sta debug_vp+2
:
.endif
    jsr SramBoot
    stz nmi_count
    stz lag_count
    stz nmi_end_line_max
    stz vblank_overrun_count
    sep #$20
    .a8
:   lda HVBJOY
    bmi :-
:   lda HVBJOY
    bpl :-
:   lda HVBJOY
    bmi :-
    lda #$81
    sta NMITIMEN                ; NMI + auto joypad read
    rep #$20
    .a16
Main:
    jsr TitleScreen             ; never returns (the VM returns to it)
    bra Main

; ---------------------------------------------------------------- NMI
Nmi:
    rep #$30
    pha
    phx
    phy
    phb
    phd
    sep #$20
    .a8
    lda #$00
    pha
    plb
    lda RDNMI
    rep #$20
    .a16
    lda #$0000
    tcd
    inc nmi_count
    lda frame_ready
    bne @upload
    inc lag_count
    jmp @regs
@upload:
    stz dma_bytes
    ldx job_head
@job:
    cpx job_tail
    beq @jobs_done
    lda dma_bytes
    beq @take
    clc
    adc jobs+6,x
    cmp #DMA_BUDGET+1
    bcc @take
    inc dma_deferred
    bra @jobs_left
@take:
    lda jobs+2,x
    and #$00FF
    bne @cgram
    lda jobs+0,x
    sta VMADDL
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    bra @src
@cgram:
    .a16
    sep #$20
    .a8
    lda jobs+0,x
    sta CGADD
    stz DMAP0
    lda #$22
    sta BBAD0
@src:
    lda jobs+3,x
    sta A1B0
    rep #$20
    .a16
    lda jobs+4,x
    sta A1T0L
    lda jobs+6,x
    sta DAS0L
    clc
    adc dma_bytes
    sta dma_bytes
    sep #$20
    .a8
    lda #$01
    sta MDMAEN
    rep #$20
    .a16
    txa
    clc
    adc #8
    tax
    bra @job
@jobs_done:
    ldx #0
    stx job_tail
@jobs_left:
    stx job_head
    lda dma_bytes
    cmp dma_bytes_max
    bcc :+
    sta dma_bytes_max
:   stz frame_ready
@regs:
    sep #$20
    .a8
    lda inidisp
    sta INIDISP
    lda reg_tm
    sta TM
    lda reg_mosaic
    sta MOSAIC
    lda reg_cgadsub
    sta CGADSUB
    lda reg_col_r
    sta COLDATA
    lda reg_col_g
    sta COLDATA
    lda reg_col_b
    sta COLDATA
    lda reg_hofs
    sta BG1HOFS
    lda reg_hofs+1
    sta BG1HOFS
    lda reg_vofs
    sta BG1VOFS
    lda reg_vofs+1
    sta BG1VOFS
    lda reg_hdma
    beq @nohdma
    ldx reg_hdma_src
    stx A1T7L
    lda #$80
    sta HDMAEN
    bra @hdone
@nohdma:
    stz HDMAEN
@hdone:
    ; V counter at the end of the work
    lda SLHV
    lda STAT78
    lda OPVCT
    xba
    lda OPVCT
    and #$01
    xba
    rep #$20
    .a16
    sta nmi_end_line
    ldx blanked
    bne @done                   ; forced blank: nothing is drawn, nothing to overrun
    cmp #225
    bcs :+
    inc vblank_overrun_count
    bra @done
:   cmp nmi_end_line_max
    bcc @done
    sta nmi_end_line_max
@done:
    pld
    plb
    ply
    plx
    pla
    rti

; ---------------------------------------------------------------- init
.a16
.i16
; A = WRAM bank ($7E: from $2000, $7F: all) -> zero, by DMA from a fixed zero word (channel 1)
ClearWramBank:
    cmp #$7E
    bne @full
    lda #$2000
    sta WMADDL
    ldx #$E000
    sep #$20
    .a8
    stz WMADDH
    bra @go
@full:
    .a16
    lda #$0000
    sta WMADDL
    ldx #$0000                  ; 65536
    sep #$20
    .a8
    lda #$01
    sta WMADDH
@go:
    lda #$08                    ; fixed source, one register
    sta DMAP1
    lda #<WMDATA
    sta BBAD1
    ldy #.loword(ZeroWord)
    sty A1T1L
    lda #^ZeroWord
    sta A1B1
    stx DAS1L
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    rts

ClearVram:
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    ldx #$0000
    stx VMADDL
    lda #$09                    ; fixed source, two registers
    sta DMAP0
    lda #$18
    sta BBAD0
    ldx #.loword(ZeroWord)
    stx A1T0L
    lda #^ZeroWord
    sta A1B0
    ldx #$0000                  ; 65536 bytes
    stx DAS0L
    lda #$01
    sta MDMAEN
    stz CGADD
    ldx #512
:   stz CGDATA
    dex
    bne :-
    rep #$20
    .a16
    rts

InitPpu:
    sep #$20
    .a8
    lda #$04                    ; mode 4
    sta BGMODE
    lda #(VRAM_BG1MAP >> 8) & $FC
    sta BG1SC
    lda #(VRAM_BG2MAP >> 8) & $FC
    sta BG2SC
    lda #((VRAM_BG2TILES >> 12) << 4) | (VRAM_BG1TILES >> 12)
    sta BG12NBA
    lda #(VRAM_BG2TILES >> 8) & $FC  ; mode 4 offset-per-tile reads the BG3 map: point it at zero words
    sta BG3SC
    stz OBJSEL
    stz MOSAIC
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF                    ; V scroll -1: map row 0 on the first line
    sta BG1VOFS
    lda #$03
    sta BG1VOFS
    lda #$FF
    sta BG2VOFS
    lda #$03
    sta BG2VOFS
    lda #$03
    sta TM
    stz TS
    stz TMW
    stz W12SEL
    stz CGWSEL                  ; colour math always, with the fixed colour
    stz CGADSUB
    lda #$E0
    sta COLDATA
    stz SETINI
    ; HDMA channel 7: BG1HOFS, write twice, the table in bank 0 (RippleTable)
    lda #$02
    sta DMAP7
    lda #<BG1HOFS
    sta BBAD7
    lda #^RippleTable
    sta A1B7
    ; colours 0-15
    stz CGADD
    ldx #0
:   lda f:SysPalette,x
    sta CGDATA
    inx
    cpx #32
    bne :-
    ; BG1 map: rows 2-25 = tiles 0-767, others the blank tile
    lda #$80
    sta VMAIN
    rep #$20
    .a16
    lda #VRAM_BG1MAP
    sta VMADDL
    ldy #0
@r1:
    ldx #0
@c1:
    cpy #2
    bcc @blank1
    cpy #26
    bcs @blank1
    tya
    sec
    sbc #2
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t0
    txa
    clc
    adc t0
    bra @put1
@blank1:
    lda #BLANK_TILE
@put1:
    sta VMDATAL
    inx
    cpx #32
    bne @c1
    iny
    cpy #32
    bne @r1
    ; BG2 map shadow: rows 2-25, columns 1-30 = tiles 4.., others tile 0
    ldx #0                      ; byte offset in the map
    ldy #0                      ; row
@r2:
    stz t1                      ; column
@c2:
    lda #0
    cpy #2
    bcc @put2
    cpy #26
    bcs @put2
    lda t1
    beq @put2
    cmp #31
    bcs @blank2
    tya
    sec
    sbc #2
    sta t0
    asl a
    asl a
    asl a
    asl a
    sec
    sbc t0
    asl a                       ; (row - 2) * 30
    clc
    adc t1
    adc #3                      ; 4 + column - 1
    ora #$2000                  ; priority: above the photo (BG1 has none)
    bra @put2
@blank2:
    lda #0
@put2:
    sta f:MAPBUF,x
    inx
    inx
    inc t1
    lda t1
    cmp #32
    bne @c2
    iny
    cpy #32
    bne @r2
    jsr UploadMapNow
    lda #$03
    sta reg_tm
    rts

; the BG2 map shadow to VRAM now (forced blank)
UploadMapNow:
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    ldx #VRAM_BG2MAP
    stx VMADDL
    lda #$01
    sta DMAP1
    lda #$18
    sta BBAD1
    ldx #.loword(MAPBUF)
    stx A1T1L
    lda #^MAPBUF
    sta A1B1
    ldx #2048
    stx DAS1L
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    rts

InitState:
    lda #$FFFF
    sta hl_line
    sta music_cur
    sta amb_cur
    sta chapter_cur
    sta last_text
    sta pic_cur
    ldx #6
:   sta sil_key,x
    dex
    dex
    bpl :-
    stz reg_c0
    stz reg_c1
    lda #24
    sta reg_top
    lda #1
    sta speed
    lda #$E0
    sta reg_col_b
    lda #$40
    sta reg_col_g
    lda #$20
    sta reg_col_r
    ldx #0
:   lda f:SysPalette,x
    sta ui_pal,x
    inx
    inx
    cpx #32
    bne :-
    rts

; ---------------------------------------------------------------- frame
; End of a frame: effects, uploads, sound, wait for the NMI, read the pad.
WaitFrame:
    ldx #14                     ; t0-t7 survive a frame
:   lda t0,x
    pha
    dex
    dex
    bpl :-
    stz glyph_count
    stz work_count
    jsr Tick
    jsr PumpUploads
    jsr SndPump
    inc main_count
    lda #1
    sta frame_ready
:   wai
    lda frame_ready
    bne :-
    jsr ReadPad
    ldx #0
:   pla
    sta t0,x
    inx
    inx
    cpx #16
    bne :-
    rts

; A frame boundary inside long work (glyphs, page clears, compositing): like WaitFrame, but the presses of
; the frame are added to those the caller has not looked at yet.  Keeps every frame's work well under a frame,
; so the game takes the same frames on every core (no lag frames to drift by).
PacedWait:
    lda pad_new
    pha
    lda pad_rep
    pha
    jsr WaitFrame
    lda pad_new                 ; presses of this frame: kept for the next WaitFrame of the caller's loop
    ora pad_carry
    sta pad_carry
    pla
    sta pad_rep
    pla
    sta pad_new
    rts

; forget the presses made while the screen was being drawn (before a cursor or a wait mark is shown)
FlushPad:
    stz pad_carry
    stz pad_new
    stz pad_rep
    rts

; A = frames
WaitFrames:
    sta t7
:   lda t7
    beq :+
    pha
    jsr WaitFrame
    pla
    dec a
    sta t7
    bra :-
:   rts

; until every upload went out
WaitUploads:
    lda #600
    sta g_pad
:   lda text_dirty
    ora text_dirty+2
    ora photo_dirty
    ora photo_dirty+2
    ora pal_dirty
    ora tint_dirty
    ora map_dirty
    ora ui_dirty
    bne :+
    lda job_head
    cmp job_tail
    beq @done
:   jsr WaitFrame
    dec g_pad
    bne :--
@done:
    rts

; A = last line on which a main-thread DMA may start: wait (the NMI may come meanwhile) until the beam is
; on an earlier line, so the DMA cannot hold the next NMI past the V-blank.  Nothing to wait in forced blank.
VGuard:
    ldx blanked
    bne @r
    sta t6
@l:
    sep #$20
    .a8
    lda SLHV
    lda STAT78                  ; reset the OPVCT read order
    lda OPVCT
    xba
    lda OPVCT
    and #$01
    xba
    rep #$20
    .a16
    cmp t6
    bcs @l
@r:
    rts

; ---------------------------------------------------------------- input
ReadPad:
    sep #$20
    .a8
:   lda HVBJOY
    and #$01
    bne :-
    rep #$20
    .a16
    lda pad
    sta pad_prev
    lda JOY1L
    sta pad
    lda pad_prev
    eor #$FFFF
    and pad
    sta pad_new
    sta pad_rep
    lda pad
    and #PAD_DIRS
    beq @none
    sta t6
    lda pad_prev
    and #PAD_DIRS
    cmp t6
    bne @none
    inc rep_timer
    lda rep_timer
    cmp #18
    bcc @done
    lda #13
    sta rep_timer
    lda t6
    ora pad_rep
    sta pad_rep
    bra @done
@none:
    stz rep_timer
@done:
    lda pad_carry               ; presses made during paced work
    beq :+
    ora pad_new
    sta pad_new
    lda pad_carry
    ora pad_rep
    sta pad_rep
    stz pad_carry
:   rts

; ---------------------------------------------------------------- uploads
; Queue one job.  t0 dest, t1 type | bank << 8, t2 source, t3 length.
Enqueue:
    ldx job_tail
    cpx #JOB_MAX*8
    bcs @full
    lda t0
    sta jobs+0,x
    lda t1
    sta jobs+2,x
    lda t2
    sta jobs+4,x
    lda t3
    sta jobs+6,x
    txa
    clc
    adc #8
    sta job_tail
    sec
    lda t5
    sbc t3
    sta t5
    rts
@full:
    inc dma_deferred
    rts

; End of frame: palette, map, photo rows and text rows within the budget (t5).
PumpUploads:
    lda job_head
    cmp job_tail
    beq :+
    rts                         ; the NMI did not take everything yet
:   stz job_head
    stz job_tail
    lda #DMA_BUDGET
    sta t5
    lda ui_dirty
    beq :+
    stz ui_dirty
    stz t0
    lda #$0001
    sta t1
    lda #.loword(ui_pal)
    sta t2
    lda #32
    sta t3
    jsr Enqueue
:   lda pal_dirty
    beq :+
    stz pal_dirty
    lda #16
    sta t0
    lda pal_src+2
    xba
    and #$FF00
    ora #$0001
    sta t1
    lda pal_src
    sta t2
    lda #480
    sta t3
    jsr Enqueue
:   lda tint_dirty                  ; after the photo colours, which it overwrites in part
    beq @map
    stz tint_dirty
    lda #144
    sta t0
    lda tint_up+2
    xba
    and #$FF00
    ora #$0001
    sta t1
    lda tint_up
    sta t2
    lda #224
    sta t3
    jsr Enqueue
@map:
    lda map_dirty
    beq @photo
    stz map_dirty
    lda #VRAM_BG2MAP
    sta t0
    lda #$7E00
    sta t1
    lda #.loword(MAPBUF)
    sta t2
    lda #2048
    sta t3
    jsr Enqueue
@photo:
    lda photo_dirty
    ora photo_dirty+2
    beq @text
    lda photo_c1
    sec
    sbc photo_c0
    xba
    lsr a
    lsr a                       ; columns * 64
    sta t4
    cmp t5
    beq :+
    bcs @text
:   ldx #photo_dirty
    jsr LowestRow               ; A = row, cleared
    xba
    lsr a
    lsr a
    lsr a                       ; row * 32 tiles
    clc
    adc photo_c0
    asl a
    asl a
    asl a
    asl a
    asl a                       ; tile * 32 words
    sta t0
    asl a                       ; tile * 64 bytes
    sta t2
    lda #$7F00
    sta t1
    lda t4
    sta t3
    jsr Enqueue
    lda job_tail
    cmp #JOB_MAX*8
    bcc @photo
    rts
@text:
    lda text_dirty
    ora text_dirty+2
    beq @done
    lda t5
    cmp #BMP_ROW
    bcc @done
    ldx #text_dirty
    jsr LowestRow
    sta t0
    asl a
    asl a
    asl a
    asl a
    sec
    sbc t0
    asl a
    asl a
    asl a
    asl a
    asl a                       ; row * 480
    sta t2
    lsr a
    clc
    adc #VRAM_TEXT
    sta t0
    lda t2
    clc
    adc #.loword(BMP)
    sta t2
    lda #$7E00
    sta t1
    lda #BMP_ROW
    sta t3
    jsr Enqueue
    lda job_tail
    cmp #JOB_MAX*8
    bcc @text
@done:
    rts

; X = address of a 32-bit row mask (rows 0-23) -> A = lowest set row, its bit cleared
LowestRow:
    lda 0,x
    bne @lo
    lda 2,x
    ldy #16
    bra @find
@lo:
    ldy #0
@find:
    sta t6
    lda #1
    sta t7
:   lda t6
    and t7
    bne :+
    asl t7
    iny
    bra :-
:   lda t7
    eor #$FFFF
    cpy #16
    bcs @hi
    and 0,x
    sta 0,x
    tya
    rts
@hi:
    and 2,x
    sta 2,x
    tya
    rts

; A = first row, X = last row (0-23) -> mark those text rows dirty
MarkTextRows:
    stx t6
    tax
@l:
    txa
    cmp #16
    bcs @h
    asl a
    tay
    lda BitTable,y
    ora text_dirty
    sta text_dirty
    bra @n
@h:
    sec
    sbc #16
    asl a
    tay
    lda BitTable,y
    ora text_dirty+2
    sta text_dirty+2
@n:
    cpx t6
    beq @d
    inx
    cpx #24
    bcc @l
@d:
    rts

BitTable:
    .word $0001, $0002, $0004, $0008, $0010, $0020, $0040, $0080
    .word $0100, $0200, $0400, $0800, $1000, $2000, $4000, $8000

ZeroWord: .word 0
FFWord: .word $FFFF

; colours 0-15: BG2 palette 0 (0 backdrop black, 1 text, 2 shadow, 3 grey), palette 1 (5 highlighted
; text, 6 shadow, 7 grey as in palette 0), 8/9 white silhouette body/rim, 10/11 red, 12/13 blue (the bodies
; are drawn with these only where the photo has no translucent-figure colours)
SysPalette:
    .word $0000, $7BDE, $0C42, $4A52
    .word $0000, $3F7F, $0842, $4A52
    .word $6B18, $6F7B, $0C54, $211F
    .word $5505, $558B, $0000, $0000

.include "src/yonaki/text.inc"
.include "src/yonaki/pic.inc"
.include "src/yonaki/vm.inc"
.include "src/yonaki/ui.inc"
.include "src/yonaki/save.inc"
.include "src/yonaki/audio.inc"
.include "data.inc"
