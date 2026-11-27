; ---------------------------------------------------------------- text bitmap (BG2, 2bpp)
; Bitmap coordinates x 0-239 (screen 8-247), y 0-191 (screen 16-207).  Byte of (x, y):
; (y >> 3) * 480 + (x >> 3) * 16 + (y & 7) * 2 (+1 for plane 1).  Colours: 1 white (plane 0), 2 shadow
; (plane 1), 3 grey (both).  Story text uses a one-pixel outline; other glyphs use a shadow one pixel
; right, down and diagonal.  The shadow never covers existing ink, and ink always covers shadow.
; Encoded strings (tools/yonaki/build.py Encoder): $00 end, $01 new line, $02 page chunk, $03 / $04 the names
; (主人公, ヒロイン), $05 / $06 + word: a new line / page chunk when the mask has the bit of the names' lengths
; (NameMask), $10-$EF glyph 0-223, $F0-$FF + byte: glyph 224 + 12-bit value.
.a16
.i16

; whole page: bitmap zero (DMA from a fixed zero), every row dirty, no highlight, page_line 0
ClearPage:
    jsr PacedWait               ; 11.5 KiB of DMA (about 70 lines): at the top of a frame
    lda #.loword(BMP)
    sta WMADDL
    sep #$20
    .a8
    lda #^BMP & 1
    sta WMADDH
    lda #$08
    sta DMAP1
    lda #<WMDATA
    sta BBAD1
    ldx #.loword(ZeroWord)
    stx A1T1L
    lda #^ZeroWord
    sta A1B1
    ldx #BMP_SIZE
    stx DAS1L
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    lda #$FFFF
    sta text_dirty
    lda #$00FF
    sta text_dirty+2
    jsr ClearHighlight
    stz page_line
    stz mark_on
    lda #$FFFF
    sta last_text
    rts

; A = tile row: the bitmap from that row down zeroed (the text above stays), page_line = A, no highlight
ClearFrom:
    sta page_line
    jsr PacedWait               ; a WRAM DMA of up to 11.5 KiB: at the top of a frame (the frame uses t0-t2)
    lda page_line
    sta t0
    xba                         ; * 256
    asl a                       ; * 512
    sta t1
    lda t0
    asl a
    asl a
    asl a
    asl a
    asl a                       ; * 32
    eor #$FFFF
    sec
    adc t1                      ; row * 480 = row * 512 - row * 32
    sta t1                      ; byte offset in the bitmap
    lda #BMP_SIZE
    sec
    sbc t1
    beq @done
    sta t2                      ; bytes to clear
    lda #.loword(BMP)
    clc
    adc t1
    sta WMADDL
    sep #$20
    .a8
    lda #^BMP & 1
    sta WMADDH
    lda #$08
    sta DMAP1
    lda #<WMDATA
    sta BBAD1
    ldx #.loword(ZeroWord)
    stx A1T1L
    lda #^ZeroWord
    sta A1B1
    ldx t2
    stx DAS1L
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    lda #$FFFF                  ; every row up again (the rows above are unchanged)
    sta text_dirty
    lda #$00FF
    sta text_dirty+2
@done:
    jsr ClearHighlight
    stz mark_on
    rts

; A = menu line (16 px apart) -> g_y
LineY:
    asl a
; A = tile row -> g_y
RowY:
    asl a
    asl a
    asl a
    clc
    adc #TY0
    sta g_y
    rts

; ---------------------------------------------------------------- highlight (BG2 map palette 1)
; A = first menu line, X = number of lines (each two tile rows)
Highlight:
    asl a
    pha
    txa
    asl a
    tax
    pla
; A = first tile row, X = number of tile rows
HighlightRows:
    sta hl_line
    stx hl_count
    lda #$0400
    bra SetLinePal
ClearHighlight:
    lda hl_line
    cmp #$FFFF
    beq @r
    lda #0
    jsr SetLinePal
    lda #$FFFF
    sta hl_line
@r: rts

; A = palette bits ($0000 / $0400) for the map rows of tile rows hl_line .. + hl_count
SetLinePal:
    sta t3
    lda hl_line
    clc
    adc #2                      ; map row of the first tile row
    sta t0
    lda hl_count
    sta t1                      ; map rows
