; ---------------------------------------------------------------- battery SRAM ($70:0000, 8 KiB)
; Journal: global + three bookmarks ($0000-$03FF, mirrored at $0400-$07FF).
; Read marks: a build header at $0800 and two bitmaps at $0808 and $1400.
; See docs/yonaki/ENGINE.md for the record layout and recovery rules.
.a16
.i16

SRAM = $700000
SAVE_MIRROR = $0400
SAVE_VERSION = 2
SAVE_MAGIC = $4E59                 ; "YN", low byte is the commit marker
SAVE_GENERATION = 48
SAVE_CRC = 148
SAVE_SIZE = SAVE_CRC + 2
GLOBAL_SPEED = 10
GLOBAL_ENDINGS = 12
GLOBAL_FLAGS = 16
GLOBAL_NAMES = 20

READ_HEADER = $700800
READ_MAGIC = $5259                 ; "YR", low byte is the commit marker
READ_PRIMARY = READ_HEADER + 8
READ_MIRROR = $701400
READ_BYTES = $0BF0
.assert TEXT_COUNT <= READ_BYTES * 8, error, "Read bitmaps are too small"
.assert READ_MIRROR + READ_BYTES <= $701FF0, error, "Read marks overlap the debug mailbox"

; p1 = record base in SRAM or WRAM -> A = CRC-16/CCITT-FALSE of bytes 2..147.
SaveCRC:
    lda #$FFFF
    sta t0
    ldy #2
@byte:
    lda [p1],y
    xba
    eor t0
    and #$FF00
    xba
    asl a
    tax
    lda t0
    xba
    and #$FF00
    eor CRC16Table,x
    sta t0
    iny
    cpy #SAVE_CRC
    bne @byte
    rts

CRC16Table:
.repeat 256, Byte
    CrcEntry .set Byte << 8
    .repeat 8
        .if CrcEntry & $8000
            CrcEntry .set ((CrcEntry << 1) ^ $1021) & $FFFF
        .else
            CrcEntry .set (CrcEntry << 1) & $FFFF
        .endif
    .endrepeat
    .word CrcEntry
.endrepeat

; A = record number (0 global, 1..3 bookmarks).
; p1 = newest valid copy, A = 1. If both are invalid, p1 = primary, A = 0.
FindRecord:
    sta record_id
    xba
    sta p1
    lda #^SRAM
    sta p1+2
    stz record_generation
    jsr CheckRecord
    sta primary_valid
    beq @mirror
    ldy #SAVE_GENERATION
    lda [p1],y
    sta record_generation
@mirror:
    lda p1
    eor #SAVE_MIRROR
    sta p1
    jsr CheckRecord
    beq @primary
    ldy #SAVE_GENERATION
    lda [p1],y
    ldx primary_valid
    beq @use_mirror
    sec
    sbc record_generation
    beq @primary                 ; tie: prefer the primary
    bmi @primary                 ; compare modulo 65536, including rollover
    lda [p1],y
@use_mirror:
    sta record_generation
    lda #1
    rts
@primary:
    lda p1
    eor #SAVE_MIRROR
    sta p1
    lda primary_valid
    rts

CheckRecord:
    lda [p1]
    cmp #SAVE_MAGIC
    bne @bad
    ldy #2
    lda [p1],y
    cmp record_id
    bne @bad
    ldy #4
    lda [p1],y
    cmp #SAVE_VERSION
    bne @bad
    ldy #6
    lda [p1],y
    cmp #BUILD_ID_LO
    bne @bad
    ldy #8
    lda [p1],y
    cmp #BUILD_ID_HI
    bne @bad
    jsr SaveCRC                 ; Y = SAVE_CRC
    cmp [p1],y
    bne @bad
    lda record_id
    bne CheckBookmark
    ldy #GLOBAL_SPEED
    lda [p1],y
    cmp #4
    bcs @bad
    lda #1
    rts
@bad:
    lda #0
    rts

CheckBookmark:
    ldy #10
    lda [p1],y
    cmp #1
    bne @choice
    ldy #12
    lda [p1],y
    cmp #TEXT_COUNT
    bcs @bad
    ldy #14
    lda [p1],y
    cmp #$FFFF
    bne @bad
    bra @scene
