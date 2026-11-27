; ---------------------------------------------------------------- script VM (byte code of tools/yonaki/build.py)
; vp = long pointer to the next op.  An op never crosses a bank (the build ends a bank with OP_GOTO).
; RunVM runs ops until OP_END / OP_HALT / タイトルへ, which unwind to its caller (VmExit).
.a16
.i16

ReadB:
    lda [vp]
    and #$00FF
    inc vp
    rts

ReadW:
    lda [vp]
    inc vp
    inc vp
    rts

; -> t0 = address, t1 = bank
ReadAddr:
    lda [vp]
    sta t0
    inc vp
    inc vp
    lda [vp]
    and #$00FF
    sta t1
    inc vp
    rts

JumpT0:
    lda t0
    sta vp
    lda t1
    sta vp+2
    rts

RunVM:
    tsx
    stx vm_sp
    lda #1
    sta story_active
@loop:
    lda demo_quit               ; (the opening / demo: a button)
    beq :+
    jmp DemoExit
:   lda [vp]
    and #$00FF
    ldx sil_dirty
    beq @go
    cmp #OP_SIL
    beq @go
    cmp #OP_SILCLEAR
    beq @go
    jsr ApplySils
    lda [vp]
    and #$00FF
@go:
    inc vp
    cmp #OP_ASK+1
    bcc :+
    lda #OP_HALT
:   asl a
    tax
    jsr (OpTable,x)
    bra @loop

VmExit:
    stz story_active
    ldx vm_sp
    txs
    rts

OpTable:
    .word OpHalt, OpText, OpBlank, OpPage, OpBg, OpSil, OpSilClear, OpBgm, OpSe, OpFx, OpSet, OpClr
    .word OpSetG, OpClrG, OpIf, OpGoto, OpChoice, OpEnd, OpChapter, OpAmb, OpAsk

; @title or the end of the program: back to the title, which fades out what is on screen (unless it is the
; title picture: the opening ends on it)
OpHalt:
    jmp VmExit

; turn on the display before drawing text on a blanked screen
EnsureVisible:
    lda blanked
    beq :+
    lda #1
    jsr FadeIn
:   rts

; ---------------------------------------------------------------- text
; TEXT id16 lines8 [16 counts] <string>: page break if it does not fit, typewriter, wait mark, read mark.
; lines8: the lines of the first page, | $80 shown at once, | $40 the count depends on the names' lengths
; (16 counts follow, one per NameIndex).

; vp at the 16 counts -> A = the count of the names' lengths; vp after them
NameLines:
    jsr NameIndex
    txy
    lda [vp],y
    and #$00FF
    pha
    lda vp
    clc
    adc #16
    sta vp
    pla
    rts

OpText:
    lda #ST_BUSY                ; (not the wait of the paragraph before while the page clears)
    sta ui_state
    jsr ReadW
    sta cur_text
    jsr ReadB
    stz text_nowait
    bit #$80
    beq :+
    and #$7F
    inc text_nowait
:   bit #$40
    beq :+
    jsr NameLines
:   sta t0
    asl a
    adc t0                      ; tile rows (lines < 128: the shift leaves C clear)
    sta t0
    inc paragraphs
    lda page_line
    beq :+
    clc
    adc t0
    cmp #PAGE_ROWS+1
    bcc :+
    jsr ClearPage
:   lda redraw
    bne :+
    jsr EnsureVisible
:   lda cur_text
    jsr IsRead
    sta cur_read
    lda #1
    sta save_kind
    lda cur_text
    sta save_id
    stz instant
    stz ff
    lda redraw
    bne @inst
    lda text_nowait
    bne @inst
    lda speed
    cmp #3
    beq @inst
    jsr ReadSkipHeld
    beq @pos
    lda #1
    sta ff
@inst:
    lda #1
    sta instant
@pos:
    lda page_line
    sta cur_line
    jsr RowY
    lda #TX0
    sta g_x
    lda #TEXT_OUTLINE
    sta g_col
    stz g_space
    lda vp
    sta p0
    lda vp+2
    sta p0+2
    stz type_timer
    lda #ST_TYPE
    sta ui_state
@frame:
    lda instant
    beq :+
    lda #$7FFF
    bra @budget
:   ldx speed
    lda SpeedGlyphs,x
    and #$00FF
    bne @budget
    lda type_timer              ; slow: a glyph every other frame
    and #1
@budget:
    sta type_budget
    inc type_timer
    lda type_budget
    beq @wait
