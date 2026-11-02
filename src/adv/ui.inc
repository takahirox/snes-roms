; ---------------------------------------------------------------- screen parts
.a16
.i16

; Restore whole tiles from the ROM templates by DMA (channel 1, WRAM port $2180):
; t0 = first column, t1 = last column, t2 = first tile row, t3 = last tile row (0-11),
; t4 = panel template (0 message frame, 1 command frame with the divider).  Rows 0-1 = header.
RestoreRect:
    lda t1
    sec
    sbc t0
    inc a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t5                      ; bytes per tile row
    lda t2
    sta t6
@r:
    lda t6
    cmp #2
    bcs @panel
    xba
    asl a
    asl a
    bra @src
@panel:
    sec
    sbc #2
    xba
    asl a
    asl a
    clc
    adc #2048
    ldx t4
    beq @src
    clc
    adc #10240
@src:
    sta t7
    lda t0
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t1
    clc
    adc t7
    clc
    adc #.loword(TemplateData)
    sta f:$4312                 ; A1T1
    lda t6
    xba
    asl a
    asl a
    clc
    adc t1
    clc
    adc #.loword(BMP)
    sta f:$2181                 ; WMADD (bank $7E)
    sep #$20
    .a8
    lda #$00
    sta f:$2183
    sta f:$4310                 ; A -> B, one register, increment
    lda #$80
    sta f:$4311                 ; $2180
    lda #^TemplateData
    sta f:$4314
    rep #$20
    .a16
    lda t5
    sta f:$4315
    sep #$20
    .a8
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    ; t1 was used as scratch: rebuild it from t5
    lda t5
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    dec a
    clc
    adc t0
    sta t1
    lda t6
    cmp t3
    beq @done
    inc t6
    jmp @r
@done:
    lda t2
    asl a
    asl a
    asl a
    sta t0
    lda t3
    asl a
    asl a
    asl a
    ora #7
    sta t1
    jmp MarkDirty

; A = template; whole text layer rows 2-11 from it
RestorePanel:
    sta t4
    stz t0
    lda #31
    sta t1
    lda #2
    sta t2
    lda #11
    sta t3
    jmp RestoreRect

InitBitmap:
    stz t4
    stz t0
    lda #31
    sta t1
    stz t2
    lda #11
    sta t3
    jmp RestoreRect

ClearInterior:
    lda #0
    jmp RestorePanel

ClearHeader:
    stz t4
    stz t0
    lda #31
    sta t1
    stz t2
    lda #1
    sta t3
    jmp RestoreRect

; command-layout columns t0..t1 of the panel
RestoreCmdCols:
    lda #1
    sta t4
    lda #2
    sta t2
    lda #11
    sta t3
    jmp RestoreRect

; ---------------------------------------------------------------- header
; left: A = text id at x 6; right: the pieces hp_* right-aligned to x 250
DrawHeader:
    pha
    jsr ClearHeader
    lda #252
    sta clip_right
    lda #6
    sta g_x
    lda #2
    sta g_y
    lda #C_WHITE
    sta g_c
    pla
    jsr DrawTextId
    lda g_x
    sta hdr_left                ; end of the left text
    ; total width of the right pieces
    stz hdr_total
    ldx #0
@w:
    cpx hp_count
    beq @wd
    phx
    jsr PieceWidth
    plx
    clc
    adc hdr_total
    sta hdr_total
    inx
    inx
    bra @w
@wd:
    lda #250
    sec
    sbc hdr_total
    sta g_x
    cmp hdr_left
    bcs :+
    inc text_clip               ; the two halves would overlap
:   ldx #0
@d:
    cpx hp_count
    beq @dd
    phx
    jsr PieceDraw
    plx
    inx
    inx
    bra @d
@dd:
    rts

; piece X: kind 0 = text id (white unless coloured), 1 = "n/m" in half-width digits, 2 = 6 px gap
PieceWidth:
    lda hp_kind,x
    bne :+
    lda hp_val,x
    jsr TextPtr
    jmp TextWidth
:   cmp #1
    bne :+
    lda #6
    sta t0
    lda hp_val,x
    phx
    jsr NumberWidth
    plx
    sta t5
    lda #6
    sta t0
    lda hp_val2,x
    jsr NumberWidth
    clc
    adc t5
    clc
    adc #6                      ; "/"
    rts
:   lda #6
    rts

PieceDraw:
    lda #C_WHITE
    sta g_c
    lda hp_kind,x
    bne :+
    lda hp_val,x
    jmp DrawTextId
