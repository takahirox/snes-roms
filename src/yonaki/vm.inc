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
@loop:
    lda [vp]
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
    cmp #OP_AMB+1
    bcc :+
    lda #OP_HALT
:   asl a
    tax
    jsr (OpTable,x)
    bra @loop

VmExit:
    ldx vm_sp
    txs
    rts

OpTable:
    .word OpHalt, OpText, OpBlank, OpPage, OpBg, OpSil, OpSilClear, OpBgm, OpSe, OpFx, OpSet, OpClr
    .word OpSetG, OpClrG, OpIf, OpGoto, OpChoice, OpEnd, OpChapter, OpAmb

OpHalt:
    lda #2
    jsr FadeOut
    jmp VmExit

; the screen must be on before text appears (after a chapter card without a picture)
EnsureVisible:
    lda #3
    sta reg_tm
    lda blanked
    beq :+
    lda #1
    jsr FadeIn
:   rts

; ---------------------------------------------------------------- text
; TEXT id16 lines8 <string>: page break if it does not fit, typewriter, wait mark, read mark.
OpText:
    jsr ReadW
    sta cur_text
    jsr ReadB
    sta t0
    inc paragraphs
    lda page_line
    beq :+
    clc
    adc t0
    cmp #PAGE_LINES+1
    bcc :+
    jsr ClearPage
:   lda redraw
    bne :+
    jsr EnsureVisible
:   lda #1
    sta text_on
    lda cur_text
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
    lda speed
    cmp #3
    beq @inst
    lda cur_read
    beq @pos
    lda pad
    and #PAD_B
    beq @pos
    lda #1
    sta ff
@inst:
    lda #1
    sta instant
@pos:
    lda page_line
    sta cur_line
    jsr LineY
    lda #TX0
    sta g_x
    lda #1
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
    jsr WaitFrame
    lda pad_new
    and #PAD_A
    beq :+
    lda #1
    sta instant
:   lda cur_read
    beq @frame
    lda pad
    and #PAD_B
    beq @frame
    lda #1
    sta instant
    sta ff
    bra @frame
@ctl:
    cmp #1
    bne @chunk
    inc cur_line
    lda cur_line
    jsr LineY
    lda #TX0
    sta g_x
    bra @glyph
@chunk:
    cmp #2
    bne @end
    lda [p0]                    ; line count of the next chunk
    inc p0
    jsr SetMark
    lda #GLYPH_PAGE
    sta mark_glyph
    jsr WaitAdvance
    jsr ClearPage
    lda #1
    sta text_on
    stz cur_line
    lda #0
    jsr LineY
    lda #TX0
    sta g_x
    jmp @glyph
@end:
    lda p0
    sta vp
    lda p0+2
    sta vp+2
    lda cur_line
    inc a
    sta page_line
    lda cur_text
    sta last_text
    lda redraw
    beq :+
    rts
:   jsr SetMark
    jsr NextMark
    sta mark_glyph
    jsr WaitAdvance
    lda cur_text
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
    ldy #3
    lda [p2],y
    and #$00FF
    clc
    adc t3
    cmp #PAGE_LINES+1
    bcs @page
    bra @para
@other:
    cmp #OP_BLANK
    bne :+
    lda t3
    beq @skip1
    inc t3
    bra @skip1
:   cmp #OP_PAGE
    beq @page
    cmp #OP_BG
    beq @page
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

; size of the ops NextMark may step over (0: stop there)
OpSize:
    .byte 0, 0, 1, 0, 0, 5, 1, 2, 2, 4, 3, 3, 2, 2, 0, 0, 0, 0, 0, 2

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
    jsr WaitFrame               ; fast-forward: a short look at the page
    jsr WaitFrame
    rts
:   stz blink
    stz mark_on
    jsr FlushPad
@loop:
    lda blink
    and #32
    bne @off
    lda mark_on
    bne @shown
    lda #1
    jsr DrawMark
    bra @shown
@off:
    lda mark_on
    beq @shown
    lda #0
    jsr DrawMark
