; 潮鳴りの密室 -- SFC command-selection adventure (65816, ca65)
;
; Mode 3: BG1 = 8bpp picture 256x128 (512 tiles, one LoROM bank per picture), BG2 = 4bpp text layer
; (header 2 tile rows + bottom panel 10 tile rows drawn by the CPU into a WRAM bitmap and uploaded by
; DMA, a dirty tile row at a time).  No OBJ, no BG3/4.  Pictures change by fading CGRAM 16-255 to
; black, streaming the tiles in 4 KiB per V-blank and fading in again: no forced blank after boot.
;
; Frame protocol: the main loop reads the pad, updates the game, queues DMA jobs (PumpUploads keeps
; them under DMA_BUDGET bytes) and sets frame_ready; the NMI uploads only a prepared frame and counts
; the others (lag_count).  The V counter at the end of every NMI is kept (nmi_end_line_max) and NMIs
; that end outside the V-blank are counted (vblank_overrun_count).
;
; Conventions: native mode, X/Y always 16 bit, A 16 bit except around 8-bit register and byte work,
; DB = $00, D = $0000.  The bitmap and the palette buffer live at $7E:2000+ (long addressing).

.setcpu "65816"
.smart -
.include "build/adv/const.inc"

; ---------------------------------------------------------------- hardware
INIDISP = $2100
OBJSEL  = $2101
OAMADDL = $2102
OAMDATA = $2104
BGMODE  = $2105
MOSAIC  = $2106
BG1SC   = $2107
BG2SC   = $2108
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
NMITIMEN = $4200
WRDIVL  = $4204
WRDIVB  = $4206
MDMAEN  = $420B
HDMAEN  = $420C
MEMSEL  = $420D
RDNMI   = $4210
HVBJOY  = $4212
RDDIVL  = $4214
RDMPYL  = $4216
JOY1L   = $4218
DMAP0   = $4300
BBAD0   = $4301
A1T0L   = $4302
A1B0    = $4304
DAS0L   = $4305

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
PAD_DIRS   = $0F30              ; directions and L/R repeat while held

; VRAM (word addresses)
VRAM_BG1TILES = $0000           ; 512 x 64 bytes
VRAM_BG1BLANK = $4000           ; tile 512, zero
VRAM_BG1MAP   = $4400
VRAM_BG2MAP   = $4800
VRAM_BG2TILES = $5000           ; tile 0 transparent, tiles 1-384 = the bitmap rows
VRAM_TEXT     = VRAM_BG2TILES + 16

BMP       = $7E2000             ; 12 tile rows x 32 tiles x 32 bytes
BMP_ROW   = 1024
BMP_ROWS  = 12
BOOT_FRAMES = 96                ; power-on to the first frame of the game (the driver upload fits)
DMA_BUDGET = 4096               ; bytes per V-blank (measured end line: see nmi_end_line_max)
JOB_MAX   = 16
LIST_MAX  = 48

; text layout (bitmap coordinates: x 0-255, y 0-95; y 16-95 = screen 144-223)
MSG_X0    = 12
MSG_Y0    = 21
MSG_PITCH = 17
MSG_RIGHT = 228
PAGE_X    = 234
PAGE_Y    = 76
ROW_Y0    = 22                  ; command / list rows (screen 150, 164, ...)
ROW_PITCH = 14
LIST_ROWS = 5
CMD_CURSOR_X = 8
CMD_LABEL_X  = 20
DIVIDER_X    = 76
LST_CURSOR_X = 81
LST_LABEL_X  = 94
LST_RIGHT    = 228
MARK_X       = 230

; colours (CGRAM 0-15)
C_BG = 1
C_WHITE = 2
C_FRAME = 3
C_SHADE = 4
C_GRAY = 5
C_YELLOW = 6
C_CYAN = 7

; modes
M_CMD   = 0
M_LIST  = 1
M_MSG   = 2
M_FADE  = 3
M_END   = 4
M_OPEN  = 5

