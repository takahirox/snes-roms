; ---------------------------------------------------------------- battery SRAM ($70:0000, 8 KiB)
; $0000 global (256 bytes): +0 "YNKG" +4 version +6 text speed +8 endings seen (32 bits) +12 global flags
;        (32 bits) +16 the names (20 bytes, see names) +36..+251 zero +252 sum of words 0-125 +254 sum xor $FFFF
; $0100, $0200, $0300 bookmarks 1-3 (256 bytes): +0 "YNKS" +4 version +6 build id (32 bits) +10 kind (1 at a
;        paragraph, 2 at a choice) +12 text / choice id +14 paragraph to redraw before a choice ($FFFF none)
;        +16 picture +18 song ($FFFF none) +20 chapter ($FFFF) +22 dark +24 ripple +26 ambience ($FFFF)
;        +28 sequence +32 four silhouette slots (key, silhouette, x, colour: bytes) +48..+63 zero
;        +64..+127 local flags +128 the names (20 bytes) +148..+251 zero +252 sum +254 sum xor $FFFF
; $0400 read marks: +0 "YNKR" +4 build id (32 bits) +8.. one bit per paragraph (text id), $1FFC sum of the words
;        $0400-$1FFB, $1FFE sum xor $FFFF.  The sum is kept up to date bit by bit (MarkRead).
; Power-on SRAM is undefined: everything is checked; a broken global block or read-mark block is reset,
; a broken bookmark is shown as empty.
.a16
.i16

SRAM = $700000
SAVE_VERSION = 1
READ_BASE = $700400
READ_MARKS = $700408
READ_SUM = $701FFC
READ_MAX = ($1FFC - $0408) * 8

; t0 = sum of A words from SRAM long address p1 -> A
SumSram:
    tax
    stz t0
    ldy #0
:   lda [p1],y
    clc
    adc t0
    sta t0
    iny
    iny
    dex
    bne :-
    lda t0
    rts

SramBoot:
    ; global block
    lda #.loword(SRAM)
    sta p1
    lda #^SRAM
    sta p1+2
    lda #126
    jsr SumSram
    cmp f:SRAM+252
    bne @gbad
    eor #$FFFF
    cmp f:SRAM+254
    bne @gbad
    lda f:SRAM
    cmp #$4E59                  ; "YN"
    bne @gbad
    lda f:SRAM+2
    cmp #$474B                  ; "KG"
    bne @gbad
    lda f:SRAM+4
    cmp #SAVE_VERSION
    bne @gbad
    lda f:SRAM+6
    cmp #4
    bcs @gbad
    sta speed
    lda f:SRAM+8
    sta gendings
    lda f:SRAM+10
    sta gendings+2
    lda f:SRAM+12
    sta gflags
    lda f:SRAM+14
    sta gflags+2
    ldx #0
:   lda f:SRAM+16,x
    sta names,x
    inx
    inx
    cpx #20
    bne :-
    jsr CheckNames
    bra @read
@gbad:
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
@read:
    lda #.loword(READ_BASE)
    sta p1
    lda #^READ_BASE
    sta p1+2
    lda #($1FFC - $0400) / 2
    jsr SumSram
    cmp f:READ_SUM
    bne @rbad
    eor #$FFFF
    cmp f:READ_SUM+2
    bne @rbad
    lda f:READ_BASE
    cmp #$4E59
    bne @rbad
    lda f:READ_BASE+2
    cmp #$524B                  ; "KR"
    bne @rbad
    lda f:READ_BASE+4
    cmp #BUILD_ID_LO
    bne @rbad
    lda f:READ_BASE+6
    cmp #BUILD_ID_HI
    bne @rbad
    rts
@rbad:
    lda sram_resets
    ora #2
    sta sram_resets
    ldx #0
    lda #0
:   sta f:READ_BASE,x
    inx
    inx
    cpx #$1C00
    bne :-
    lda #$4E59
    sta f:READ_BASE
    lda #$524B
    sta f:READ_BASE+2
    lda #BUILD_ID_LO
    sta f:READ_BASE+4
    lda #BUILD_ID_HI
    sta f:READ_BASE+6
    lda #$4E59
    clc
    adc #$524B
    clc
    adc #BUILD_ID_LO
    clc
    adc #BUILD_ID_HI
    sta f:READ_SUM
    eor #$FFFF
    sta f:READ_SUM+2
    rts

SaveGlobal:
    lda #$4E59
    sta f:SRAM
    lda #$474B
    sta f:SRAM+2
    lda #SAVE_VERSION
    sta f:SRAM+4
    lda speed
    sta f:SRAM+6
    lda gendings
    sta f:SRAM+8
    lda gendings+2
    sta f:SRAM+10
    lda gflags
    sta f:SRAM+12
    lda gflags+2
    sta f:SRAM+14
    ldx #0
:   lda names,x
    sta f:SRAM+16,x
    inx
    inx
    cpx #20
    bne :-
    ldx #36
    lda #0
:   sta f:SRAM,x
    inx
    inx
    cpx #252
    bne :-
    lda #.loword(SRAM)
    sta p1
    lda #^SRAM
    sta p1+2
    lda #126
    jsr SumSram
    sta f:SRAM+252
    eor #$FFFF
    sta f:SRAM+254
    rts

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
; A = text id -> X = byte offset from READ_BASE, Y = bit index
ReadPos:
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc #8
    tax
    pla
    and #7
    tay
    rts