:   cmp #1
    bne :+
    lda #C_GRAY
    sta g_c
    lda #.loword(HalfDigitGlyphs)
    sta p1
    lda hp_val,x
    phx
    jsr DrawNumber
    plx
    lda #GL_SLASH
    sta g_glyph
    phx
    jsr DrawGlyph
    plx
    lda g_x
    clc
    adc g_w
    sta g_x
    lda hp_val2,x
    jmp DrawNumber
:   lda g_x
    clc
    adc #6
    sta g_x
    rts

; header for the game screens: scene name, right side by mode
GameHeader:
    stz hp_count
    lda mode
    cmp #M_LIST
    beq @list
    ; the time of night
    jsr CurrentTime
    sta hp_val
    stz hp_kind
    lda #2
    sta hp_count
    jmp @draw
@list:
    ldx #0
    lda list_kind
    cmp #LK_DQCHOICE
    beq @dq
    cmp #LK_DQCLUE
    beq @dq
    cmp #LK_TOPIC
    beq @who
    cmp #LK_SHOW
    beq @who
    ; command name (or the notebook page)
    lda list_kind
    cmp #LK_ITEMS
    bne :+
    lda #TX_NOTE_ITEMS
    bra @named
:   cmp #LK_TESTI
    bne :+
    lda #TX_NOTE_TESTI
    bra @named
:   lda cmd_active
    asl a
    tay
    lda CmdTexts,y
@named:
    sta hp_val,x
    stz hp_kind,x
    inx
    inx
    bra @page
@dq:
    phx
    ldx dq_entry
    lda a:10,x                  ; the short question
    plx
    sta hp_val,x
    stz hp_kind,x
    inx
    inx
    bra @page
@who:
    lda list_kind
    cmp #LK_TOPIC
    bne :+
    lda #TX_HDR_TALK
    bra :++
:   lda #TX_HDR_SHOW
:   sta hp_val,x
    stz hp_kind,x
    inx
    inx
    lda person
    dec a
    asl a
    asl a
    asl a
    tay
    lda PersonTable,y
    sta hp_val,x
    stz hp_kind,x
    inx
    inx
@page:
    lda list_count
    cmp #LIST_ROWS+1
    bcc @back
    lda #2
    sta hp_kind,x
    inx
    inx
    lda #1
    sta hp_kind,x
    lda list_sel
    jsr DivRows
    inc a
    sta hp_val,x
    lda list_count
    clc
    adc #LIST_ROWS-1
    jsr DivRows
    sta hp_val2,x
    inx
    inx
@back:
    lda #2
    sta hp_kind,x
    inx
    inx
    lda #TX_HDR_BACK
    sta hp_val,x
    stz hp_kind,x
    inx
    inx
    stx hp_count
@draw:
    lda scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable,x
    jmp DrawHeader

; A / 5 (A < 256)
DivRows:
    ldy #0
:   cmp #LIST_ROWS
    bcc :+
    sec
    sbc #LIST_ROWS
    iny
    bra :-
:   tya
    rts

; text id of the clock in the header (first entry whose flag is set)
CurrentTime:
    ldx #0
@l:
    lda TimeTable,x
    beq @hit
    jsr TestFlag
    bne @hit
    inx
    inx
    inx
    inx
    bra @l
@hit:
    lda TimeTable+2,x
    rts

CmdTexts:
    .word TX_CMD_TALK, TX_CMD_LOOK, TX_CMD_SHOW, TX_CMD_MOVE, TX_CMD_NOTE

; ---------------------------------------------------------------- command box (left)
DrawCmdBox:
    lda #1
    sta t0
    lda #8
    sta t1
    jsr RestoreCmdCols
    lda #72
    sta clip_right
    lda list_kind
    ldx mode
    cpx #M_LIST
    bne @cmds
    cmp #LK_DQCHOICE
    beq @dq
    cmp #LK_DQCLUE
    beq @dq
@cmds:
    stz t7
@l:
    lda #CMD_LABEL_X
    sta g_x
    lda t7
    jsr RowY
    sta g_y
    lda #C_WHITE
    sta g_c
    lda mode
    cmp #M_LIST
    bne :+
    lda list_kind
    cmp #LK_TITLE
    beq :+
    lda t7
    cmp cmd_active
    bne :+
    lda #C_YELLOW
    sta g_c
:   lda t7
    asl a
    tax
    lda CmdTexts,x
    jsr DrawTextId
    inc t7
    lda t7
    cmp #5
    bne @l
    lda mode
    cmp #M_CMD
    bne :+
    jsr DrawCmdCursor
