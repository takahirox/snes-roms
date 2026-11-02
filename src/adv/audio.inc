; ---------------------------------------------------------------- sound
; The SPC700 runs the original driver of tools/adv/spc.py (loaded at $0200 by the IPL).  The CPU sends
; one command per frame from a small queue: port 0 = command, then port 1 changes.
; 1-8 effects, $30/$31 mute/unmute, $40+n song n, $60 fade the music out, $62/$63 duck / full.  With the sound off the
; effects are not sent; the music keeps playing under the driver's mute (the opening follows its beat).
.a16
.i16

SND_MUTE = $30
SND_UNMUTE = $31
SND_SONG = $40
SND_FADE = $60
SND_DUCK = $62
SND_UNDUCK = $63
SND_QUEUE = 8

InitSpc:
    lda #.loword(SpcImage)
    sta p0
    lda #^SpcImage
    sta p0+2
    lda #SpcImageEnd-SpcImage
    sta t0
    ldy #$0000
@ipl:
    lda APUIO0
    cmp #$BBAA
    beq @go
    dey
    bne @ipl
    rts                         ; no APU answer: the game runs silent
@go:
    lda #$0200
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
    lda [p0],y
    sta APUIO1
    tya
    sta APUIO0
:   cmp APUIO0
    bne :-
    iny
    cpy t0
    bne @byte
    rep #$20
    .a16
    lda #$0200
    sta APUIO2
    sep #$20
    .a8
    stz APUIO1
    tya
    clc
    adc #2
    bne :+
    inc a                       ; the kick value must not be 0
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
    sta spc_ready
    rts

; A = effect id (1-8) or a driver command ($30 and up)
PlaySfx:
    cmp #SND_MUTE
    bcs SndQueue
    sta sfx_last
    inc sfx_count
    ldx sound_on
    bne SndQueue
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

; end of frame: one command to the SPC700
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

; the driver's master volume follows sound_on
ApplyAmbient:
    lda sound_on
    cmp snd_unmuted
    beq @ret
    sta snd_unmuted
    lda #SND_MUTE
    ldx sound_on
    beq @m
    lda #SND_UNMUTE
@m: jmp SndQueue
@ret:
    rts

; ---------------------------------------------------------------- music (tools/adv/songs.py)
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

MusicFadeOut:
    lda #$FFFF
    sta music_cur
    lda #SND_FADE
    jmp SndQueue

; every frame: the music 10 dB down while a message is open (its speech blips over it), full otherwise
DuckUpdate:
    ldx #0
    lda mode
    cmp #M_MSG
    bne :+
    inx
:   cpx duck_cur
    beq @ret
    stx duck_cur
    lda #SND_UNDUCK
    cpx #0
    beq :+
    lda #SND_DUCK
:   jmp SndQueue
@ret:
    rts

; the scene's song, unless a script chose one (music_lock)
SceneMusic:
    lda music_lock
    bne @ret
    lda scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+12,x
    jmp PlayMusic
@ret:
    rts