@shown:
    jsr WaitFrame
    lda pad_new
    and #PAD_A
    bne @done
    lda cur_read
    beq :+
    lda pad
    and #PAD_B
    bne @done
:   lda pad_new
    and #PAD_START
    beq @loop
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
    cmp #PAGE_LINES
    bcs :+
    inc page_line
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
    sta t7                      ; options in the op
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
    sta t2                      ; lines
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
@skip:
    jsr ReadB                   ; skip the string
    cmp #0
    beq @opt
    cmp #$F0
    bcc @skip
    jsr ReadB
    bra @skip
@shown:
    lda opt_count
    bne :+
    rts                         ; nothing to choose: go on after the op
:   jsr EnsureVisible
    lda #1
    sta text_on
    ; lines needed: every option + a blank line after text
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
    sta t0
    lda page_line
    beq :+
    inc t0
:   lda page_line
    clc
    adc t0
    cmp #PAGE_LINES+1
    bcc :+
    jsr ClearPage
:   lda page_line
    beq :+
    inc page_line
:   ; draw the options
    ldx #0
@draw:
    phx
    lda page_line
    sta opt_line,x
    jsr LineY
    lda #CHOICE_X               ; the letter: A, B, ... in the order shown
    sta g_x
    lda #1
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
    lda #1
    sta g_col
    stz g_space
    jsr PrintStr
    plx
    lda page_line
    clc
    adc opt_lines,x
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
    jsr WaitFrame
    lda pad_rep
    and #PAD_UP
    beq @dn
    lda opt_count
    cmp #2
    bcc @dn
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
    lda pad_rep
    and #PAD_DOWN
    beq @a
    lda opt_count
    cmp #2
    bcc @a
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
    lda pad_new
    and #PAD_A
    bne @chosen
    lda pad_new
    and #PAD_START
    beq @loop
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
    jmp ClearPage

ShowSel:
    lda opt_sel
    asl a
    tax
    lda opt_lines,x
    pha
    lda opt_line,x
    plx
    jsr Highlight
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
    jsr LineY
    lda #TX0
    sta g_x
    lda #GLYPH_CURSOR
    sta g_glyph
    jsr DrawGlyph
    lda #1
    sta g_col
    rts

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
    ldx #gflags
    jsr BitSet
    jmp SaveGlobal
OpClrG:
    jsr ReadB
    ldx #gflags
    jsr BitClr
    jmp SaveGlobal

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
; BG pic8 mode8.  The page is cleared; the silhouettes go; SIL ops right after it are taken into the new
; picture before it is shown.
OpBg:
    jsr ReadB
    pha
    jsr ReadB
    pha
    lda #ST_BUSY
    sta ui_state
    jsr ClearPage
    stz text_on
    jsr ClearSlots
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
    pla
    asl a
    tax
    pla
    jmp (BgModes,x)

BgModes: .word BgCut, BgFade, BgWhite, BgMosaic

BgFade:
    pha
    lda #2
    jsr FadeOut
    pla
    jsr LoadPic
    stz dim_cur
    lda #2
    jmp FadeIn

BgCut:
    pha
    lda #1
    sta blanked
    jsr WaitFrame
    pla
    jsr LoadPic
    stz dim_cur
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
    stz dim_cur
    lda #2
    sta add_decay
:   jsr WaitFrame
    lda add_level
    bne :-
    rts

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
    stz dim_cur
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
FxTable: .word FxShake, FxFlash, FxRedFlash, FxRippleOn, FxRippleOff, FxDark, FxLight, FxWait

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
:   jsr WaitFrame
    lda add_level
    bne :-
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
:   jsr WaitFrame
    lda dim_cur
    cmp #31
    bne :-
    rts
FxLight:
    stz dark_on
    lda #40
    jmp WaitFrames
FxWait:
    lda #ST_BUSY
    sta ui_state
:   lda t7
    beq :+
    dec t7
    jsr WaitFrame
    lda ff
    beq :-
    lda pad
    and #PAD_B
    beq :-
:   rts

OpEnd:
    jsr ReadB
    jsr EndingScreen
    jmp VmExit

OpChapter:
    jsr ReadB
    jmp ChapterCard