; list kinds
LK_LOOK  = 0
LK_TOPIC = 1
LK_SHOW  = 2
LK_MOVE  = 3
LK_NOTE  = 4
LK_ITEMS = 5
LK_TESTI = 6
LK_DQCHOICE = 7
LK_DQCLUE = 8
LK_TITLE = 9

; where to go after a message / script / fade
RET_CMD     = 0
RET_LIST    = 1
RET_TITLE   = 2
RET_DQSTART = 3
RET_DQLIST  = 4
RET_DQNEXT  = 5
RET_VM      = 6

; ---------------------------------------------------------------- variables
.segment "ZEROPAGE"
p0:       .res 4               ; long pointer
p1:       .res 4
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
g_c:      .res 2
g_w:      .res 2
g_addr:   .res 2
g_shift:  .res 2
g_yin:    .res 2
g_m0:     .res 1
g_m1:     .res 1
g_m2:     .res 1
g_pad:    .res 1
gbuf:     .res 24
msg_ptr:  .res 4               ; long pointer into the text being typed
g_drawn:  .res 2               ; DrawGlyph got past its checks (the glyph is in the bitmap)

.segment "BSS"
; statistics for the tests and the host monitor
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
text_clip:        .res 2       ; glyphs that crossed their box (must stay 0)
inidisp:          .res 2
; input
pad:      .res 2
pad_prev: .res 2
pad_new:  .res 2
pad_rep:  .res 2
rep_timer: .res 2
; DMA jobs (8 bytes: dest, type (0 VRAM, 1 CGRAM), bank, source, length)
job_head: .res 2
job_tail: .res 2
jobs:     .res JOB_MAX*8
dirty_rows: .res 2
; game
mode:       .res 2
scene:      .res 2
person:     .res 2             ; person index + 1 of the scene (0 none)
image_cur:  .res 2
flags:      .res 128
actions:    .res 2
wrong_count: .res 2
sound_on:   .res 2
cmd_sel:    .res 2
cmd_active: .res 2
note_sel:   .res 2
list_kind:  .res 2
list_count: .res 2
list_sel:   .res 2
list_top:   .res 2
list_label: .res LIST_MAX*2
list_arg:   .res LIST_MAX*2
list_color: .res LIST_MAX*2
list_base:  .res 2             ; item list address of LOOK / TOPIC
clip_right: .res 2
; message
msg_x:      .res 2
msg_y:      .res 2
msg_color:  .res 2
msg_state:  .res 2             ; 0 typing, 1 page wait, 2 end wait
msg_timer:  .res 2
msg_fast:   .res 2
msg_blink:  .res 2
msg_count:  .res 2             ; messages opened
msg_text:   .res 2             ; text id of the last message opened
; script VM
vm_pc:      .res 2
vm_active:  .res 2
vm_return:  .res 2
vm_sp:      .res 2
vm_stack:   .res 16
; fade / picture stream
fade_state: .res 2             ; 0 idle, 1 out, 2 load, 3 in
fade_level: .res 2
fade_scene: .res 2             ; $FFFF = keep the scene
fade_image: .res 2
fade_return: .res 2
pal_level:  .res 2
pal_dirty:  .res 2
img_left:   .res 2
img_pos:    .res 2
img_bank:   .res 2
; portrait overlay
por_shown:  .res 2             ; portrait index + 1 on screen
por_want:   .res 2
por_row:    .res 2
por_rows:   .res 2             ; rows still to upload
por_src:    .res 2
por_bank:   .res 2
por_on:     .res 2             ; the stream uploads the portrait (1) or the picture (0)
por_index:  .res 2
; deduction
dq_index:   .res 2
dq_entry:   .res 2
; title / save
save_status: .res 2            ; 0 none, 1 broken, 2 valid
save_slot:  .res 2
save_seq:   .res 2
save_ok:    .res 2             ; last write verified
load_count: .res 2
saves_done: .res 2
ending_seen: .res 2
; header pieces
hp_kind:    .res 16            ; up to 8 header pieces
hp_val:     .res 16
hp_val2:    .res 16
hp_count:   .res 2
hdr_total:  .res 2
hdr_left:   .res 2
nw_digit:   .res 2
num_digits: .res 12
num_left:   .res 2
nav_old_sel: .res 2
nav_old_top: .res 2
; sound
sfx_last:   .res 2
sfx_count:  .res 2
spc_toggle: .res 2
ambient_cur: .res 2
amb_want:   .res 2
snd_queue:  .res 16
snd_count:  .res 2
snd_sent:   .res 2
snd_unmuted: .res 2             ; master volume state sent to the driver (1 = on)
music_cur:  .res 2              ; song asked of the driver ($FFFF none / fading)
music_lock: .res 2              ; 1: a script chose the song (scene changes keep it)
duck_cur:   .res 2              ; 1: the driver was told to duck the music (a message is open)
; opening and title (src/adv/opening.inc)
op_state:   .res 2
op_step:    .res 2              ; next OpTimeline entry
op_arg:     .res 2              ; argument of the entry being done
op_frames:  .res 2
op_beat:    .res 2              ; beats of the opening song
op_song_seen: .res 2            ; the driver reported the opening song
op_blink:   .res 2
op_idle:    .res 2
op_ui_level: .res 2             ; text-layer colours 0-16
op_ui_target: .res 2
op_ui_src:  .res 2              ; OpenPalette or UiPalette
op_pic_state: .res 2
op_pic_next: .res 2
ui_pal:     .res 32
ui_dirty:   .res 2
; lip-sync (src/adv/mouth.inc)
mouth_actor: .res 2             ; speaker id of the page being typed (0 none, 1.. person, SPEAKER_ME)
mouth_want:  .res 2             ; wanted mouth: 0 closed, 1 half open, 2 open
mouth_shown: .res 2             ; mouth in VRAM (0 also when there is no portrait)
mouth_timer: .res 2             ; position in MouthSeq
mouth_pause: .res 2             ; frames to stay closed after punctuation
mouth_talk:  .res 2             ; 1 in a frame where the shown person speaks
mouth_uploads: .res 2           ; mouth tile uploads queued
mouth_other: .res 2             ; frames where another person spoke in front of a portrait
; speech blips (src/adv/voice.inc)
voice_glyphs: .res 2            ; voiced glyphs of a spoken body drawn in this frame
voice_pause:  .res 2            ; frames to stay silent after punctuation
voice_wait:   .res 2            ; frames until the next blip may sound
voice_phrase: .res 2            ; 1: the next blip starts a phrase
voice_mail:   .res 2            ; last blip byte sent (voice | $80 phrase)
voice_seq:    .res 2            ; port 3 value of the last blip
voice_sent:   .res 2            ; blips sent

