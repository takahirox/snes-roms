; ---------------------------------------------------------------- opening and title (mode M_OPEN)
; At power-on: a notice on black, four pictures of the harbour night with two lines of text each (one
; picture every 2 bars of the opening song), 2 bars of black with a timpani roll, then the title (the
; picture, the logo, PUSH START BUTTON blinking) on the first bar of the main theme.  The prologue
; follows the song's beat counter (driver port 3); without a sound driver it counts 45 frames a beat.
; A or START skips to the title; on the title A / START opens the menu (はじめから / つづきから) and B
; on the menu comes back.  Left alone on the title for one loop of its theme (48 s), it all starts again.
; The text layer is faded through the UI colours 0-15: in the opening they come from OpenPalette (the
; panel colours black) scaled by op_ui_level; the game's UiPalette is put back when a game starts.
.a16
.i16

OP_PROLOGUE = 0
OP_TO_TITLE = 1
OP_TITLE    = 2
OP_RESTART  = 3

OA_TEXT    = 0                  ; draw caption pair arg, fade the text in
OA_TEXTOUT = 1                  ; fade the text out
OA_PIC     = 2                  ; change the picture to arg (fade out, load, fade in)
OA_PICOUT  = 3                  ; fade the picture to black
OA_TITLE   = 4                  ; the title
OA_END     = $FF

C_BLINK = 8                     ; PUSH START BUTTON (the blink switches this colour)
BEAT_FRAMES = 45                ; 80 bpm without a sound driver
TITLE_IDLE = 2860               ; frames on the title before the opening starts again (one loop of the theme)
CAPTION_Y0 = 40
CAPTION_Y1 = 60

; beat, action, argument
OpTimeline:
    .word 0,  OA_TEXT, 0
    .word 6,  OA_TEXTOUT, 0
    .word 8,  OA_PIC, IMAGE_TITLE
    .word 8,  OA_TEXT, 1
    .word 14, OA_TEXTOUT, 0
    .word 16, OA_PIC, IMAGE_LIGHTHOUSE
    .word 16, OA_TEXT, 2
    .word 22, OA_TEXTOUT, 0
    .word 24, OA_PIC, IMAGE_SIGNAL
    .word 24, OA_TEXT, 3
    .word 30, OA_TEXTOUT, 0
    .word 32, OA_PIC, IMAGE_WAREHOUSE
    .word 32, OA_TEXT, 4
    .word 38, OA_TEXTOUT, 0
    .word 40, OA_PICOUT, 0
    .word 48, OA_TITLE, 0
    .word $FFFF, OA_END, 0

OpCaptions:
    .word TX_OPEN_0_0, TX_OPEN_0_1, TX_OPEN_1_0, TX_OPEN_1_1, TX_OPEN_2_0, TX_OPEN_2_1
    .word TX_OPEN_3_0, TX_OPEN_3_1, TX_OPEN_4_0, TX_OPEN_4_1
OpCaptionColor:
    .word C_GRAY, C_WHITE, C_WHITE, C_WHITE, C_WHITE

;      0 black   1 bg      2 text    3 frame   4 shade   5 gray    6 yellow  7 cyan    8 blink
OpenPalette:
    .word $0000,    $0000,    $6FBD,    $0000,    $0000,    $4A31,    $335F,    $7750
    .word $5EF7,    $0000,    $0000,    $0000,    $0000,    $0000,    $0000,    $0000

; ---------------------------------------------------------------- entry points
; Power-on and the attract loop: the opening from its first beat.
OpeningStart:
    lda #M_OPEN
    sta mode
    stz op_state
    stz op_step
    stz op_frames
    stz op_beat
    stz op_song_seen
    stz op_blink
    stz music_lock
    lda #.loword(OpenPalette)
    sta op_ui_src
    stz op_ui_target
    lda op_ui_level
    beq :+
    stz op_ui_level             ; (already black when the restart gets here)
    jsr BuildUiPal
:   jsr InitBitmap
    lda #$FFFF
    sta music_cur               ; the song restarts even when it is the one playing
    lda #SONG_OPENING
    jmp PlayMusic

; From the ending: the text fades, then the title as after a skipped prologue.
TitleFromGame:
    lda #M_OPEN
    sta mode
    stz music_lock
    jsr PortraitOff
    lda #OP_TO_TITLE
    sta op_state
    stz op_ui_target
    lda #SONG_TITLE
    jsr PlayMusic
    lda #IMAGE_TITLE
    jmp OpPicTo