@choice:
    cmp #2
    bne @bad
    ldy #12
    lda [p1],y
    cmp #CHOICE_COUNT
    bcs @bad
    ldy #14
    lda [p1],y
    cmp #$FFFF
    beq @scene
    cmp #TEXT_COUNT
    bcs @bad
@scene:
    ldy #16
    lda [p1],y
    cmp #PIC_COUNT
    bcs @bad
    ldy #18
    lda [p1],y
    cmp #$FFFF
    beq :+
    cmp #SONG_COUNT
    bcs @bad
:   ldy #BOOKMARK_CHAPTER
    lda [p1],y
    cmp #$FFFF
    beq :+
    cmp #CHAPTER_COUNT
    bcs @bad
:   ldy #22
    lda [p1],y
    cmp #2
    bcs @bad
    ldy #24
    lda [p1],y
    cmp #2
    bcs @bad
    ldy #26
    lda [p1],y
    cmp #$FFFF
    beq @sil
    cmp #AMB_COUNT
    bcc @sil
@bad:
    lda #0
    rts
@sil:
    ldy #32
@slot:
    lda [p1],y
    and #$00FF
    cmp #$FF
    beq @next
    cmp #3
    bcc @key_ok
    cmp #$80                    ; explicit x position
    bcc @bad
    cmp #$A0
    bcs @bad
@key_ok:
    lda [p1],y
    xba
    and #$00FF
    cmp #SIL_COUNT
    bcs @bad
    iny
    iny
    lda [p1],y
    and #$00FF
    cmp #32
    bcs @bad
    lda [p1],y
    xba
    and #$00FF
    cmp #3
    bcs @bad
    dey
    dey
@next:
    iny
    iny
    iny
    iny
    cpy #48
    bne @slot
    lda #1
    rts

; A = record number. Select the write target and prepare the header in save_buf.
BeginRecord:
    jsr FindRecord
    beq @init
    lda p1
    eor #SAVE_MIRROR
    sta p1
@init:
    ldx #SAVE_SIZE-2
    lda #0
:   sta save_buf,x
    dex
    dex
    bpl :-
    lda #SAVE_MAGIC
    sta save_buf
    lda record_id
    sta save_buf+2
    lda #SAVE_VERSION
    sta save_buf+4
    lda #BUILD_ID_LO
    sta save_buf+6
    lda #BUILD_ID_HI
    sta save_buf+8
    lda record_generation
    inc a
    sta save_buf+SAVE_GENERATION
    rts

; Commit only after the payload and its CRC reach SRAM. Each marker store is a single byte.
CommitRecord:
    lda p1
    pha
    lda #.loword(save_buf)
    sta p1
    stz p1+2
    jsr SaveCRC
    sta save_buf+SAVE_CRC
    pla
    sta p1
    lda #^SRAM
    sta p1+2
    sep #$20
    .a8
    lda #0
    sta [p1]
    ldy #1
    lda save_buf+1
    sta [p1],y
    rep #$20
    .a16
    ldy #2
:   tyx
    lda save_buf,x
    sta [p1],y
    iny
    iny
    cpy #SAVE_SIZE
    bne :-
    sep #$20
    .a8
    lda save_buf
    sta [p1]
    rep #$20
    .a16
    jsr CheckRecord
    bne @done
    sep #$20
    .a8
    sta [p1]                    ; validation failed, leave the previous copy selectable
    rep #$20
    .a16
    lda #0
@done:
    rts

; Populate the same buffer from the selected, already validated copy.
ReadRecord:
    ldy #0
:   lda [p1],y
    tyx
    sta save_buf,x
    iny
    iny
    cpy #SAVE_SIZE
    bne :-
    lda #1
    rts

SramBoot:
    lda #0
    jsr FindRecord
    beq @defaults
    jsr ReadRecord
    lda save_buf+GLOBAL_SPEED
    sta speed
    lda save_buf+GLOBAL_ENDINGS
    sta gendings
    lda save_buf+GLOBAL_ENDINGS+2
    sta gendings+2
    lda save_buf+GLOBAL_FLAGS
    sta gflags
    lda save_buf+GLOBAL_FLAGS+2
    sta gflags+2
    ldx #0
:   lda save_buf+GLOBAL_NAMES,x
    sta names,x
    inx
    inx
    cpx #20
    bne :-
    jsr CheckNames
    bra ReadBoot
@defaults:
    lda #1
    sta sram_resets
    stz gendings
    stz gendings+2
    stz gflags
    stz gflags+2
    lda #1
    sta speed
    jsr DefaultNames
    jsr SaveGlobal

