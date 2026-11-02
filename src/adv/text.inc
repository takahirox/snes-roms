; ---------------------------------------------------------------- text bitmap (BG2, 4bpp)
; Bitmap coordinates: x 0-255, y 0-95 (rows 0-15 = header, 16-95 = screen 144-223).
; Byte offset of (x, y): (y >> 3) * 1024 + (x >> 3) * 32 + (y & 7) * 2, planes 0/1 at +0/+1, 2/3 at +16/+17.
; The panel background is colour 1 (plane 0 set).  Glyphs are drawn on that background: plane 0 is
; cleared where the colour has bit 0 clear, planes 1-3 are set where the colour has the bit.
.a16
.i16

; mark tile rows t0 (first y) .. t1 (last y) dirty
MarkDirty:
    lda t0
    lsr a
    lsr a
    lsr a
    tax
    lda t1
    lsr a
    lsr a
    lsr a
    sta t2
@l:
    txa
    asl a
    tay
    lda BitTable,y
    ora dirty_rows
    sta dirty_rows
    cpx t2
    beq @d
    inx
    bra @l
@d:
    rts

; Fill tile columns t0..t1, pixel rows t2..t3 with the panel colour.
ClearRect:
    lda t2
    sta t4
@row:
    lda t4
    and #$FFF8
    xba
    lsr a                       ; (y >> 3) * 1024
    sta t5
    lda t4
    and #7
    asl a
    clc
    adc t5
    sta t5
    lda t0
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc t5
    tax
    lda t1
    sec
    sbc t0
    inc a
    tay
@col:
    lda #$00FF
    sta f:BMP,x
    lda #$0000
    sta f:BMP+16,x
    txa
    clc
    adc #32
    tax
    dey
    bne @col
    lda t4
    cmp t3
    beq @done
    inc t4
    bra @row
@done:
    lda t2
    sta t0
    lda t3
    sta t1
    jmp MarkDirty

; Plot one pixel: t0 = x, t1 = y, t2 = colour (all four planes written).
Plot:
    lda t1
    and #$FFF8
    xba
    lsr a
    sta t3
    lda t1
    and #7
    asl a
    clc
    adc t3
    sta t3
    lda t0
    and #$FFF8
    asl a
    asl a
    clc
    adc t3
    tax
    lda t0
    and #7
    tay
    sep #$20
    .a8
    lda PixelBit,y
    sta g_m0
    eor #$FF
    sta g_m1
    lda t2
    lsr a
    bcc :+
    lda f:BMP,x
    ora g_m0
    bra :++
:   lda f:BMP,x
    and g_m1
:   sta f:BMP,x
    lda t2
    and #2
    beq :+
    lda f:BMP+1,x
    ora g_m0
    bra :++
:   lda f:BMP+1,x
    and g_m1
:   sta f:BMP+1,x
    lda t2
    and #4
    beq :+
    lda f:BMP+16,x
    ora g_m0
    bra :++
:   lda f:BMP+16,x
    and g_m1
:   sta f:BMP+16,x
    lda t2
    and #8
    beq :+
    lda f:BMP+17,x
    ora g_m0
    bra :++
:   lda f:BMP+17,x
    and g_m1
:   sta f:BMP+17,x
    rep #$20
    .a16
    lda t1
    sta t0
    jmp MarkDirty

PixelBit: .byte $80, $40, $20, $10, $08, $04, $02, $01

; Horizontal line: t6 = x0, t7 = x1, g_y = y, g_c = colour
HLine:
    lda t6
    sta t0
@l:
    lda g_y
    sta t1
    lda g_c
    sta t2
    lda t0
    pha
    jsr Plot
    pla
    sta t0
    cmp t7
    beq @d
    inc t0
    bra @l
@d:
    rts

; Vertical line: g_x = x, t6 = y0, t7 = y1, g_c = colour
VLine:
    lda t6
    sta t1
@l:
    lda g_x
    sta t0
    lda g_c
    sta t2
    lda t1
    pha
    jsr Plot
    pla
    sta t1
    cmp t7
    beq @d
    inc t1
    bra @l
@d:
    rts

; Draw glyph g_glyph at g_x, g_y in colour g_c on the panel background.  Sets g_w (advance).
DrawGlyph:
    ldx g_glyph
    sep #$20
    .a8
    lda f:GlyphWidth,x
    rep #$20
    .a16
    and #$00FF
    sta g_w
    lda g_x
    clc
    adc g_w
    cmp clip_right
    beq :+
    bcc :+
    inc text_clip
:   cmp #257
    bcc :+
    rts
:   lda g_y
    cmp #85
    bcc :+
    inc text_clip
    rts
:   lda g_glyph
    bne :+
    rts                         ; full-width space
:   inc g_drawn                 ; (for the speech blips: this glyph is drawn)
    asl a
    asl a
    asl a
    sta t0
    asl a
    clc
    adc t0                      ; glyph * 24
    tax
    ldy #0
:   lda f:FontData,x
    sta gbuf,y
    inx
    inx
    iny
    iny
    cpy #24
    bne :-
    lda g_y
    and #$FFF8
    xba
    lsr a
    sta g_addr
    lda g_y
    and #7
    sta g_yin
    asl a
    clc
    adc g_addr
    sta g_addr
    lda g_x
    and #$FFF8
    asl a
    asl a
    clc
    adc g_addr
    sta g_addr
    lda g_x
    and #7
    sta g_shift
    ldy #0