; ---------------------------------------------------------------- per frame
UpdateOpen:
    inc op_frames
    jsr OpPicStep
    jsr OpUiStep
    lda op_state
    asl a
    tax
    jmp (OpStateTable,x)
OpStateTable:
    .word OpPrologue, OpToTitle, OpTitle, OpRestart

OpPrologue:
    lda pad_new
    and #PAD_A|PAD_START
    beq @beat
    ; skip: the title now, the song from its main theme
    lda #SONG_TITLE
    jsr PlayMusic
    jmp OpGoTitle
@beat:
    jsr OpCurrentBeat
    bcc @ret                    ; the song has not started yet
    sta op_beat
@act:
    lda op_step
    asl a
    clc
    adc op_step
    asl a
    tax                         ; step * 6
    lda OpTimeline,x
    cmp op_beat
    beq :+
    bcs @ret
:   inc op_step
    lda OpTimeline+4,x
    sta op_arg
    lda OpTimeline+2,x
    asl a
    tax
    jsr (OpActions,x)
    lda mode
    cmp #M_OPEN
    bne @ret
    lda op_state
    beq @act
@ret:
    rts
OpActions:
    .word OpaText, OpaTextOut, OpaPic, OpaPicOut, OpaTitle

; carry set and A = beats since the opening song started; carry clear before it has started
OpCurrentBeat:
    lda spc_ready
    bne @spc
    lda op_frames               ; no sound driver: count frames
    sta f:WRDIVL
    sep #$20
    .a8
    lda #BEAT_FRAMES
    sta f:WRDIVB
    rep #$20
    .a16
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda f:RDDIVL
    sec
    rts
@spc:
    sep #$20
    .a8
    lda op_song_seen
    bne @run
    lda APUIO2                  ; song number + 1 of the driver
    cmp #SONG_OPENING+1
    bne @no
    lda #1
    sta op_song_seen
@run:
    lda APUIO3
    rep #$20
    .a16
    and #$00FF
    sec
    rts
@no:
    rep #$20
    .a16
    clc
    rts

OpaText:
    jsr OpClearCaption
    lda op_arg
    asl a
    tax
    lda OpCaptionColor,x
    sta g_c
    lda op_arg
    asl a
    asl a
    tax
    phx
    lda OpCaptions,x
    ldx #CAPTION_Y0
    jsr OpCentered
    plx
    lda OpCaptions+2,x
    ldx #CAPTION_Y1
    jsr OpCentered
    lda #16
    sta op_ui_target
    rts

OpaTextOut:
    stz op_ui_target
    rts

OpaPic:
    lda op_arg
    jmp OpPicTo

OpaPicOut:
    lda #4
    sta op_pic_state
    rts

OpaTitle:
OpGoTitle:
    lda #OP_TO_TITLE
    sta op_state
    stz op_ui_target
    lda #IMAGE_TITLE
    jmp OpPicTo

; the text out, then the title drawn and faded in with the picture
OpToTitle:
    lda op_ui_level
    bne @ret
    lda #.loword(OpenPalette)
    sta op_ui_src
    jsr DrawTitleScreen
    jsr OpDrawPush
    lda #16
    sta op_ui_target
    lda #OP_TITLE
    sta op_state
    stz op_idle
    stz op_blink
@ret:
    rts

OpTitle:
    ; PUSH START BUTTON blinks: 40 frames on, 24 off (once the title is in)
    lda op_ui_level
    cmp #16
    bne @keys
    inc op_blink
    lda op_blink
    cmp #40
    bne :+
    jsr BuildUiPal
:   lda op_blink
    cmp #64
    bcc @keys
    stz op_blink
    jsr BuildUiPal
@keys:
    lda pad_new
    and #PAD_A|PAD_START
    beq @idle
    lda #SFX_OK
    jsr PlaySfx
    stz op_blink
    jsr BuildUiPal
    jmp TitleShow
@idle:
    inc op_idle
    lda op_idle
    cmp #TITLE_IDLE
    bcc @ret
    ; left alone: everything fades and the opening starts again
    lda #OP_RESTART
    sta op_state
    stz op_ui_target
    lda #4
    sta op_pic_state
    stz op_idle
    jmp MusicFadeOut