.segment "HIBSS"
bmp:      .res BMP_ROW*BMP_ROWS
bmp_pad:  .res 128             ; glyph rows near the end may touch (unchanged) bytes past the bitmap
pal_buf:  .res 480
oam_buf:  .res 544
save_buf: .res 256

.assert bmp = BMP, error, "bitmap must start at $7E2000"

; ---------------------------------------------------------------- header
.segment "HEADER"
    .byte "SHIONARI NO MISSITSU "      ; 21 bytes
    .byte $20                          ; LoROM, SlowROM
    .byte $02                          ; ROM + RAM + battery
    .byte $09                          ; 512 KiB
    .byte $03                          ; 8 KiB SRAM
    .byte $00                          ; Japan
    .byte $00                          ; licensee
    .byte $00                          ; version
    .word $FFFF, $0000                 ; checksum complement / checksum (tools/adv/romfix.py)
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
    stz MEMSEL                  ; SlowROM timing (header $20)
    ldx #$2101
@clr:
    stz $00,x
    inx
    cpx #$2134
    bne @clr
    lda #$80
    sta INIDISP
    ; WRAM: $0000-$1DFF and $7E2000-$7E7FFF
    rep #$20
    .a16
    ldx #$0000
:   stz $0000,x
    inx
    inx
    cpx #$1E00
    bne :-
    ldx #$0000
    lda #$0000