:   lda #252
    sta clip_right
    rts
@dq:
    lda #CMD_LABEL_X
    sta g_x
    lda #ROW_Y0
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #TX_CMD_DEDUCE
    jsr DrawTextId
    lda #CMD_LABEL_X
    sta g_x
    lda #ROW_Y0+ROW_PITCH
    sta g_y
    lda #C_WHITE
    sta g_c
    lda #TX_DEDUCE_Q
    jsr DrawTextId
    lda #.loword(DigitGlyphs)
    sta p1
    lda dq_index
    inc a
    jsr DrawNumber
    lda #252
    sta clip_right
    rts

; y of row A
RowY:
    sta t0
    asl a
    asl a
    asl a
    sec
    sbc t0
    asl a                       ; * 14
    clc
    adc #ROW_Y0
    rts

; clear the cursor column of the left box, then draw the cursor at cmd_sel
DrawCmdCursor:
    lda #1
    sta t0
    sta t1
    jsr RestoreCmdCols
    lda #CMD_CURSOR_X
    sta g_x
    lda cmd_sel
    jsr RowY
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #GL_CURSOR
    sta g_glyph
    jmp DrawGlyph

; ---------------------------------------------------------------- right box: prompt or list
DrawRightBox:
    lda #10
    sta t0
    lda #30
    sta t1
    jsr RestoreCmdCols
    lda #LST_RIGHT
    sta clip_right
    lda mode
    cmp #M_LIST
    beq @list
    lda #LST_LABEL_X
    sta g_x
    lda #ROW_Y0
    sta g_y
    lda #C_WHITE
    sta g_c
    lda #TX_PROMPT
    jsr DrawTextId
    lda #240
    sta clip_right
    lda #LST_CURSOR_X
    sta g_x
    lda #4
    jsr RowY
    sta g_y
    lda #C_GRAY
    sta g_c
    lda #TX_HELP
    jsr DrawTextId
    lda #252
    sta clip_right
    rts
@list:
    stz t7
@row:
    lda t7
    clc
    adc list_top
    cmp list_count
    bcs @marks
    asl a
    tax
    lda list_color,x
    sta g_c
    lda list_label,x
    pha
    lda #LST_LABEL_X
    sta g_x
    lda t7
    jsr RowY
    sta g_y
    pla
    jsr DrawTextId
    inc t7
    lda t7
    cmp #LIST_ROWS
    bne @row
@marks:
    lda #252
    sta clip_right
    lda list_top
    beq :+
    lda #MARK_X
    sta g_x
    lda #ROW_Y0
    sta g_y
    lda #C_CYAN
    sta g_c
    lda #GL_UP
    sta g_glyph
    jsr DrawGlyph
:   lda list_top
    clc
    adc #LIST_ROWS
    cmp list_count
    bcs :+
    lda #MARK_X
    sta g_x
    lda #4
    jsr RowY
    sta g_y
    lda #C_CYAN
    sta g_c
    lda #GL_DOWN
    sta g_glyph
    jsr DrawGlyph
:   jmp DrawListCursor

DrawListCursor:
    lda #10
    sta t0
    sta t1
    jsr RestoreCmdCols
    lda #LST_CURSOR_X
    sta g_x
    lda list_sel
    sec
    sbc list_top
    jsr RowY
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #GL_CURSOR
    sta g_glyph
    jmp DrawGlyph

; whole command / list screen
DrawGameScreen:
    jsr GameHeader
    lda #1
    jsr RestorePanel
    jsr DrawCmdBox
    jmp DrawRightBox

; ---------------------------------------------------------------- title screen layout
TITLE_CURSOR_X = 88
TITLE_LABEL_X = 100
TITLE_Y0 = 54
TITLE_PITCH = 17

DrawTitleList:
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
    stz t7
@l:
    lda t7
    asl a
    tax
    lda list_color,x
    sta g_c
    lda #TITLE_LABEL_X
    sta g_x
    lda t7
    jsr TitleRowY
    sta g_y
    lda list_label,x
    jsr DrawTextId
    inc t7
    lda t7
    cmp list_count
    bne @l
DrawTitleCursor:
    lda #11
    sta t0
    sta t1
    lda #6
    sta t2
    lda #11
    sta t3
    stz t4
    jsr RestoreRect
    lda #TITLE_CURSOR_X
    sta g_x
    lda list_sel
    jsr TitleRowY
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #GL_CURSOR
    sta g_glyph
    jmp DrawGlyph