@ret:
    rts

OpRestart:
    inc op_idle
    lda op_idle
    cmp #90
    bcc @ret
    lda op_pic_state
    ora op_ui_level
    bne @ret
    jmp OpeningStart
@ret:
    rts

; ---------------------------------------------------------------- drawing
; the whole text layer for the title: the tagline above the picture and the logo below it
DrawTitleScreen:
    jsr InitBitmap              ; (the panel template: its colours are black in OpenPalette)
    lda #C_GRAY
    sta g_c
    lda #TX_HDR_TITLE
    ldx #2
    jsr OpCentered
    jmp DrawLogo

OpDrawPush:
    lda #1
    sta t0
    lda #30
    sta t1
    lda #6
    sta t2
    lda #11
    sta t3
    stz t4
    jsr RestoreRect
    lda #C_BLINK
    sta g_c
    lda #TX_PUSH_START
    ldx #64
    jmp OpCentered

OpClearCaption:
    lda #0
    jmp RestorePanel

; A = text id, X = y: drawn centred in g_c
OpCentered:
    stx g_y
    pha
    jsr TextPtr
    jsr TextWidth
    lsr a
    eor #$FFFF
    sec
    adc #128
    sta g_x
    pla
    jmp DrawTextId

; ---------------------------------------------------------------- the picture: slow fades
; op_pic_state: 0 idle, 1 out (then load op_pic_next), 2 loading, 3 in, 4 out and stay black
OpPicTo:
    sta op_pic_next
    cmp image_cur
    bne @out
    lda fade_level
    cmp #16
    beq @ret
    lda #3                      ; the same picture, faded: only fade in
    sta op_pic_state
@ret:
    rts
@out:
    lda #1
    sta op_pic_state
    rts

OpPicStep:
    lda op_frames
    and #1
    bne @ret
    lda op_pic_state
    beq @ret
    cmp #2
    beq @load
    cmp #3
    beq @in
    ; out (1 or 4)
    lda fade_level
    beq @black
    dec fade_level
    jmp FadePalette
@black:
    lda op_pic_state
    cmp #4
    bne :+
    stz op_pic_state
    rts
:   lda op_pic_next
    sta image_cur
    asl a
    asl a
    tax
    lda ImageTable,x
    sta img_bank
    stz img_pos
    lda #32768
    sta img_left
    lda #2
    sta op_pic_state
    rts
@load:
    lda img_left
    bne @ret
    lda #3
    sta op_pic_state
    rts
@in:
    lda fade_level
    cmp #16
    bcs :+
    inc fade_level
    jmp FadePalette
:   stz op_pic_state
@ret:
    rts

; ---------------------------------------------------------------- the text colours
OpUiStep:
    lda op_frames
    and #1
    bne @ret
    lda op_ui_level
    cmp op_ui_target
    beq @ret
    bcc :+
    dec op_ui_level
    jmp BuildUiPal
:   inc op_ui_level
    jmp BuildUiPal
@ret:
    rts

; ui_pal = colours 0-15 of op_ui_src at op_ui_level (colour 8 dark while the blink is off)
BuildUiPal:
    lda op_ui_src
    sta p1
    lda op_ui_level
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t6                      ; level * 32
    ldy #0
@l:
    lda (p1),y
    sta t0
    cpy #C_BLINK*2
    bne :+
    lda op_blink
    cmp #40
    bcc :+
    stz t0
:   lda t0
    and #31
    clc
    adc t6
    tax
    lda FadeTab,x
    and #$00FF
    sta t1
    lda t0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    sta t0
    and #31
    clc
    adc t6
    tax
    lda FadeTab,x
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora t1
    sta t1
    lda t0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #31
    clc
    adc t6
    tax
    lda FadeTab,x
    and #$00FF
    xba
    asl a
    asl a
    ora t1
    sta ui_pal,y
    iny
    iny
    cpy #32
    bne @l
    lda #1
    sta ui_dirty
    rts

; the game's colours back (a game starts): the text layer at full brightness from UiPalette
GameColors:
    lda #.loword(UiPalette)
    sta op_ui_src
    lda #16
    sta op_ui_level
    sta op_ui_target
    stz op_blink
    jmp BuildUiPal
