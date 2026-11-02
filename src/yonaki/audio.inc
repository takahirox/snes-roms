; ---------------------------------------------------------------- sound (tools/yonaki/audio.py)
; The SPC700 image (SPC_LEN bytes from SPC_ADDR, over as many banks as it needs) goes up with the IPL
; transfer to SPC_LOAD and starts at SPC_ENTRY; the driver writes $5A to port 0 when ready.
; Commands, one per frame from a small queue: port 0 = command, then a new value on port 1.
;   $01-$2F effect n, $40+n song n, $60 fade the music, $61 stop it, $70+k ambience k, $7F ambience off.
.a16
.i16

SND_SONG = $40
SND_FADE = $60
SND_STOP = $61
SND_AMB = $70
SND_AMB_OFF = $7F
SND_QUEUE = 8

InitSpc:
    lda #.loword(SPC_ADDR)
    sta p0
    lda #^SPC_ADDR
    sta p0+2
    lda #SPC_LEN
    sta t0
    ldy #$0000
@ipl:
    lda APUIO0
    cmp #$BBAA
    beq @go
    dey
    bne @ipl
    rts                         ; no answer: silent
@go:
    lda #SPC_LOAD
    sta APUIO2
    sep #$20
    .a8
    lda #$01
    sta APUIO1
    lda #$CC
    sta APUIO0
:   cmp APUIO0
    bne :-
    ldy #0
@byte:
    lda [p0]
    sta APUIO1
    tya
    sta APUIO0
:   cmp APUIO0
    bne :-
    rep #$20
    .a16
    inc p0
    bne :+
    lda #$8000
    sta p0
    inc p0+2
:   sep #$20
    .a8
    iny
    cpy t0
    bne @byte
    rep #$20
    .a16
    lda #SPC_ENTRY
    sta APUIO2
    sep #$20
    .a8
    stz APUIO1
    tya
    clc
    adc #2
    bne :+
    inc a
:   sta APUIO0
    rep #$20
    .a16
    ldy #$0000
:   lda APUIO0
    and #$00FF
    cmp #$5A
    beq @ok
    dey
    bne :-
    rts
@ok:
    lda #1
    sta spc_ready
    rts

SndQueue:
    ldx snd_count
    cpx #SND_QUEUE*2
    bcs :+
    sta snd_queue,x
    inx
    inx
    stx snd_count
:   rts

; end of frame: one command
SndPump:
    lda snd_count
    beq @ret
    lda spc_ready
    beq @drop
    sep #$20
    .a8
    lda snd_queue
    sta APUIO0
    inc spc_toggle
    lda spc_toggle
    sta APUIO1
    rep #$20
    .a16
    inc snd_sent
@drop:
    ldx #0
:   lda snd_queue+2,x
    sta snd_queue,x
    inx
    inx
    cpx #SND_QUEUE*2-2
    bne :-
    dec snd_count
    dec snd_count
@ret:
    rts

; A = song: asked of the driver unless it is the one playing
PlayMusic:
    cmp music_cur
    beq @ret
    sta music_cur
    clc
    adc #SND_SONG
    jmp SndQueue
@ret:
    rts

SndCursor:
    lda #SE_CURSOR
    bra SndUi
SndOk:
    lda #SE_OK
    bra SndUi
SndCancel:
    lda #SE_CANCEL
SndUi:
    cmp #$FF
    beq :+
    jmp SndQueue
:   rts