; A = text id -> A = 1 when read
IsRead:
    cmp #READ_MAX
    bcs @no
    jsr ReadPos
    sep #$20
    .a8
    lda f:READ_BASE,x
    and BitMask8,y
    rep #$20
    .a16
    beq @no
    lda #1
    rts
@no:
    lda #0
    rts

; A = text id: mark read (the sum follows the one bit)
MarkRead:
    cmp #READ_MAX
    bcs @r
    jsr ReadPos
    sep #$20
    .a8
    lda f:READ_BASE,x
    and BitMask8,y
    bne @r8
    lda f:READ_BASE,x
    ora BitMask8,y
    sta f:READ_BASE,x
    rep #$20
    .a16
    lda BitMask8,y
    and #$00FF
    sta t0
    txa
    lsr a
    bcc :+
    lda t0
    xba
    sta t0
:   lda f:READ_SUM
    clc
    adc t0
    sta f:READ_SUM
    eor #$FFFF
    sta f:READ_SUM+2
@r:
    rts
@r8:
    rep #$20
    .a16
    rts

; ---------------------------------------------------------------- bookmarks
; A = slot -> p1 = its SRAM address
SlotAddr:
    inc a
    xba
    sta p1
    lda #^SRAM
    sta p1+2
    rts

; A = slot -> save_buf = the slot; A = 1 valid, 0 not (Z)
ValidateSlot:
    jsr SlotAddr
    ldy #0
:   lda [p1],y
    tyx
    sta save_buf,x
    iny
    iny
    cpy #256
    bne :-
    stz t0
    ldx #0
:   lda save_buf,x
    clc
    adc t0
    sta t0
    inx
    inx
    cpx #252
    bne :-
    lda t0
    cmp save_buf+252
    beq :+
    jmp @bad
:   eor #$FFFF
    cmp save_buf+254
    beq :+
    jmp @bad
:   lda save_buf
    cmp #$4E59
    beq :+
    jmp @bad
:   lda save_buf+2
    cmp #$534B                  ; "KS"
    beq :+
    jmp @bad
:   lda save_buf+4
    cmp #SAVE_VERSION
    jne @bad
    lda save_buf+6
    cmp #BUILD_ID_LO
    jne @bad
    lda save_buf+8
    cmp #BUILD_ID_HI
    bne @bad
    lda save_buf+10
    cmp #1
    bne @choice
    lda save_buf+12
    cmp #TEXT_COUNT
    bcs @bad
    bra @kind_ok
@choice:
    cmp #2
    bne @bad
    lda save_buf+12
    cmp #CHOICE_COUNT
    bcs @bad
@kind_ok:
    lda save_buf+14
    cmp #$FFFF
    beq :+
    cmp #TEXT_COUNT
    bcs @bad
:   lda save_buf+16
    cmp #PIC_COUNT
    bcs @bad
    lda save_buf+20
    cmp #$FFFF
    beq :+
    cmp #CHAPTER_COUNT
    bcs @bad
:   ldx #0
@sl:
    lda save_buf+32,x
    and #$00FF
    cmp #$FF
    beq @sn
    lda save_buf+33,x
    and #$00FF
    cmp #SIL_COUNT
    bcs @bad
    lda save_buf+34,x
    and #$00FF
    cmp #32
    bcs @bad
    lda save_buf+35,x
    and #$00FF
    cmp #3
    bcs @bad
@sn:
    inx
    inx
    inx
    inx
    cpx #16
    bne @sl
    lda #1
    rts
@bad:
    lda #0
    rts

; A = slot: write the state at the current wait (save_kind / save_id) and verify it
SaveGame:
    sta t7
    ldx #0
    lda #0
:   sta save_buf,x
    inx
    inx
    cpx #256
    bne :-
    lda #$4E59
    sta save_buf
    lda #$534B
    sta save_buf+2
    lda #SAVE_VERSION
    sta save_buf+4
    lda #BUILD_ID_LO
    sta save_buf+6
    lda #BUILD_ID_HI
    sta save_buf+8
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
    sta save_buf+20
    lda dark_on
    sta save_buf+22
    lda ripple_on
    sta save_buf+24
    lda amb_cur
    sta save_buf+26
    inc save_seq
    lda save_seq
    sta save_buf+28
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
    stz t0
    ldx #0
:   lda save_buf,x
    clc
    adc t0
    sta t0
    inx
    inx
    cpx #252
    bne :-
    lda t0
    sta save_buf+252
    eor #$FFFF
    sta save_buf+254
    lda t7
    jsr SlotAddr
    ldy #0
:   tyx
    lda save_buf,x
    sta [p1],y
    iny
    iny
    cpy #256
    bne :-
    inc saves_done
    lda t7
    jsr ValidateSlot
    sta save_ok
    rts

; A = slot: restore the state, show the picture, set vp to the op to resume (a paragraph is shown again;
; at a choice the paragraph before it is redrawn first)
LoadGame:
    jsr ValidateSlot
    bne :+
    rts
:   inc loads_done
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
    lda save_buf+20
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
    beq :+
    jsr PlayMusic
:   lda save_buf+26
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
    lda f:CHOICE_TABLE+2,x
    and #$00FF
    sta vp+2
    rts
@text:
    lda save_buf+12
TextAddr:
    sta t0
    asl a
    clc
    adc t0
    tax
    lda f:TEXT_TABLE,x
    sta vp
    lda f:TEXT_TABLE+2,x
    and #$00FF
    sta vp+2
    rts