:   sta f:$7E2000,x
    inx
    inx
    cpx #$6000
    bne :-
    jsr ClearVram
    ; the sound driver (about 65 frames on the IPL): NMI counts the frames meanwhile, and the boot
    ; always takes BOOT_FRAMES whatever the upload took (the same frame for the first input on every core)
    lda #$80
    sta inidisp
    sep #$20
    .a8
    lda #$80
    sta NMITIMEN                ; NMI only (the handler sees no frame_ready: forced blank stays)
    rep #$20
    .a16
    jsr InitSpc
:   lda nmi_count
    cmp #BOOT_FRAMES
    bcc :-
    sep #$20
    .a8
    stz NMITIMEN
    rep #$20
    .a16
    stz nmi_count
    stz lag_count
    stz nmi_end_line_max
    stz vblank_overrun_count
    jsr InitPpu
    lda #1
    sta sound_on
    lda #252
    sta clip_right
    lda #$80
    sta inidisp
    ; the title picture and the text layer, committed in forced blank
    lda #IMAGE_TITLE
    jsr LoadPictureNow
    ; everything black: the opening fades the picture and the text in
    sep #$20
    .a8
    stz CGADD
    ldx #512
:   stz CGDATA
    dex
    bne :-
    rep #$20
    .a16
    stz fade_level
    stz pal_level
    stz op_ui_level
    jsr OpeningStart
    jsr FlushNow
    ; two frames with the display on at brightness 0 before the NMI starts
    sep #$20
    .a8
    stz INIDISP
    ldy #2
@vb:
:   lda HVBJOY
    bmi :-
:   lda HVBJOY
    bpl :-
    dey
    bne @vb
:   lda HVBJOY
    bmi :-
    lda #$81
    sta NMITIMEN                ; NMI + auto joypad read
    rep #$20
    .a16
    lda #$0F
    sta inidisp
MainLoop:
    rep #$30
    .a16
    .i16
    jsr ReadPad
    jsr Update
    jsr MouthUpdate
    jsr VoiceUpdate
    jsr DuckUpdate
    jsr PumpUploads
    jsr SndPump
    inc main_count
    lda #1
    sta frame_ready
@wait:
    wai
    lda frame_ready
    bne @wait
    bra MainLoop

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
    lda #$01                    ; two registers, $2118/$2119
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
    stz DMAP0                   ; one register
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
    cmp #225
    bcs :+
    inc vblank_overrun_count
    bra :++
:   cmp nmi_end_line_max
    bcc :+
    sta nmi_end_line_max
:   pld
    plb
    ply
    plx
    pla
    rti

; ---------------------------------------------------------------- init
.a16
.i16
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
    ; OAM: every object below the picture (y 240), small, name 0 -- and OBJ is not on the main screen
    rep #$20
    .a16
    ldx #0
:   lda #$F000                  ; x 0, y 240
    sta f:oam_buf,x
    lda #$0000
    sta f:oam_buf+2,x
    inx
    inx
    inx
    inx
    cpx #512
    bne :-
:   sta f:oam_buf,x
    inx
    inx
    cpx #544
    bne :-
    sep #$20
    .a8
    stz OAMADDL
    stz OAMADDL+1
    stz DMAP0
    lda #$04
    sta BBAD0
    ldx #.loword(oam_buf)
    stx A1T0L
    lda #^oam_buf
    sta A1B0
    ldx #544
    stx DAS0L
    lda #$01
    sta MDMAEN
    rep #$20
    .a16
    rts

InitPpu:
    sep #$20
    .a8
    lda #$03
    sta BGMODE
    lda #(VRAM_BG1MAP >> 8) & $FC
    sta BG1SC
    lda #(VRAM_BG2MAP >> 8) & $FC
    sta BG2SC
    lda #((VRAM_BG2TILES >> 12) << 4) | (VRAM_BG1TILES >> 12)
    sta BG12NBA
    stz OBJSEL
    stz MOSAIC
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF                    ; V scroll -1: tile row 0 on the first visible line
    sta BG1VOFS
    lda #$03
    sta BG1VOFS
    lda #$FF
    sta BG2VOFS
    lda #$03
    sta BG2VOFS
    lda #$03
    sta TM                      ; BG1 + BG2
    stz TS
    stz TMW
    stz W12SEL
    stz CGWSEL
    stz CGADSUB
    lda #$E0
    sta COLDATA
    stz SETINI
    ; UI colours 0-15
    stz CGADD
    ldx #0
