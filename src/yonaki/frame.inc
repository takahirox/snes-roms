; ---------------------------------------------------------------- frame scheduler
.a16
.i16

; Byte offsets in WaitChecks. Keep zero for an idle scheduler.
WAIT_TIMER     = 2
WAIT_SKIP      = 4
WAIT_UPLOADS   = 6
WAIT_DIM       = 8
WAIT_FLASH     = 10
WAIT_TYPING    = 12
WAIT_ADVANCE   = 14
WAIT_CHOICE    = 16
WAIT_ENDING    = 18

; X = event. The caller's stack is its continuation. A check returns zero to run another frame,
; or a nonzero completion result (a PAD_* bit for interactive waits). Checks may pace work with
; PacedWait. Menu calls and other blocking events belong in the caller after WaitEvent returns.
WaitEvent:
    stx wait_event
@frame:
    jsr WaitFrame
    ldx wait_event
    jsr (WaitChecks,x)
    cmp #0
    beq @frame
    stz wait_event
    stz wait_remaining
    rts

WaitChecks:
    .word 0, CheckTimer, CheckSkip, CheckUploads, CheckDim, CheckFlash
    .word CheckTyping, CheckAdvance, CheckChoice, CheckEnding

; A = frames. Zero-length timers and already-drained uploads need no frame.
WaitFrames:
    ldx #WAIT_TIMER
WaitTimedEvent:
    cmp #0
    beq @done
    sta wait_remaining
    bra WaitEvent
@done:
    rts

WaitUploads:
    jsr UploadsPending
    beq @done
    lda #600                    ; keep the upload watchdog
    ldx #WAIT_UPLOADS
    bra WaitTimedEvent
@done:
    rts

CheckSkip:
    lda ff
    beq CheckTimer
    lda pad
    and #PAD_B
    bne EventReady
CheckTimer:
    dec wait_remaining
    beq EventReady
EventPending:
    lda #0
    rts
EventReady:
    lda #1
    rts

CheckUploads:
    jsr UploadsPending
    bne CheckTimer
    bra EventReady

UploadsPending:
    lda text_dirty
    ora text_dirty+2
    ora photo_dirty
    ora pal_dirty
    ora tint_dirty
    ora map_dirty
    ora ui_dirty
    ora sil_pending
    bne @done
    lda job_head
    eor job_tail
@done:
    rts

CheckDim:
    lda dim_cur
    cmp #31
    beq EventReady
    bra EventPending

CheckFlash:
    lda add_level
    beq EventReady
    bra EventPending

CheckTyping:
    lda pad_new
    and #PAD_A
    beq :+
    lda #1
    sta instant
:   jsr ReadSkipHeld
    beq EventReady
    lda #1
    sta instant
    sta ff
    rts

; A is nonzero only while B is held over a paragraph that was already read.
ReadSkipHeld:
    lda cur_read
    beq :+
    lda pad
    and #PAD_B
:   rts

CheckAdvance:
    lda pad_new
    and #PAD_A
    bne @done
    jsr ReadSkipHeld
    bne @done
    lda pad_new
    and #PAD_START
    bne @done
    jsr UpdateWaitMark
    lda #0
@done:
    rts

CheckChoice:
    lda opt_count
    cmp #2
    bcc @buttons
    lda pad_rep
    and #PAD_UP
    bne @done
    lda pad_rep
    and #PAD_DOWN
    bne @done
@buttons:
    lda pad_new
    and #PAD_A
    bne @done
    lda pad_new
    and #PAD_START
@done:
    rts

CheckEnding:
    lda pad_new
    and #PAD_A|PAD_START
    rts

; Run one frame for the active wait or a paced producer. All producers share this order.
; The main thread owns effects, upload preparation and the SPC FIFO. NMI owns the published DMA
; list and PPU writes. Only after that handoff completes do we sample input and check the wait.
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