TitleRowY:
    sta t0
    asl a
    asl a
    asl a
    asl a
    clc
    adc t0
    clc
    adc #TITLE_Y0
    rts

; copy the logo tiles (18 x 3) to bitmap tile rows 3-5, columns 7-24
DrawLogo:
    lda #3
    sta t0                      ; row
    ldy #0                      ; source offset
@r:
    lda t0
    xba
    asl a
    asl a                       ; row * 1024
    clc
    adc #7*32
    tax
    lda #18*16
    sta t1                      ; words per row
@w:
    lda LogoTiles,y
    sta f:BMP,x
    inx
    inx
    iny
    iny
    dec t1
    bne @w
    lda t0
    asl a
    tax
    lda BitTable,x
    ora dirty_rows
    sta dirty_rows
    inc t0
    lda t0
    cmp #6
    bne @r
    rts

; ---------------------------------------------------------------- messages
; A = text id.  Clears the panel and starts typing.
OpenMessage:
    sta msg_text                ; (for the tests: which text is on screen)
    jsr TextPtr
    lda p0
    sta msg_ptr
    lda p0+2
    sta msg_ptr+2
    inc msg_count
    lda #M_MSG
    sta mode
MsgNewPage:
    jsr ClearInterior
    lda #MSG_X0
    sta msg_x
    lda #MSG_Y0
    sta msg_y
    lda #C_WHITE
    sta msg_color
    stz msg_state
    stz msg_fast
    stz msg_timer
    stz mouth_actor             ; no speaker until the page's speaker code (after the name)
    stz mouth_pause
    rts

UpdateMsg:
    lda msg_state
    beq @typing
    ; waiting: blink the page mark, A or B goes on
    inc msg_blink
    lda msg_blink
    and #$0F
    bne :+
    jsr DrawPageMark
:   lda pad_new
    and #PAD_A|PAD_B
    beq @ret
    lda msg_state
    cmp #2
    beq @close
    lda #SFX_PAGE
    jsr PlaySfx
    jmp MsgNewPage
@close:
    jmp MessageDone
@ret:
    rts
@typing:
    lda pad_new
    and #PAD_A|PAD_B
    beq :+
    lda #1
    sta msg_fast
:   lda msg_fast
    beq :+
    lda #6
    bra :++
:   inc msg_timer
    lda msg_timer
    and #1
    beq @ret                    ; one glyph every other frame
    lda #1
:   sta t7
@glyph:
    lda #MSG_RIGHT
    sta clip_right
    ldy #0
    lda [msg_ptr],y
    inc msg_ptr
    inc msg_ptr
    cmp #$FFFF
    beq @end
    cmp #$FFFD
    beq @page
    cmp #$FFFE
    beq @nl
    cmp #$FFFC
    beq @color
    cmp #SPEAKER_CODE
    bcs @speaker
    sta g_glyph
    lda msg_x
    sta g_x
    lda msg_y
    sta g_y
    lda msg_color
    sta g_c
    stz g_drawn
    jsr DrawGlyph
    ldx g_glyph                 ; punctuation: the mouth closes for a moment (largest in this frame)
    lda GlyphPause,x
    and #$00FF
    cmp mouth_pause
    bcc :+
    sta mouth_pause
:   jsr VoiceGlyph
    lda msg_x
    clc
    adc g_w
    sta msg_x
    dec t7
    bne @glyph
    rts
@color:
    lda [msg_ptr],y
    inc msg_ptr
    inc msg_ptr
    sta msg_color
    bra @glyph
@speaker:
    and #$000F                  ; the body starts: who speaks this page
    sta mouth_actor
    stz mouth_pause
    stz voice_pause
    bra @glyph
@nl:
    lda #MSG_X0
    sta msg_x
    lda msg_y
    clc
    adc #MSG_PITCH
    sta msg_y
    brl @glyph
@page:
    lda #1
    bra :+
@end:
    lda #2
:   sta msg_state
    stz msg_blink
    lda #252
    sta clip_right
    jmp DrawPageMark

DrawPageMark:
    lda #29
    sta t0
    lda #30
    sta t1
    lda #PAGE_Y/8
    sta t2
    lda #(PAGE_Y+11)/8
    sta t3
    stz t4
    jsr RestoreRect
    lda msg_blink
    and #$10
    bne :+
    lda #PAGE_X
    sta g_x
    lda #PAGE_Y
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #GL_PAGE
    sta g_glyph
    jsr DrawGlyph
:   rts
