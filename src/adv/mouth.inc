; ---------------------------------------------------------------- lip-sync (mouth of the shown portrait)
; The mouth moves only while the body of a page is being typed, the page's speaker code ($FFE0|id after
; the yellow name, see UpdateMsg) is the person of the portrait on screen, and the portrait is fully
; uploaded.  Anything else asks for the closed mouth in the same frame.  The closed mouth is the
; portrait's own tiles; the half-open and open mouths are 1-4 picture tiles from MouthTable.
.a16
.i16

MOUTH_CYCLE = 13

; Every frame after Update: mouth_want from the message state, the speaker and the portrait.
MouthUpdate:
    stz mouth_talk
    lda mode
    cmp #M_MSG
    bne @closed
    lda msg_state
    bne @closed                 ; page or end wait
    lda mouth_actor
    beq @closed                 ; narration, or the name is still being typed
    cmp #SPEAKER_ME
    beq @closed                 ; the player has no portrait
    lda por_shown
    beq @closed
    lda por_rows
    bne @closed                 ; the portrait is still being written
    lda por_shown
    dec a
    asl a
    asl a
    asl a
    asl a
    tax                         ; MouthTable entry (16 bytes)
    lda MouthTable,x
    cmp mouth_actor
    beq @talk
    inc mouth_other             ; someone else speaks: this face stays still
    bra @closed
@talk:
    lda #1
    sta mouth_talk
    lda mouth_pause
    beq @cycle
    dec mouth_pause             ; a pause after punctuation: closed, then the cycle from its start
    stz mouth_timer
    stz mouth_want
    rts
@cycle:
    ldx mouth_timer
    lda MouthSeq,x
    and #$00FF
    sta mouth_want
    inx
    cpx #MOUTH_CYCLE
    bcc :+
    ldx #0
:   stx mouth_timer
    rts
@closed:
    stz mouth_timer
    stz mouth_pause
    stz mouth_want
    rts

; half x3, open x4, half x3, closed x3 (frames), and a pad byte for the 16-bit read
MouthSeq: .byte 1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 0, 0, 0, 0

; First thing in PumpUploads (t5 = budget): the mouth tiles when the wanted frame is not on screen.
; While a portrait is being put on or taken off (or there is none) its rows rewrite these tiles with
; the closed mouth or the picture, so nothing is queued and the shown frame becomes the closed one.
MouthPump:
    lda por_shown
    beq @base
    lda por_rows
    bne @base
    lda mouth_want
    cmp mouth_shown
    beq @ret                    ; no change: nothing is sent
    sta mouth_shown
    asl a
    sta t6
    lda por_shown
    dec a
    asl a
    asl a
    asl a
    asl a
    tax
    clc
    adc t6
    tay
    lda MouthTable+8,y          ; closed / half / open tiles
    sta t2
    lda MouthTable+14,x
    xba
    and #$FF00
    sta t1                      ; VRAM, bank
    lda MouthTable+2,x
    sta t0
    lda MouthTable+4,x
    sta t3                      ; bytes per tile row
    lda MouthTable+6,x
    sta t4                      ; tile rows
@row:
    jsr Enqueue
    lda t5
    sec
    sbc t3
    sta t5
    lda t2
    clc
    adc t3
    sta t2
    lda t0
    clc
    adc #32*32                  ; next picture tile row
    sta t0
    dec t4
    bne @row
    inc mouth_uploads
@ret:
    rts
@base:
    stz mouth_shown
    rts
