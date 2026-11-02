; ---------------------------------------------------------------- battery SRAM ($70:0000, 8 KiB)
; Two 256-byte slots (A at $0000, B at $0100):
;   +0 "SHIO"  +4 version (1)  +6 sequence  +8 scene  +10 wrong answers  +12 actions  +14 sound
;   +16..+143 flags (1024 bits)  +144..+251 zero  +252 sum of words 0-125  +254 sum xor $FFFF
; A save goes to the older (or invalid) slot, the checksum last; a load takes the newest valid slot.
; Power-on SRAM is undefined: every field is checked before anything is used.
.a16
.i16

SRAM = $700000
SAVE_VERSION = 1
SAVE_SUM = 252

; copy slot A (0/1) into save_buf
CopySlot:
    xba
    and #$FF00
    tax
    ldy #0
:   lda f:SRAM,x
    phx
    tyx
    sta f:save_buf,x
    plx
    inx
    inx
    iny
    iny
    cpy #256
    bne :-
    rts

; A = slot -> A = 0 empty (no magic), 1 broken, 2 valid; t6 = sequence when valid
ValidateSlot:
    jsr CopySlot
    lda f:save_buf
    cmp #$4853                  ; "SH"
    beq :+
    jmp @none
:   lda f:save_buf+2
    cmp #$4F49                  ; "IO"
    beq :+
    jmp @none
:
    ; checksum
    stz t0
    ldx #0
:   lda f:save_buf,x
    clc
    adc t0
    sta t0
    inx
    inx
    cpx #SAVE_SUM
    bne :-
    lda f:save_buf+SAVE_SUM
    cmp t0
    bne @broken
    eor #$FFFF
    cmp f:save_buf+SAVE_SUM+2
    bne @broken
    lda f:save_buf+4
    cmp #SAVE_VERSION
    bne @broken
    lda f:save_buf+8
    cmp #SCENE_COUNT
    bcs @broken
    lda f:save_buf+14
    cmp #2
    bcs @broken
    ; unused flag bits and the reserved bytes must be zero
    sep #$20
    .a8
    lda f:save_buf+16
    and #$01                    ; flag 0 does not exist
    bne @broken8
    lda f:save_buf+16+(FLAG_COUNT >> 3)
    and #<($FF << (FLAG_COUNT & 7))
    bne @broken8
    ldx #16+(FLAG_COUNT >> 3)+1
:   cpx #SAVE_SUM
    beq :+
    lda f:save_buf,x
    bne @broken8
    inx
    bra :-
:   rep #$20
    .a16
    ; the saved place must be open under the saved flags
    lda f:save_buf+8
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+8,x
    beq @ok
    pha
    lsr a
    lsr a
    lsr a
    tax
    pla
    and #7
    tay
    sep #$20
    .a8
    lda f:save_buf+16,x
    and ByteBit,y
    bne :+
    rep #$20
    .a16
    bra @broken
:   rep #$20
    .a16
@ok:
    lda f:save_buf+6
    sta t6
    lda #2
    rts
@broken8:
    rep #$20
    .a16
@broken:
    lda #1
    rts
@none:
    lda #0
    rts

; save_status = best of the two slots
CheckSave:
    lda #0
    jsr ValidateSlot
    sta t7
    lda #1
    jsr ValidateSlot
    cmp t7
    bcc :+
    sta t7
:   lda t7
    sta save_status
    rts

; newest valid slot -> save_slot, its sequence -> save_seq; A = 0 if none
NewestSlot:
    lda #0
    jsr ValidateSlot
    sta t4
    lda t6
    sta t5
    lda #1
    jsr ValidateSlot
    cmp #2
    bne @a
    lda t4
    cmp #2
    bne @b
    lda t6                      ; both valid: the newer sequence (wrapping)
    sec
    sbc t5
    bmi @a
@b:
    lda #1
    sta save_slot
    lda t6
    sta save_seq
    lda #1
    rts
@a:
    lda t4
    cmp #2
    bne @no
    stz save_slot
    lda t5
    sta save_seq
    lda #1
    rts
@no:
    stz save_seq
    lda #0
    rts

SaveGame:
    jsr NewestSlot
    beq @slot0
    lda save_slot
    eor #1                      ; overwrite the other (older or invalid) slot
    bra :+
@slot0:
    lda #0
:   sta t7                      ; target
    ; build the record
    ldx #0
    lda #0
:   sta f:save_buf,x
    inx
    inx
    cpx #256
    bne :-
    lda #$4853
    sta f:save_buf
    lda #$4F49
    sta f:save_buf+2
    lda #SAVE_VERSION
    sta f:save_buf+4
    lda save_seq
    inc a
    sta f:save_buf+6
    sta t5
    lda scene
    sta f:save_buf+8
    lda wrong_count
    sta f:save_buf+10
    lda actions
    sta f:save_buf+12
    lda sound_on
    sta f:save_buf+14
    ldx #0
:   lda flags,x
    sta f:save_buf+16,x
    inx
    inx
    cpx #128
    bne :-
    stz t0
    ldx #0
:   lda f:save_buf,x
    clc
    adc t0
    sta t0
    inx
    inx
    cpx #SAVE_SUM
    bne :-
    lda t0
    sta f:save_buf+SAVE_SUM
    eor #$FFFF
    sta f:save_buf+SAVE_SUM+2
    ; write: body first, the checksum last
    lda t7
    xba
    and #$FF00
    tax
    ldy #0
:   phx
    tyx
    lda f:save_buf,x
    plx
    sta f:SRAM,x
    inx
    inx
    iny
    iny
    cpy #256
    bne :-
    inc saves_done
    ; verify
    lda t7
    jsr ValidateSlot
    stz save_ok
    cmp #2
    bne :+
    lda t6
    cmp t5
    bne :+
    lda #1
    sta save_ok
    lda t7
    sta save_slot
:   rts

LoadSave:
    jsr NewestSlot
    lda save_slot
    jsr ValidateSlot
    ldx #0
:   lda f:save_buf+16,x
    sta flags,x
    inx
    inx
    cpx #128
    bne :-
    lda f:save_buf+10
    sta wrong_count
    lda f:save_buf+12
    sta actions
    lda f:save_buf+14
    sta sound_on
    lda f:save_buf+8
    jsr SetSceneQuiet          ; (the song comes with the picture: OpResume)
    inc load_count
    rts