@row:
    lda t0
    asl a
    asl a
    asl a
    asl a
    asl a
    inc a                       ; column 1
    asl a
    tax
    ldy #30
:   lda f:MAPBUF,x
    and #$E3FF
    ora t3
    sta f:MAPBUF,x
    inx
    inx
    dey
    bne :-
    inc t0
    dec t1
    bne @row
    lda #1
    sta map_dirty
    rts

; ---------------------------------------------------------------- glyphs
TEXT_OUTLINE = 2                ; white ink with a dark outline, using the story text margins

; Draw g_glyph at g_x, g_y.  g_col: 0 erase, 1 white, TEXT_OUTLINE outlined white, 3 grey.
; Outlined text starts at least one pixel inside the top/left of the bitmap.  Sets g_w (advance).
DrawGlyph:
    lda glyph_count
    cmp #GLYPHS_PER_FRAME
    bcc :+
    jsr PacedWait
:   inc glyph_count
    lda g_glyph
    and #$03FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora #$8000
    sta p1
    lda g_glyph
    xba
    lsr a
    lsr a
    and #$003F
    clc
    adc #FONT_BANK
    sta p1+2
    ldy #24
    lda [p1],y
    and #$00FF
    sta g_w
    lda g_x
    clc
    adc g_w
    cmp #241
    bcc :+
    inc text_clip
    rts
:   lda g_y
    cmp #192-12
    bcc :+
    inc text_clip
    rts
:   lda g_glyph
    cmp #GLYPH_COUNT
    bcc :+
    rts
:   ; the outlined footprint starts one pixel above and to the left of the ink
    lda g_x
    sta t1
    lda g_y
    ldx g_col
    cpx #TEXT_OUTLINE
    bne :+
    dec t1
    dec a
:   sta g_row
    lda t1
    and #7
    xba
    asl a                       ; shift * 512: ShiftTable offset
    sta g_shift
    ; dirty rows (both styles reach through g_y + 12)
    lda g_y
    clc
    adc #12
    lsr a
    lsr a
    lsr a
    tax
    lda g_row
    lsr a
    lsr a
    lsr a
    jsr MarkTextRows
    ; address of the first byte
    lda g_row
    lsr a
    lsr a
    lsr a
    sta t0
    asl a
    asl a
    asl a
    asl a
    sec
    sbc t0
    asl a
    asl a
    asl a
    asl a
    asl a                       ; (y >> 3) * 480
    sta g_addr
    lda t1
    lsr a
    lsr a
    lsr a
    sta t1                      ; column
    asl a
    asl a
    asl a
    asl a
    clc
    adc g_addr
    sta g_addr
    lda g_row
    and #7
    sta g_row
    asl a
    clc
    adc g_addr
    sta g_addr
    lda #BMP_COLS
    sec
    sbc t1
    sta t2                      ; byte columns available (1..30)
    stz g_prev
    stz g_cur
    ldy #0                      ; glyph row * 2
@row:
    cpy #24
    bcc :+
    lda #0
    bra :++
:   lda [p1],y
:   ldx g_col
    cpx #TEXT_OUTLINE
    beq @outline
    sta t1                      ; ink in the current row
    lsr a
    ora g_prev
    sta t0
    lda g_prev
    lsr a
    ora t0
    sta t0
    lda t1
    sta g_prev
    bra @mask
@outline:
    ; Combine three rows of ink, then expand left and right.  The footprint starts at x - 1,
    ; so the original column positions are restored by shifting the middle row right once.
    sta t1                      ; next row
    ora g_prev
    ora g_cur
    sta t0
    lsr a
    ora t0
    sta t0
    lsr a
    ora t0
    sta t0
    lda g_cur
    sta g_prev
    lda t1
    sta g_cur
    lda g_prev
    lsr a
    sta t1
@mask:
    eor #$FFFF
    and t0
    sta t0                      ; shadow S
    ora t1
    bne :+
    jmp @next