:   lda f:UiPalette,x
    sta CGDATA
    inx
    cpx #32
    bne :-
    ; BG1 map: rows 2-17 = tiles 0-511, others the blank tile 512
    lda #$80
    sta VMAIN
    rep #$20
    .a16
    lda #VRAM_BG1MAP
    sta VMADDL
    ldy #0                      ; row
@r1:
    ldx #0                      ; column
@c1:
    cpy #2
    bcc @blank1
    cpy #18
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
    lda #512
@put1:
    sta VMDATAL
    inx
    cpx #32
    bne @c1
    iny
    cpy #32
    bne @r1
    ; BG2 map: rows 0-1 = tiles 1-64, rows 18-27 = tiles 65-384, others tile 0
    lda #VRAM_BG2MAP
    sta VMADDL
    ldy #0
@r2:
    ldx #0
@c2:
    cpy #2
    bcc @top2
    cpy #18
    bcc @blank2
    cpy #28
    bcs @blank2
    tya
    sec
    sbc #16                     ; bitmap row 2..11
    bra @row2
@top2:
    tya
@row2:
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t0
    txa
    clc
    adc t0
    inc a
    bra @put2
@blank2:
    lda #0
@put2:
    sta VMDATAL
    inx
    cpx #32
    bne @c2
    iny
    cpy #32
    bne @r2
    rts

; Picture + palette in forced blank (boot only).  A = image index.
LoadPictureNow:
    sta image_cur
    asl a
    asl a
    tax
    lda ImageTable,x
    sta t0                      ; bank
    lda ImageTable+2,x
    sta t1                      ; palette
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    ldx #VRAM_BG1TILES
    stx VMADDL
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    ldx #$8000
    stx A1T0L
    lda t0
    sta A1B0
    ldx #$8000
    stx DAS0L
    lda #$01
    sta MDMAEN
    lda #16
    sta CGADD
    stz DMAP0
    lda #$22
    sta BBAD0
    ldx t1
    stx A1T0L
    stz A1B0
    ldx #480
    stx DAS0L
    lda #$01
    sta MDMAEN
    rep #$20
    .a16
    lda #16
    sta pal_level
    rts

; In forced blank: the whole text bitmap, and drop the queued jobs and dirty rows.
FlushNow:
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    ldx #VRAM_TEXT
    stx VMADDL
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    ldx #.loword(BMP)
    stx A1T0L
    lda #^BMP
    sta A1B0
    ldx #BMP_ROW*BMP_ROWS
    stx DAS0L
    lda #$01
    sta MDMAEN
    rep #$20
    .a16
    stz dirty_rows
    stz job_head
    stz job_tail
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
    ; repeat: directions / L / R held -> again after 16 frames, then every 5
    lda pad
    and #PAD_DIRS
    beq @none
    sta t7
    lda pad_prev
    and #PAD_DIRS
    cmp t7
    bne @none                   ; changed: the new press is already in pad_new
    inc rep_timer
    lda rep_timer
    cmp #16
    bcc @done
    lda #11
    sta rep_timer
    lda t7
    ora pad_rep
    sta pad_rep
    rts
@none:
    stz rep_timer
@done:
    rts

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
@full:
    rts

; End of frame: mouth tiles, palette, picture stream, portrait rows and dirty text rows within the budget.
; The mouth comes first: the NMI always takes the first job, so a closing mouth is never deferred.
PumpUploads:
    lda job_head
    cmp job_tail
    beq :+
    rts                         ; the NMI did not take everything yet
:   stz job_head
    stz job_tail
    lda #DMA_BUDGET
    sta t5
    jsr MouthPump
    ; palette 16-255
    lda pal_dirty
    beq @img
    stz pal_dirty
    lda #16
    sta t0
    lda #$7E01
    sta t1
    lda #.loword(pal_buf)
    sta t2
    lda #480
    sta t3
    jsr Enqueue
    lda t5
    sec
    sbc #480
    sta t5
