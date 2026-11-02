; ---------------------------------------------------------------- speech blips (voice 1 of the driver)
; While the body of a spoken page is typed (the page's speaker code, see UpdateMsg: the six people and
; わたし, with or without a portrait), a short blip of the speaker's voice (data/adv/voices.txt) sounds
; in a frame where UpdateMsg drew at least one voiced glyph of that body (voice_glyphs), at most once
; every SpeakerGap frames.  Punctuation (GlyphPause) keeps it silent for the same frames as the mouth,
; and the next blip starts a phrase.  Nothing is sent for the names, the narration, page / end waits,
; menus, moves or with the sound off.  The blip goes straight to the mailbox on ports 2/3 (the latest
; one only): the effect queue and its one command per frame are not used.
.a16
.i16

VOICE_PHRASE = $80

; UpdateMsg, after each glyph of a message (X = glyph, A = its GlyphPause, g_drawn set by DrawGlyph):
; the speech blips stop for as long as the mouth; a voiced glyph of a spoken body on screen is counted.
VoiceGlyph:
    cmp voice_pause
    bcc :+
    sta voice_pause
:   lda g_drawn
    beq @ret
    lda mouth_actor
    beq @ret
    lda GlyphVoice,x
    and #$00FF
    beq @ret
    inc voice_glyphs
@ret:
    rts

; Every frame after Update.
VoiceUpdate:
    lda voice_wait
    beq :+
    dec voice_wait
:   lda mode
    cmp #M_MSG
    bne @reset
    lda msg_state
    bne @reset                  ; page or end wait
    lda mouth_actor
    beq @reset                  ; narration, or the name is still being typed
    lda voice_pause
    beq @try
    dec voice_pause             ; after punctuation: silent, then a new phrase
    lda #1
    sta voice_phrase
    bra @done
@try:
    lda voice_glyphs
    beq @done
    lda voice_wait
    bne @done
    lda sound_on
    beq @done
    lda spc_ready
    beq @done
    ldx mouth_actor
    lda SpeakerVoice,x
    and #$00FF
    cmp #$00FF
    beq @done                   ; (every speaker of the script has a voice: build.py checks it)
    ldy voice_phrase
    beq :+
    ora #VOICE_PHRASE
:   sta voice_mail
    lda SpeakerGap,x
    and #$00FF
    sta voice_wait
    stz voice_phrase
    inc voice_sent
    sep #$20
    .a8
    lda voice_mail
    sta APUIO2                  ; the blip, then a new value on port 3
    inc voice_seq
    lda voice_seq
    sta APUIO3
    rep #$20
    .a16
@done:
    stz voice_glyphs
    rts
@reset:
    stz voice_glyphs
    stz voice_pause
    lda #1
    sta voice_phrase
    rts