:   ; spread W and S over three bytes, shifted right (ShiftTable[s][v] = v << 8 >> s)
    lda t1
    xba
    and #$00FF
    asl a
    ora g_shift
    tax
    lda ShiftTable,x
    sta t6
    lda t1
    and #$00FF
    asl a
    ora g_shift
    tax
    lda ShiftTable,x
    sep #$20
    .a8
    sta g_w2
    xba
    ora t6
    sta g_w1
    lda t6+1
    sta g_w0
    rep #$20
    .a16
    lda t0+1
    and #$00FF
    asl a
    ora g_shift
    tax
    lda ShiftTable,x
    sta t6
    lda t0
    and #$00FF
    asl a
    ora g_shift
    tax
    lda ShiftTable,x
    sep #$20
    .a8
    sta g_s2
    xba
    ora t6
    sta g_s1
    lda t6+1
    sta g_s0
@nosh:
    ldx g_addr
    lda g_w0
    sta t4
    lda g_s0
    sta t4+1
    jsr @byte
    lda t2
    cmp #2
    bcc @wrote
    rep #$20
    .a16
    lda g_addr
    clc
    adc #16
    tax
    sep #$20
    .a8
    lda g_w1
    sta t4
    lda g_s1
    sta t4+1
    jsr @byte
    lda t2
    cmp #3
    bcc @wrote
    rep #$20
    .a16
    lda g_addr
    clc
    adc #32
    tax
    sep #$20
    .a8
    lda g_w2
    sta t4
    lda g_s2
    sta t4+1
    jsr @byte
@wrote:
    rep #$20
    .a16
@next:
    lda g_row
    inc a
    cmp #8
    bcc :+
    lda g_addr
    clc
    adc #BMP_ROW-14
    sta g_addr
    lda #0
    bra :++
:   inc g_addr
    inc g_addr
:   sta g_row
    iny
    iny
    cpy #26
    bcc @more
    bne @done
    lda g_col
    cmp #TEXT_OUTLINE
    bne @done
@more:
    jmp @row
@done:
    rts

; one byte column: t4 = white bits, t4+1 = shadow bits, X = bitmap offset (8-bit A)
.a8
@byte:
    lda t4
    ora t4+1
    beq @bx
    lda g_col
    beq @erase
    cmp #3
    beq @grey
    ; white: plane 1 loses the white bits and gains the shadow where plane 0 is clear
    lda f:BMP,x
    eor #$FF
    and t4+1
    sta t5
    lda t4
    eor #$FF
    and f:BMP+1,x
    ora t5
    sta f:BMP+1,x
    lda f:BMP,x
    ora t4
    sta f:BMP,x
@bx:
    rts
@grey:
    lda f:BMP,x
    eor #$FF
    and t4+1
    ora t4
    ora f:BMP+1,x
    sta f:BMP+1,x
    lda f:BMP,x
    ora t4
    sta f:BMP,x
    rts
@erase:
    lda t4
    ora t4+1
    eor #$FF
    sta t5
    and f:BMP,x
    sta f:BMP,x
    lda t5
    and f:BMP+1,x
    sta f:BMP+1,x
    rts
.a16

; ---------------------------------------------------------------- strings
; [p0] -> next code.  Carry clear: A = glyph.  Carry set: A = control byte (0 end, 1 new line, 2 chunk).
; $03 / $04 are the names the player set: their glyphs come one per call (name_left, name_pos).
ReadCode:
    lda name_left
    bne @name
    lda [p0]
    and #$00FF
    inc p0
    cmp #$10
    bcc @ctl
    cmp #$F0
    bcs @two
    sec
    sbc #$10
    clc
    rts
@two:
    and #$000F
    xba
    sta t6
    lda [p0]
    and #$00FF
    inc p0
    ora t6
    clc
    adc #224
    clc
    rts
@ctl:
    cmp #5
    bcs @cond
    cmp #3
    bcc @ctl_ret
    phx
    ldx #0
    cmp #3
    beq :+
    ldx #10
:   lda names,x                 ; length (1..NAME_MAX)
    sta name_left
    inx
    inx
    stx name_pos
    plx
@name:
    phx
    ldx name_pos
    lda names,x
    inx
    inx
    stx name_pos
    plx
    dec name_left
    clc
    rts
@ctl_ret:
    sec
    rts
@cond:                          ; $05 / $06 + mask: a break of some name lengths
    sbc #4                      ; (carry set) 1 new line, 2 chunk
    pha
    phx
    jsr NameMask
    plx
    and [p0]
    sta t6
    inc p0
    inc p0
    lda t6
    beq :+
    pla
    sec
    rts