@row:
    sep #$20
    .a8
    lda gbuf,y
    sta g_m0
    lda gbuf+1,y
    sta g_m1
    stz g_m2
    ldx g_shift
    beq @noshift
@sh:
    lsr g_m0
    ror g_m1
    ror g_m2
    dex
    bne @sh
@noshift:
    lda g_m0
    ora g_m1
    ora g_m2
    bne :+
    jmp @next
:   ldx g_addr
    lda g_c
    lsr a
    bcs @p1
    lda g_m0
    eor #$FF
    and f:BMP,x
    sta f:BMP,x
    lda g_m1
    eor #$FF
    and f:BMP+32,x
    sta f:BMP+32,x
    lda g_m2
    beq @p1
    eor #$FF
    and f:BMP+64,x
    sta f:BMP+64,x
@p1:
    lda g_c
    and #2
    beq @p2
    lda g_m0
    ora f:BMP+1,x
    sta f:BMP+1,x
    lda g_m1
    ora f:BMP+33,x
    sta f:BMP+33,x
    lda g_m2
    beq @p2
    ora f:BMP+65,x
    sta f:BMP+65,x
@p2:
    lda g_c
    and #4
    beq @p3
    lda g_m0
    ora f:BMP+16,x
    sta f:BMP+16,x
    lda g_m1
    ora f:BMP+48,x
    sta f:BMP+48,x
    lda g_m2
    beq @p3
    ora f:BMP+80,x
    sta f:BMP+80,x
@p3:
    lda g_c
    and #8
    beq @next
    lda g_m0
    ora f:BMP+17,x
    sta f:BMP+17,x
    lda g_m1
    ora f:BMP+49,x
    sta f:BMP+49,x
    lda g_m2
    beq @next
    ora f:BMP+81,x
    sta f:BMP+81,x
@next:
    rep #$20
    .a16
    lda g_yin
    cmp #7
    bne @in
    stz g_yin
    lda g_addr
    clc
    adc #BMP_ROW-14
    sta g_addr
    bra @adv
@in:
    inc g_yin
    inc g_addr
    inc g_addr
@adv:
    iny
    iny
    cpy #24
    beq :+
    jmp @row
:   lda g_y
    sta t0
    clc
    adc #11
    sta t1
    jmp MarkDirty

; p0 = long pointer of text A (TextTable entry)
TextPtr:
    sta t0
    asl a
    clc
    adc t0
    tax
    lda TextTable,x
    sta p0
    lda TextTable+1,x
    sta p0+1
    rts

; Draw the single-line text at p0 from g_x, g_y in colour g_c (a colour code in the text overrides).
; Returns g_x after the text.
DrawText:
    ldy #0
@l:
    lda [p0],y
    iny
    iny
    cmp #$FFFF
    beq @end
    cmp #$FFFC
    bne :+
    lda [p0],y
    iny
    iny
    sta g_c
    bra @l
:   cmp #$FFFE
    beq @l
    sta g_glyph
    phy
    jsr DrawGlyph
    ply
    lda g_x
    clc
    adc g_w
    sta g_x
    bra @l
@end:
    rts

; A = text id -> draw it (g_x, g_y, g_c)
DrawTextId:
    jsr TextPtr
    jmp DrawText

; width in pixels of the text at p0 -> A
TextWidth:
    ldy #0
    stz t0
@l:
    lda [p0],y
    iny
    iny
    cmp #$FFFF
    beq @end
    cmp #$FFFC
    bne :+
    iny
    iny
    bra @l
:   cmp #$FFFE
    beq @l
    tax
    sep #$20
    .a8
    lda f:GlyphWidth,x
    rep #$20
    .a16
    and #$00FF
    clc
    adc t0
    sta t0
    bra @l
@end:
    lda t0
    rts

; Draw A as a decimal number (no leading zeros) with the glyph table at p1 (DigitGlyphs / HalfDigitGlyphs).
; The digits are kept in num_digits: DrawGlyph (MarkDirty) uses t0-t2.
DrawNumber:
    ldx #0
@div:
    sta f:WRDIVL
    sep #$20
    .a8
    lda #10
    sta f:WRDIVB
    nop                         ; 16 cycles for the divider
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
    .a16
    lda f:RDMPYL                ; remainder
    sta num_digits,x
    inx
    inx
    lda f:RDDIVL
    bne @div
    stx num_left
@out:
    lda num_left
    dec a
    dec a
    sta num_left
    tax
    lda num_digits,x
    asl a
    tay
    lda (p1),y
    sta g_glyph
    jsr DrawGlyph
    lda g_x
    clc
    adc g_w
    sta g_x
    lda num_left
    bne @out
    rts

; width of a number drawn with DrawNumber (A = value, t0 = digit width) -> A
NumberWidth:
    ldx t0
    stx nw_digit
    ldy #0
@d:
    iny
    sta f:WRDIVL
    sep #$20
    .a8
    lda #10
    sta f:WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
    .a16
    lda f:RDDIVL
    bne @d
    lda #0
:   clc
    adc nw_digit
    dey
    bne :-
    rts