@glyph:
    jsr ReadCode
    bcs @ctl
    sta g_glyph
    jsr DrawGlyph
    lda g_x
    clc
    adc g_w
    sta g_x
    dec type_budget
    bne @glyph
@wait:
    ldx #WAIT_TYPING
    jsr WaitEvent
    bra @frame
@ctl:
    cmp #1
    bne @chunk
    lda cur_line
    clc
    adc #LINE_ROWS
    sta cur_line
    jsr RowY
    lda #TX0
    sta g_x
    bra @glyph
@chunk:
    cmp #2
    bne @end
    lda redraw
    bne :+
    jsr SetMark
    lda #GLYPH_PAGE
    sta mark_glyph
    jsr WaitAdvance
:   jsr ClearPage
    stz cur_line
    lda #0
    jsr RowY
    lda #TX0
    sta g_x
    lda #TEXT_OUTLINE
    sta g_col
    jmp @glyph
@end:
    lda p0
    sta vp
    lda p0+2
    sta vp+2
    lda cur_line
    clc
    adc #LINE_ROWS
    sta page_line
    lda cur_text
    sta last_text
    lda redraw
    beq :+
    rts
:   lda text_nowait
    bne :+
    jsr SetMark
    jsr NextMark
    sta mark_glyph
    jsr WaitAdvance
:   lda cur_text
    jmp MarkRead

SpeedGlyphs: .byte 0, 1, 2, 0

; the wait mark after the last glyph (g_x, g_y)
SetMark:
    lda g_x
    inc a
    cmp #229
    bcc :+
    lda #228
:   sta mark_x
    lda g_y
    sta mark_y
    rts