ReadBoot:
    lda f:READ_HEADER
    cmp #READ_MAGIC
    bne @reset
    lda f:READ_HEADER+2
    cmp #SAVE_VERSION
    bne @reset
    lda f:READ_HEADER+4
    cmp #BUILD_ID_LO
    bne @reset
    lda f:READ_HEADER+6
    cmp #BUILD_ID_HI
    bne @reset
    rts
@reset:
    lda sram_resets
    ora #2
    sta sram_resets
    sep #$20
    .a8
    lda #0
    sta f:READ_HEADER
    lda #>READ_MAGIC
    sta f:READ_HEADER+1
    rep #$20
    .a16
    ldx #0
    lda #0
:   sta f:READ_PRIMARY,x
    sta f:READ_MIRROR,x
    inx
    inx
    cpx #READ_BYTES
    bne :-
    lda #SAVE_VERSION
    sta f:READ_HEADER+2
    lda #BUILD_ID_LO
    sta f:READ_HEADER+4
    lda #BUILD_ID_HI
    sta f:READ_HEADER+6
    sep #$20
    .a8
    lda #<READ_MAGIC
    sta f:READ_HEADER
    rep #$20
    .a16
    rts

SaveGlobal:
    lda #0
    jsr BeginRecord
    lda speed
    sta save_buf+GLOBAL_SPEED
    lda gendings
    sta save_buf+GLOBAL_ENDINGS
    lda gendings+2
    sta save_buf+GLOBAL_ENDINGS+2
    lda gflags
    sta save_buf+GLOBAL_FLAGS
    lda gflags+2
    sta save_buf+GLOBAL_FLAGS+2
    ldx #0
:   lda names,x
    sta save_buf+GLOBAL_NAMES,x
    inx
    inx
    cpx #20
    bne :-
    jmp CommitRecord

; names: each name 1..NAME_MAX glyphs that exist, else its default
CheckNames:
    ldx #0
    jsr @one
    ldx #10
@one:
    lda names,x
    beq @bad
    cmp #NAME_MAX+1
    bcs @bad
    sta t0
    phx
:   inx
    inx
    lda names,x
    cmp #GLYPH_COUNT
    bcs @badp
    dec t0
    bne :-
    plx
    rts
@badp:
    plx
@bad:
    ldy #10
:   lda NameDefault,x
    sta names,x
    inx
    inx
    dey
    dey
    bne :-
    rts

DefaultNames:
    ldx #18
:   lda NameDefault,x
    sta names,x
    dex
    dex
    bpl :-
    rts

; A = ending index: seen, its global flags set, saved
RecordEnding:
    pha
    ldx #gendings
    jsr BitSet
    pla
    asl a
    asl a
    asl a
    tax
    lda EndingTable+4,x
    ora gflags
    sta gflags
    lda EndingTable+6,x
    ora gflags+2
    sta gflags+2
    jmp SaveGlobal

; ---------------------------------------------------------------- read marks
; A = text id -> X = byte offset in both bitmaps, Y = bit index
ReadPos:
    pha
    lsr a
    lsr a
    lsr a
    tax
    pla
    and #7
    tay
    rts

; A = text id -> A = 1 when read in both copies
IsRead:
    cmp #TEXT_COUNT
    bcs @no
    jsr ReadPos
    sep #$20
    .a8
    lda f:READ_PRIMARY,x
    and f:READ_MIRROR,x
    and BitMask8,y
    rep #$20
    .a16
    beq @no
    lda #1
    rts
@no:
    lda #0
    rts

; A = text id. Preserve the common bits and publish the new bit in both copies.
; An interrupted update can lose this mark, but leaves the common bits intact.
MarkRead:
    ldx demo_on                 ; the title's demo reads nothing for the player
    bne @done
    cmp #TEXT_COUNT
    bcs @done
    jsr ReadPos
    sep #$20
    .a8
    lda f:READ_PRIMARY,x
    and f:READ_MIRROR,x
    sta t0
    and BitMask8,y
    bne @marked
    lda t0
    ora BitMask8,y
    sta f:READ_PRIMARY,x
    sta f:READ_MIRROR,x
@marked:
    rep #$20
    .a16
@done:
    rts