:   pla
    jmp ReadCode                ; not for these names

; X = the variant of the names' lengths (tools/yonaki/script.py NAME_LENS): (hero - 1) * 4 + (heroine - 1)
.assert NAME_MAX = 4, error, "NameIndex assumes four lengths a name"
NameIndex:
    lda names                   ; lengths 1..NAME_MAX
    dec a
    asl a
    asl a
    clc
    adc names+10
    dec a
    tax
    rts

; A = the bit of NameIndex in a $05 / $06 mask
NameMask:
    jsr NameIndex
    lda #1
:   dex
    bmi :+
    asl a
    bra :-
:   rts

; Draw the string at p0 from g_x, g_y (a new line goes back to str_x0 and 16 px down).  p0 ends after it.
PrintStr:
    lda #16
    sta str_lh
; the same with str_lh px between lines
PrintStrLH:
    lda g_x
    sta str_x0
@l:
    jsr ReadCode
    bcs @ctl
    sta g_glyph
    jsr DrawGlyph
    lda g_x
    clc
    adc g_w
    adc g_space
    sta g_x
    bra @l
@ctl:
    cmp #1
    bne @end
    lda str_x0
    sta g_x
    lda g_y
    clc
    adc str_lh
    sta g_y
    bra @l
@end:
    rts

; width in px of the first line of the string at p0 (p0 kept) -> A
StrWidth:
    lda p0
    pha
    lda p0+2
    pha
    stz t3
@l:
    jsr ReadCode
    bcs @end
    sta g_glyph
    lda g_glyph
    and #$03FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora #$8000
    clc
    adc #24
    sta p1
    lda g_glyph
    xba
    lsr a
    lsr a
    and #$003F
    clc
    adc #FONT_BANK
    sta p1+2
    lda [p1]
    and #$00FF
    clc
    adc g_space
    adc t3
    sta t3
    bra @l
@end:
    pla
    sta p0+2
    pla
    sta p0
    lda t3
    sec
    sbc g_space
    bpl :+
    lda #0
:   rts

; A = string address in bank 0: centre it on the line at g_y
PrintCentered:
    sta p0
    lda #^Str_new
    sta p0+2
    jsr StrWidth
    sta t0
    lda #240
    sec
    sbc t0
    lsr a
    sta g_x
    jmp PrintStr

; A = string address in bank 0 -> drawn at g_x, g_y
PrintRom:
    sta p0
    lda #^Str_new
    sta p0+2
    jmp PrintStr

; draw glyph A at g_x, g_y (g_x advances)
PutGlyph:
    sta g_glyph
    jsr DrawGlyph
    lda g_x
    clc
    adc g_w
    sta g_x
    rts

; A = 0-99: two half-width digits at g_x, g_y
PutNum2:
    ldx #0
:   cmp #10
    bcc :+
    sbc #10
    inx
    bra :-
:   pha
    txa
    jsr PutDigit
    pla
PutDigit:
    tax
    lda DigitCodes,x
    and #$00FF
    sec
    sbc #$10
    jmp PutGlyph

; A = 0-99: digits without a leading zero
PutNum:
    cmp #10
    bcs PutNum2
    jmp PutDigit

; ---------------------------------------------------------------- 2bpp tile images
; Copy OWARI_W x OWARI_H tiles (OwariTiles) to bitmap tile column t0, tile row t1.
BlitOwari:
    lda t1
    sta t2
    clc
    adc #OWARI_H-1
    tax
    lda t1
    jsr MarkTextRows
    ldy #0                      ; source offset
    lda #OWARI_H
    sta t3
@row:
    lda t2
    sta t4
    asl a
    asl a
    asl a
    asl a
    sec
    sbc t4
    asl a
    asl a
    asl a
    asl a
    asl a
    sta t4
    lda t0
    asl a
    asl a
    asl a
    asl a
    clc
    adc t4
    tax
    lda #OWARI_W*16/2
    sta t4
:   lda OwariTiles,y
    sta f:BMP,x
    inx
    inx
    iny
    iny
    dec t4
    bne :-
    inc t2
    dec t3
    bne @row
    rts