; p2 at a TEXT op -> A = the lines of its first page (for the names' lengths)
NextLines:
    ldy #3
    lda [p2],y
    and #$007F
    bit #$40
    beq :+
    phx
    jsr NameIndex
    txa
    plx
    clc
    adc #4
    tay
    lda [p2],y
    and #$00FF
:   rts

; A = GLYPH_PAGE when the next paragraph will start a new page (or the scene changes), else GLYPH_PARA
NextMark:
    lda vp
    sta p2
    lda vp+2
    sta p2+2
    lda page_line
    sta t3                      ; lines used, with the blank lines on the way
    ldx #24                     ; at most this many ops ahead
@op:
    dex
    beq @para
    lda [p2]
    and #$00FF
    cmp #OP_GOTO
    bne @not
    ldy #1
    lda [p2],y
    sta t0
    ldy #3
    lda [p2],y
    and #$00FF
    sta p2+2
    lda t0
    sta p2
    bra @op
@not:
    cmp #OP_TEXT
    bne @other
    jsr NextLines
    sta t0
    asl a
    adc t0                      ; tile rows
    clc
    adc t3
    cmp #PAGE_ROWS+1
    bcs @page
    bra @para
@other:
    cmp #OP_BLANK
    bne :+
    lda t3
    beq @skip1
    clc
    adc #GAP_ROWS
    sta t3
    bra @skip1
:   cmp #OP_PAGE
    beq @page
    cmp #OP_BG
    beq @bg
    cmp #OP_CHAPTER
    beq @page
    cmp #OP_END
    beq @page
    cmp #OP_HALT
    beq @page
    ; ops that show nothing: skip them
    tay
    lda OpSize,y
    and #$00FF
    beq @para                   ; (IF, CHOICE: cannot tell)
    clc
    adc p2
    sta p2
    bra @op
@skip1:
    inc p2
    bra @op
@para:
    lda #GLYPH_PARA
    rts
@page:
    lda #GLYPH_PAGE
    rts
@bg:
    ldy #2
    lda [p2],y
    and #$00FF
    cmp #BG_KEEP                ; the picture changes under the text: the page goes on
    bne @page
    lda p2
    clc
    adc #3
    sta p2
    jmp @op

; size of the ops NextMark may step over (0: stop there)
OpSize:
    .byte 0, 0, 1, 0, 0, 5, 1, 2, 2, 4, 3, 3, 2, 2, 0, 0, 0, 0, 0, 2, 0

; Wait for A with the blinking mark (mark_x, mark_y, mark_glyph).  B held over read text goes on by itself;
; START opens the menu.
WaitAdvance:
    lda #ST_WAIT
    sta ui_state
    lda ff
    beq :+
    lda pad
    and #PAD_B
    beq :+
    lda #2                      ; fast-forward: a short look at the page
    jmp WaitFrames
:   stz blink
    stz mark_on
    jsr FlushPad
@loop:
    jsr UpdateWaitMark
    ldx #WAIT_ADVANCE
    jsr WaitEvent
    cmp #PAD_START
    bne @done
    jsr OpenMenu
    lda #ST_WAIT
    sta ui_state
    bra @loop
@done:
    lda mark_on
    beq :+
    lda #0
    jsr DrawMark
:   rts

; Called before the first wait frame and after frames that received no advance or menu input.
UpdateWaitMark:
    lda blink
    and #32
    bne @off
    lda mark_on
    bne @done
    lda #1
    jmp DrawMark
@off:
    lda mark_on
    beq @done
    lda #0
    jmp DrawMark
@done:
    rts

; A = 1 draw / 0 erase the wait mark
DrawMark:
    sta mark_on
    sta g_col
    lda mark_x
    sta g_x
    lda mark_y
    sta g_y
    lda mark_glyph
    sta g_glyph
    jsr DrawGlyph
    lda #1
    sta g_col
    rts

OpBlank:
    lda page_line
    beq :+
    cmp #PAGE_ROWS
    bcs :+
    clc
    adc #GAP_ROWS
    sta page_line
:   rts

OpPage:
    lda page_line
    beq :+
    jsr ClearPage
:   rts

; ---------------------------------------------------------------- choices
; CHOICE id16 n8 { nconds8 cond16* addr24 lines8 <string> }*n
OpChoice:
    jsr ReadW
    sta choice_id
    jsr ReadB
    stz choice_inline
    bit #$80
    beq :+
    and #$7F
    inc choice_inline           ; inline: the options are the next sentence; the one chosen stays as text
:   sta t7                      ; options in the op
    stz opt_count
@opt:
    lda t7
    bne :+
    jmp @shown
:   dec t7
    jsr ReadB
    sta g_pad                   ; conditions
    lda #1
    sta g_row                   ; visible
@cond:
    lda g_pad
    beq @addr
    dec g_pad
    jsr ReadW
    jsr TestCond
    bne @cond
    stz g_row
    bra @cond
@addr:
    jsr ReadAddr
    jsr ReadB
    bit #$40
    beq :+
    jsr NameLines
:   sta t2                      ; lines
    lda opt_count
    asl a
    tax
    lda g_row
    beq @skip
    lda t0
    sta opt_addr,x
    lda t1
    sta opt_bank,x
    lda vp
    sta opt_text,x
    lda vp+2
    sta opt_tbank,x
    lda t2
    sta opt_lines,x
    inc opt_count
@skip:                          ; past the string
    lda vp
    sta p0
    lda vp+2
    sta p0+2
:   jsr ReadCode
    bcc :-
    cmp #0
    bne :-
    lda p0
    sta vp
    bra @opt
@shown:
    lda opt_count
    bne :+
    rts                         ; nothing to choose: go on after the op
:   jsr EnsureVisible
    ; tile rows needed: every option + the gap after text
    lda opt_count
    asl a
    sta t1
    ldx #0
    lda #0
:   clc
    adc opt_lines,x
    inx
    inx
    cpx t1
    bne :-
    sta opt_sum
    asl a
    adc opt_sum                 ; lines * LINE_ROWS
    sta opt_sum
    lda page_line
    beq @fits                   ; (the build checks that the options fit an empty page)
    clc
    adc #GAP_ROWS
    adc opt_sum
    cmp #CHOICE_ROWS+1
    bcc @fits
    jsr ChoicePage
    lda page_line
    beq @fits
    clc
    adc #GAP_ROWS
    adc opt_sum
    cmp #CHOICE_ROWS+1
    bcc @fits
    jsr ClearPage
@fits:
    lda page_line
    beq :+
    clc
    adc #GAP_ROWS
    sta page_line
:   ; draw the options
    ldx #0
@draw:
    phx
    lda page_line
    sta opt_line,x
    jsr RowY
    lda #CHOICE_X               ; the letter: A, B, ... in the order shown
    sta g_x
    lda #TEXT_OUTLINE
    sta g_col
    txa
    lsr a
    clc
    adc #GLYPH_OPT_A
    sta g_glyph
    jsr DrawGlyph
    plx
    phx
    lda #OPT_TEXT_X
    sta g_x
    lda opt_text,x
    sta p0
    lda opt_tbank,x
    sta p0+2
    stz g_space
    lda #LINE_PX
    sta str_lh
    jsr PrintStrLH
    plx
    lda opt_lines,x
    sta t0
    asl a
    adc t0                      ; tile rows
    clc
    adc page_line
    sta page_line
    inx
    inx
    txa
    lsr a
    cmp opt_count
    bcc @draw
    lda #2
    sta save_kind
    lda choice_id
    sta save_id
    stz opt_sel
    jsr ShowSel
    jsr FlushPad
@loop:
    lda #ST_CHOICE
    sta ui_state
    ldx #WAIT_CHOICE
    jsr WaitEvent
    cmp #PAD_UP
    bne @dn
    jsr HideSel
    lda opt_sel
    bne :+
    lda opt_count
:   dec a
    sta opt_sel
    jsr ShowSel
    jsr SndCursor
    bra @loop
@dn:
    cmp #PAD_DOWN
    bne @a
    jsr HideSel
    lda opt_sel
    inc a
    cmp opt_count
    bcc :+
    lda #0
:   sta opt_sel
    jsr ShowSel
    jsr SndCursor
    bra @loop
@a:
    cmp #PAD_A
    beq @chosen
    jsr OpenMenu
    bra @loop
@chosen:
    jsr SndOk
    lda opt_sel
    asl a
    tax
    lda opt_addr,x
    sta vp
    lda opt_bank,x
    sta vp+2
    jsr HideSel
    lda choice_inline
    bne :+
    jmp ClearPage
:   lda opt_line                ; inline: the options (and the gap before them) go, the text above stays
    beq :+
    sec
    sbc #GAP_ROWS
:   sta page_line
    jmp ClearFrom

; The options do not fit under the text: a new page.  Inline options are the next sentence of the paragraph
; before them, so that paragraph is drawn again at the top (as a bookmark resume does).
ChoicePage:
    lda last_text
    pha
    jsr ClearPage
    pla
    ldx choice_inline
    beq @r
    cmp #$FFFF
    beq @r
    ldx vp
    phx
    ldx vp+2
    phx
    jsr TextAddr
    inc vp                      ; past the opcode
    lda #1
    sta redraw
    jsr OpText
    stz redraw
    plx
    stx vp+2
    plx
    stx vp
@r: rts

ShowSel:
    lda opt_sel
    asl a
    tax
    lda opt_lines,x
    sta t0
    asl a
    adc t0                      ; tile rows
    pha
    lda opt_line,x
    plx
    jsr HighlightRows
    lda #1
    bra SelCursor
HideSel:
    jsr ClearHighlight
    lda #0
SelCursor:
    sta g_col
    lda opt_sel
    asl a
    tax
    lda opt_line,x
    jsr RowY
    lda #TX0
    sta g_x
    lda #GLYPH_CURSOR
    sta g_glyph
    jsr DrawGlyph
    lda #1
    sta g_col
    rts

; ---------------------------------------------------------------- the name of someone, typed (@ask)
; ASK n8 { len8 glyph16*len addr24 }*n default_addr24 <question string>
; The player types a name on the name entry grid (AskEntry); the first answer spelled exactly so is taken,
; else the default.
OpAsk:
    lda demo_on                 ; the demo stops before anything the player answers or keeps
    beq :+
    jmp DemoExit
:   jsr ReadB
    sta ask_n
    sta t7
    lda vp
    sta ask_tbl
    lda vp+2
    sta ask_tbl+2
@skip:
    lda t7
    beq @def
    dec t7
    jsr ReadB                   ; glyphs in the answer
    asl a
    clc
    adc #3
    adc vp
    sta vp
    bra @skip
@def:
    jsr ReadAddr
    lda t0
    pha
    lda t1
    pha
    lda vp
    sta ask_prompt
    lda vp+2
    sta ask_prompt+2
    jsr EnsureVisible
    jsr AskEntry
    lda ask_tbl
    sta p2
    lda ask_tbl+2
    sta p2+2
    lda ask_n
    sta t7
@cmp:
    lda t7
    beq @nomatch
    dec t7
    lda [p2]
    and #$00FF
    sta t3                      ; glyphs
    inc p2
    cmp names+20
    bne @next
    ldy #0
@g:
    tya
    lsr a
    cmp t3
    beq @match
    tyx
    lda [p2],y
    cmp names+22,x
    bne @next
    iny
    iny
    bra @g
@next:
    lda t3
    asl a
    clc
    adc #3
    adc p2
    sta p2
    bra @cmp
@match:
    lda t3
    asl a
    tay
    lda [p2],y
    sta t0
    iny
    iny
    lda [p2],y
    and #$00FF
    sta t1
    pla
    pla
    jmp JumpT0
@nomatch:
    pla
    sta t1
    pla
    sta t0
    jmp JumpT0

; ---------------------------------------------------------------- flags
; A = condition word (bit 15 negated, bit 14 global: index < 32 global flag, 32.. ending seen) -> A = 0/1, Z
TestCond:
    sta t5
    and #$3FFF
    sta t6
    lda t5
    and #$4000
    bne @glob
    lda t6
    ldx #lflags
    bra @test
@glob:
    lda t6
    cmp #32
    bcs @end
    ldx #gflags
    bra @test
@end:
    sbc #32
    ldx #gendings
@test:
    jsr BitTest
    ldx t5
    bpl :+
    eor #1
:   cmp #0
    rts

; A = index, X = address of the bit array (bank 0) -> A = 0/1
BitTest:
    sta t4
    lsr a
    lsr a
    lsr a
    stx t3
    clc
    adc t3
    tax
    lda t4
    and #7
    tay
    sep #$20
    .a8
    lda 0,x
    and BitMask8,y
    rep #$20
    .a16
    beq :+
    lda #1
:   and #$00FF
    rts

; A = index, X = array: set / clear
BitSet:
    jsr BitAddr
    sep #$20
    .a8
    lda 0,x
    ora BitMask8,y
    sta 0,x
    rep #$20
    .a16
    rts
BitClr:
    jsr BitAddr
    sep #$20
    .a8
    lda BitMask8,y
    eor #$FF
    and 0,x
    sta 0,x
    rep #$20
    .a16
    rts
BitAddr:
    sta t4
    lsr a
    lsr a
    lsr a
    stx t3
    clc
    adc t3
    tax
    lda t4
    and #7
    tay
    rts

BitMask8: .byte $01, $02, $04, $08, $10, $20, $40, $80

OpSet:
    jsr ReadW
    ldx #lflags
    jmp BitSet
OpClr:
    jsr ReadW
    ldx #lflags
    jmp BitClr
OpSetG:
    jsr ReadB
    ldx demo_on                 ; (the demo keeps no global flag)
    bne @r
    ldx #gflags
    jsr BitSet
    jmp SaveGlobal
@r:
    rts
OpClrG:
    jsr ReadB
    ldx demo_on
    bne @r
    ldx #gflags
    jsr BitClr
    jmp SaveGlobal
@r:
    rts

OpIf:
    jsr ReadW
    pha
    jsr ReadAddr
    pla
    jsr TestCond
    beq :+
    jmp JumpT0
:   rts

OpGoto:
    jsr ReadAddr
    jmp JumpT0

; ---------------------------------------------------------------- pictures, silhouettes, effects
; BG pic8 mode8.  The page is cleared (but by BG_KEEP: the picture changes under the text); the darkness of
; @fx dark ends (the new scene is seen); the silhouettes go; SIL ops right after it are taken into the new
; picture before it is shown.
OpBg:
    jsr ReadB
    pha
    jsr ReadB
    pha
    lda #ST_BUSY
    sta ui_state
    stz dark_on
    lda 1,s
    cmp #BG_KEEP
    beq :+
    jsr ClearPage
:   jsr ClearSlots
@peek:
    lda [vp]
    and #$00FF
    cmp #OP_SIL
    bne :+
    inc vp
    jsr OpSil
    bra @peek
:   cmp #OP_SILCLEAR
    bne :+
    inc vp
    jsr ClearSlots
    bra @peek
:   stz sil_dirty
    lda 1,s                     ; mode | frames a fade step << 4 (0: 2)
    lsr a
    lsr a
    lsr a
    lsr a
    bne :+
    lda #2
:   sta fade_step
    pla
    and #$000F
    asl a
    tax
    pla
    jmp (BgModes,x)

BgModes: .word BgCut, BgFade, BgWhite, BgMosaic, BgKeep

; a cut of the camera inside the scene: the photo goes dark under the text, the new one comes up under it
BgKeep:
    pha
    lda blanked                 ; from black: a plain fade
    beq :+
    pla
    bra BgFade
:   lda #1
    sta dark_on
    ldx #WAIT_DIM
    jsr WaitEvent
    pla
    jsr LoadPic
    stz dark_on
    rts

BgFade:
    pha
    lda fade_step
    jsr FadeOut
    pla
    jsr LoadPic
    lda fade_step
    jmp FadeIn

BgCut:
    pha
    lda #1
    sta blanked
    jsr WaitFrame
    pla
    jsr LoadPic
    lda #15
    sta bright
    stz blanked
    jmp WaitFrame

BgWhite:
    pha
    lda blanked                 ; from black: a plain fade
    beq :+
    pla
    bra BgFade
:   stz add_red
    stz add_decay
@up:
    lda add_level
    clc
    adc #3
    cmp #31
    bcc :+
    lda #31
:   sta add_level
    jsr WaitFrame
    lda add_level
    cmp #31
    bcc @up
    pla
    jsr LoadPic
    lda #2
    sta add_decay
    ldx #WAIT_FLASH
    jmp WaitEvent

BgMosaic:
    pha
    lda blanked
    beq :+
    pla
    bra BgFade
:   lda #1
    sta mosaic
:   lda #2
    jsr WaitFrames
    inc mosaic
    lda mosaic
    cmp #15
    bcc :-
    lda #1
    jsr FadeOut
    pla
    jsr LoadPic
    stz bright
    stz blanked
:   lda #2
    jsr WaitFrames
    inc bright
    lda #15
    sec
    sbc bright
    sta mosaic
    lda bright
    cmp #15
    bcc :-
    stz mosaic
    rts

; SIL key8 sil8 x8 colour8 (sil $FF: remove that key)
OpSil:
    jsr ReadB
    sta t2                      ; key
    jsr ReadB
    sta t3                      ; silhouette
    jsr ReadB
    sta g_pad                   ; x
    jsr ReadB
    sta g_row                   ; colour
    lda t2
    jsr FindSlot
    lda #0
    rol a
    sta t4                      ; 1: the key is not shown
    lda t3
    cmp #$FF
    bne @put
    lda t4
    bne :+                      ; not shown: nothing to do
    lda #$FFFF
    sta sil_key,x
    lda #1
    sta sil_dirty
:   rts
@put:
    lda t2
    sta sil_key,x
    lda t3
    sta sil_id,x
    lda g_pad
    sta sil_x,x
    lda g_row
    sta sil_col,x
    lda #1
    sta sil_dirty
    rts

OpSilClear:
    jsr ClearSlots
    lda #1
    sta sil_dirty
    rts

OpBgm:
    jsr ReadB
    cmp #$FE
    bne :+
    lda #$FFFF
    sta music_cur
    lda #SND_STOP
    jmp SndQueue
:   cmp #$FF
    bne :+
    lda #$FFFF
    sta music_cur
    lda #SND_FADE
    jmp SndQueue
:   cmp #$FD
    beq :+
    jmp PlayMusic
:   rts

OpSe:
    jsr ReadB
    cmp #$FF
    beq :+
    jmp SndQueue
:   rts

OpAmb:
    jsr ReadB
    cmp #$FE
    beq @r
    cmp #$FF
    bne :+
    lda #$FFFF
    sta amb_cur
    lda #SND_AMB_OFF
    jmp SndQueue
:   cmp amb_cur
    beq @r
    sta amb_cur
    clc
    adc #SND_AMB
    jmp SndQueue
@r: rts

; FX kind8 arg16
OpFx:
    jsr ReadB
    pha
    jsr ReadW
    sta t7
    pla
    asl a
    tax
    jmp (FxTable,x)
FxTable: .word FxShake, FxFlash, FxRedFlash, FxRippleOn, FxRippleOff, FxDark, FxLight, FxWait, FxOut

FxShake:
    lda #24
    sta shake
    lda #24
    jmp WaitFrames
FxFlash:
    stz add_red
    bra :+
FxRedFlash:
    lda #1
    sta add_red
:   lda #31
    sta add_level
    lda #2
    sta add_decay
    ldx #WAIT_FLASH
    jsr WaitEvent
    stz add_red
    rts
FxRippleOn:
    lda #1
    sta ripple_on
    rts
FxRippleOff:
    stz ripple_on
    rts
FxDark:
    lda #1
    sta dark_on
    ldx #WAIT_DIM
    jmp WaitEvent
FxLight:
    stz dark_on
    lda #40
    jmp WaitFrames
FxWait:
    lda #ST_BUSY
    sta ui_state
    lda t7
    ldx #WAIT_SKIP
    jmp WaitTimedEvent
FxOut:                          ; to black, arg frames a step (the next @bg fades in from it)
    lda t7
    jmp FadeOut

OpEnd:
    lda demo_on
    beq :+
    jmp DemoExit
:   jsr ReadB
    jsr EndingScreen
    jmp VmExit

OpChapter:
    jsr ReadB
    sta chapter_cur             ; retain the chapter label for bookmarks
    rts