; ---------------------------------------------------------------- bookmarks
; A = zero-based slot. Return 1 and its payload in save_buf, or 0 when empty.
ValidateSlot:
    inc a
    jsr FindRecord
    beq @empty
    jmp ReadRecord
@empty:
    rts

; A = zero-based slot. Capture the VM's current paragraph or choice checkpoint.
SaveGame:
    inc a
    jsr BeginRecord
    lda save_kind
    sta save_buf+10
    lda save_id
    sta save_buf+12
    lda #$FFFF
    ldx save_kind
    cpx #2
    bne :+
    lda menu_last_text
:   sta save_buf+14
    lda pic_cur
    sta save_buf+16
    lda music_cur
    sta save_buf+18
    lda chapter_cur
    sta save_buf+BOOKMARK_CHAPTER
    lda dark_on
    sta save_buf+22
    lda ripple_on
    sta save_buf+24
    lda amb_cur
    sta save_buf+26
    ldx #0
    ldy #0
:   sep #$20
    .a8
    lda sil_key,x
    sta save_buf+32,y
    lda sil_id,x
    sta save_buf+33,y
    lda sil_x,x
    sta save_buf+34,y
    lda sil_col,x
    sta save_buf+35,y
    rep #$20
    .a16
    iny
    iny
    iny
    iny
    inx
    inx
    cpx #8
    bne :-
    ldx #0
:   lda lflags,x
    sta save_buf+64,x
    inx
    inx
    cpx #64
    bne :-
    ldx #0
:   lda names,x
    sta save_buf+128,x
    inx
    inx
    cpx #20
    bne :-
    inc saves_done
    jsr CommitRecord
    sta save_ok
    rts

; A = slot: restore the state, show the picture, set vp to the op to resume (a paragraph is shown again;
; at a choice the paragraph before it is redrawn first)
LoadGame:
    jsr ValidateSlot
    bne :+
    rts
:   inc loads_done
    lda #1
    sta story_active
    ldx #0
:   lda save_buf+64,x
    sta lflags,x
    inx
    inx
    cpx #64
    bne :-
    ldx #0
:   lda save_buf+128,x
    sta names,x
    inx
    inx
    cpx #20
    bne :-
    jsr CheckNames
    lda save_buf+BOOKMARK_CHAPTER
    sta chapter_cur
    lda save_buf+22
    sta dark_on
    lda save_buf+24
    sta ripple_on
    jsr ClearSlots
    ldx #0
    ldy #0
:   lda save_buf+32,y
    and #$00FF
    cmp #$FF
    beq @free
    sta sil_key,x
    lda save_buf+33,y
    and #$00FF
    sta sil_id,x
    lda save_buf+34,y
    and #$00FF
    sta sil_x,x
    lda save_buf+35,y
    and #$00FF
    sta sil_col,x
@free:
    iny
    iny
    iny
    iny
    inx
    inx
    cpx #8
    bne :-
    lda save_buf+16
    jsr LoadPic
    lda dark_on
    beq :+
    lda #31
    sta dim_cur
:   lda save_buf+18
    cmp #$FFFF
    bne @song
    sta music_cur
    lda #SND_STOP
    jsr SndQueue
    bra @amb
@song:
    jsr PlayMusic
@amb:
    lda save_buf+26
    cmp #$FFFF
    beq :+
    sta amb_cur
    clc
    adc #SND_AMB
    jsr SndQueue
:   lda #2
    jsr FadeIn
    lda save_buf+10
    cmp #2
    bne @text
    lda save_buf+14
    cmp #$FFFF
    beq @choice
    jsr TextAddr
    inc vp                      ; past the opcode
    lda #1
    sta redraw
    jsr OpText
    stz redraw
@choice:
    lda save_buf+12
    asl a
    clc
    adc save_buf+12
    tax
    lda f:CHOICE_TABLE,x
    sta vp
    lda f:CHOICE_TABLE+1,x      ; the upper word stays inside the three-byte entry
    xba
    and #$00FF
    sta vp+2
    lda #1
    rts
@text:
    lda save_buf+12
    jsr TextAddr
    lda #1
    rts

TextAddr:
    sta t0
    asl a
    clc
    adc t0
    tax
    lda f:TEXT_TABLE,x
    sta vp
    lda f:TEXT_TABLE+1,x        ; the packed table can end at the bank boundary
    xba
    and #$00FF
    sta vp+2
    rts