@img:
    ; text-layer colours 0-15 (the opening's fades, the game's colours back)
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
    lda t5
    sec
    sbc #32
    sta t5
:   lda img_left
    beq @por
    lda t5
    and #$FFC0                  ; whole tiles, within what is left of the budget
    cmp img_left
    bcc :+
    lda img_left
:   sta t3
    beq @por
    lda img_pos
    lsr a
    sta t0                      ; VRAM word address (BG1 tiles at 0)
    lda img_bank
    xba
    and #$FF00
    sta t1
    lda img_pos
    clc
    adc #$8000
    sta t2
    jsr Enqueue
    lda img_pos
    clc
    adc t3
    sta img_pos
    lda img_left
    sec
    sbc t3
    sta img_left
    lda t5
    sec
    sbc t3
    sta t5
@por:
    lda por_rows
    beq @text
    lda t5
    cmp #9*64
    bcc @text
    jsr PortraitRow
    bra @por
@text:
    lda dirty_rows
    beq @done
    lda t5
    cmp #BMP_ROW
    bcc @done
    ; lowest dirty row
    ldx #0
    lda dirty_rows
:   lsr a
    bcs :+
    inx
    bra :-
:   txa
    asl a
    tay
    lda BitTable,y
    eor #$FFFF
    and dirty_rows
    sta dirty_rows
    txa
    xba                         ; row * 256
    sta t0
    asl a
    asl a                       ; row * 1024
    clc
    adc #.loword(BMP)
    sta t2
    lda t0
    asl a                       ; row * 512 words
    clc
    adc #VRAM_TEXT
    sta t0
    lda #$7E00
    sta t1
    lda #BMP_ROW
    sta t3
    jsr Enqueue
    lda t5
    sec
    sbc #BMP_ROW
    sta t5
    bra @text
@done:
    rts

; one portrait row (picture tiles or portrait tiles) into the queue; t5 = budget left
PortraitRow:
    lda por_index
    asl a
    asl a
    sta t6
    asl a
    clc
    adc t6
    tax                         ; index * 12
    lda PortraitTable+2,x       ; y tile
    clc
    adc por_row
    asl a
    asl a
    asl a
    asl a
    asl a                       ; * 32 tiles per row
    clc
    adc PortraitTable+0,x       ; + x tile
    sta t6                      ; tile index
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t0                      ; VRAM word = tile * 32
    lda PortraitTable+4,x       ; width in tiles
    xba
    lsr a
    lsr a                       ; * 64 bytes
    sta t3
    lda por_on
    beq @pic
    lda PortraitTable+10,x
    xba
    and #$FF00
    sta t1
    lda por_row
    sta t4
    lda PortraitTable+8,x
@mul:
    ldy t4
    beq :+
    clc
    adc t3
    dec t4
    bra @mul
:   sta t2
    bra @go
@pic:
    lda image_cur
    asl a
    asl a
    tay
    lda ImageTable,y
    xba
    and #$FF00
    sta t1
    lda t6
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; tile * 64
    clc
    adc #$8000
    sta t2
@go:
    jsr Enqueue
    lda t5
    sec
    sbc t3
    sta t5
    inc por_row
    dec por_rows
    rts

BitTable:
    .word $0001, $0002, $0004, $0008, $0010, $0020, $0040, $0080
    .word $0100, $0200, $0400, $0800, $1000, $2000, $4000, $8000

ZeroWord: .word 0

UiPalette:
    ;      0 black   1 panel   2 text    3 frame   4 shade   5 gray    6 yellow  7 cyan
    .word $0000,    $2CA4,    $6FBD,    $6EF6,    $4148,    $5230,    $335F,    $7750
    .word $0000,    $0000,    $0000,    $0000,    $0000,    $0000,    $0000,    $0000

.include "src/adv/text.inc"
.include "src/adv/ui.inc"
.include "src/adv/mouth.inc"
.include "src/adv/game.inc"
.include "src/adv/vm.inc"
.include "src/adv/save.inc"
.include "src/adv/audio.inc"
.include "src/adv/voice.inc"
.include "src/adv/opening.inc"
.include "build/adv/data.inc"
