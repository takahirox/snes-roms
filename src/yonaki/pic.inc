; ---------------------------------------------------------------- effects, pictures, silhouettes
.a16
.i16

; Once per frame (WaitFrame): the dim, colour addition, shake, ripple, mosaic and brightness -> shadows.
Tick:
    inc blink
    ; the dim target
    lda #0
    ldx text_on
    beq :+
    lda #DIM_TEXT
:   ldx menu_dim
    beq :+
    lda #DIM_MENU
:   ldx dark_on
    beq :+
    lda #31
:   ldx hide_bg1
    beq :+
    lda #31
:   sta t0
    ldx #1
    lda hide_bg1
    beq :+
    ldx #6
    bra @step
:   lda dim_cur
    cmp t0
    bcc @step
    ldx #3
@step:
    stx t1
    lda dim_cur
    cmp t0
    beq @dimdone
    bcs @down
    clc
    adc t1
    cmp t0
    bcc :+
    lda t0
:   sta dim_cur
    bra @dimdone
@down:
    sec
    sbc t1
    bmi :+
    cmp t0
    bcs :++
:   lda t0
:   sta dim_cur
@dimdone:
    ; the silhouette colours rise as the photo is dimmed under text, so the figures keep their brightness;
    ; toward a full dim (dark, hiding an upload) they go down with the photo
    lda #0
    ldx add_level
    bne :+
    ldx dim_cur
    lda SilComp,x
    and #$00FF
:   cmp sil_comp
    beq @comp_ok
    sta sil_comp
    ldx #16
@cc:
    lda f:SysPalette,x
    and #$001F
    clc
    adc sil_comp
    cmp #32
    bcc :+
    lda #31
:   sta t2
    lda f:SysPalette,x
    and #$03E0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc sil_comp
    cmp #32
    bcc :+
    lda #31
:   asl a
    asl a
    asl a
    asl a
    asl a
    ora t2
    sta t2
    lda f:SysPalette,x
    xba
    lsr a
    lsr a
    and #$001F
    clc
    adc sil_comp
    cmp #32
    bcc :+
    lda #31
:   xba
    asl a
    asl a
    ora t2
    sta ui_pal,x
    inx
    inx
    cpx #28
    bne @cc
    lda #1
    sta ui_dirty
@comp_ok:
    ; colour math
    lda add_level
    beq @nodd
    sta t0
    sta t1
    lda add_red
    beq :+
    lda t0
    lsr a
    lsr a
    lsr a
    sta t1
:   lda #$3F                    ; add, every layer and the backdrop
    sta reg_cgadsub
    lda t0
    ora #$20
    sta reg_col_r
    lda t1
    ora #$40
    sta reg_col_g
    lda t1
    ora #$80
    sta reg_col_b
    lda add_level
    sec
    sbc add_decay
    bpl :+
    lda #0
:   sta add_level
    bra @shake
@nodd:
    lda dim_cur
    beq @nomath
    lda #$81                    ; subtract, BG1 only
    sta reg_cgadsub
    lda dim_cur
    ora #$20
    sta reg_col_r
    lda dim_cur
    ora #$40
    sta reg_col_g
    lda dim_cur
    ora #$80
    sta reg_col_b
    bra @shake
@nomath:
    stz reg_cgadsub
@shake:
    lda shake
    beq @noshake
    dec shake
    and #7
    asl a
    tax
    lda ShakeX,x
    and #$03FF
    sta reg_hofs
    lda ShakeY,x
    clc
    adc #$03FF
    and #$03FF
    sta reg_vofs
    bra @ripple
@noshake:
    stz reg_hofs
    lda #$03FF
    sta reg_vofs
@ripple:
    lda ripple_on
    sta reg_hdma
    beq @mosaic
    lda ripple_phase
    inc a
    and #63
    sta ripple_phase
    lsr a
    sta t0
    asl a
    clc
    adc t0
    clc
    adc #.loword(RippleTable)
    sta reg_hdma_src
@mosaic:
    lda mosaic
    beq :+
    asl a
    asl a
    asl a
    asl a
    ora #1
:   sta reg_mosaic
    lda bright
    ldx blanked
    beq :+
    lda #$80
:   sta inidisp
    rts

ShakeX: .word 3, $FFFD, 2, $FFFE, 3, $FFFF, 1, $FFFE
ShakeY: .word $FFFE, 2, $FFFF, 1, 2, $FFFE, 1, 0

; ---------------------------------------------------------------- fades (master brightness)
; A = frames per step
FadeOut:
    sta t6
    lda blanked
    bne @done
@l:
    lda bright
    beq @off
    dec bright
    lda t6
    jsr WaitFrames
    lda t6                      ; (WaitFrames keeps t6)
    bra @l
@off:
    lda #1
    sta blanked
    jsr WaitFrame
@done:
    rts

FadeIn:
    sta t6
    lda blanked
    beq :+
    stz bright
    stz blanked
:
@l:
    lda bright
    cmp #15
    bcs @done
    inc bright
    lda t6
    jsr WaitFrames
    bra @l
@done:
    rts

; ---------------------------------------------------------------- pictures
; A = picture -> pic_cur, pic_entry, pal_src
SelectPic:
    sta pic_cur
    asl a
    asl a
    asl a
    asl a
    sta t0
    asl a
    asl a
    clc
    adc t0                      ; * 80
    sta pic_entry
    tax
    lda PicTable,x
    sta pal_src
    lda PicTable+2,x
    and #$00FF
    sta pal_src+2
    rts

; A = span (start | end << 8), X = row * 2 -> t2 = WRAM byte offset, t3 = byte length.
PhotoSpanDMA:
    sta t3
    and #$00FF
    sta t2
    lda t3
    xba
    and #$00FF
    sec
    sbc t2
    xba
    lsr a
    lsr a
    sta t3
    lda t2
    xba
    lsr a
    lsr a
    sta t2
    txa
    xba
    asl a
    asl a
    ora t2
    sta t2
    rts

; Restore photo_spans from ROM into WRAM, up to 8 KiB per frame, starting right after a WaitFrame.
RestoreRows:
    lda #8192
    sta rs_bytes                ; force a WaitFrame before the first slice
    stz rs_row
@row:
    ldx rs_row
    cpx #PHOTO_SPAN_BYTES
    jcs @done
    lda photo_spans,x
    jeq @next
    jsr PhotoSpanDMA
    lda rs_bytes
    clc
    adc t3
    cmp #8193
    bcc :+
    jsr WaitFrame
    stz rs_bytes
:   lda rs_bytes
    clc
    adc t3
    sta rs_bytes
    lda t2
    sta WMADDL
    sep #$20
    .a8
    lda #$01
    sta WMADDH
    lda #<WMDATA
    sta BBAD1
    rep #$20
    .a16
    lda rs_row
    lsr a
    adc rs_row                  ; row * 3, carry clear from shifting an even offset
    clc
    adc pic_entry
    tax
    lda PicTable+5,x            ; bank of the row
    and #$00FF
    beq @solid
    sep #$20
    .a8
    sta A1B1
    stz DMAP1
    rep #$20
    .a16
    lda t2
    and #$07FF                  ; offset within the source row
    clc
    adc PicTable+3,x
    sta A1T1L
    bra @go
@solid:
    sep #$20
    .a8
    lda #$08                    ; fixed source $FF: every bitplane set = colour 255
    sta DMAP1
    lda #^FFWord
    sta A1B1
    rep #$20
    .a16
    lda #.loword(FFWord)
    sta A1T1L
@go:
    lda t3
    sta DAS1L
    sep #$20
    .a8
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
@next:
    inc rs_row
    inc rs_row
    jmp @row
@done:
    rts

; the WRAM photo to VRAM in forced blank: 16 KiB per frame
UploadPhotoNow:
    stz t5
@l:
    jsr WaitFrame
    sep #$20
    .a8
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP1
    lda #$18
    sta BBAD1
    lda #$7F
    sta A1B1
    rep #$20
    .a16
    lda t5
    lsr a
    sta VMADDL
    lda t5
    sta A1T1L
    lda #$4000
    sta DAS1L
    sep #$20
    .a8
    lda #$02
    sta MDMAEN
    rep #$20
    .a16
    lda t5
    clc
    adc #$4000
    sta t5
    cmp #$C000
    bne @l
    rts

; A = picture: WRAM <- ROM, silhouettes composited, then VRAM (forced blank: now; else by V-blank streaming)
LoadPic:
    jsr SelectPic
    lda #PHOTO_COLS << 8         ; full-width spans
    ldx #PHOTO_SPAN_BYTES-2
:   sta photo_spans,x
    dex
    dex
    bpl :-
    jsr RestoreRows
    jsr CompositeAll
    lda #1
    sta pal_dirty
    jsr QueueTint
    lda blanked
    beq @stream
    jsr UploadPhotoNow
    jmp WaitUploads
@stream:
    jmp UploadPhotoSpans

UploadPhotoSpans:
    stz photo_next
    lda #1
    sta photo_dirty
    jmp WaitUploads

; ---------------------------------------------------------------- silhouettes
; slots: sil_key $FF free / 0 l / 1 c / 2 r / $80|x; sil_id; sil_x (tile); sil_col (0 blue, 1 white, 2 red)
ClearSlots:
    lda #$FFFF
    ldx #6
:   sta sil_key,x
    dex
    dex
    bpl :-
    rts

ClearSilSpans:
    ldx #PHOTO_SPAN_BYTES-2
:   stz sil_spans,x
    dex
    dex
    bpl :-
    rts

; Enclose spans A and t1 in a single span. Neither X nor Y changes.
MergeSpan:
    cmp #0
    beq @old
    sta t0
    lda t1
    beq @new
    cmp t0
    bcs :+
    lda t0
:   and #$FF00
    sta t2
    lda t1
    and #$00FF
    sta t1
    lda t0
    and #$00FF
    cmp t1
    bcc :+
    lda t1
:   ora t2
    rts
@new:
    lda t0
    rts
@old:
    lda t1
    rts

; Only the previously composited spans need restoring. Upload their union with the new spans
; after compositing in slot order, while BG1 is fully dimmed.
ApplySils:
    stz sil_dirty
    stz t0
    ldx #PHOTO_SPAN_BYTES-2
:   lda sil_spans,x
    sta photo_spans,x
    ora t0
    sta t0
    dex
    dex
    bpl :-
    lda t0
    bne :+
    lda sil_key
    and sil_key+2
    and sil_key+4
    and sil_key+6
    cmp #$FFFF
    bne :+
    rts                         ; nothing before, nothing now
:   lda ui_state
    pha
    lda #ST_BUSY
    sta ui_state
    lda #1
    sta hide_bg1
    ldx #WAIT_DIM
    jsr WaitEvent
    jsr RestoreRows
    jsr CompositeAll
    jsr QueueTint
    ldx #PHOTO_SPAN_BYTES-2
:   lda photo_spans,x
    sta t1
    lda sil_spans,x
    jsr MergeSpan
    sta photo_spans,x
    dex
    dex
    bpl :-
    jsr UploadPhotoSpans
    stz hide_bg1
    pla
    sta ui_state
    rts

CompositeAll:
    jsr ClearSilSpans
    jsr PickTint
    ldx #0
@l:
    lda sil_key,x
    cmp #$FFFF
    beq :+
    phx
    jsr Composite
    plx
:   inx
    inx
    cpx #8
    bne @l
    rts

; tint_ok: the picture has translucent-figure colours (PicTable+75, the white / red block; the blue ones are
; colours 128-239 of its palette).  tint_col: the colour drawn translucent, white before red before blue (one
; scene shows a blue figure with a white one: the blue one is then drawn solid).
PickTint:
    stz tint_ok
    stz tint_col
    ldx pic_entry
    lda PicTable+77,x
    and #$00FF
    beq @d
    inc tint_ok
    ldx #0
@l:
    lda sil_key,x
    cmp #$FFFF
    beq @n
    lda sil_col,x
    cmp #1
    beq @white
    cmp #2
    bne @n
    lda tint_col
    bne @n                      ; white stays
    lda #2
    sta tint_col
    bra @n
@white:
    sta tint_col
@n:
    inx
    inx
    cpx #8
    bne @l
@d:
    rts

; the translucent-figure colours of tint_col to CGRAM 144-255 (after the photo colours)
QueueTint:
    lda tint_ok
    beq @d
    lda tint_col
    bne @alt
    lda pal_src
    clc
    adc #256                    ; colour 128 of the photo palette
    sta tint_up
    lda pal_src+2
    sta tint_up+2
    bra @q
@alt:
    ldx pic_entry
    cmp #2
    lda PicTable+75,x
    bcc :+
    adc #224-1                  ; red follows white (carry set)
:   sta tint_up
    lda PicTable+77,x
    and #$00FF
    sta tint_up+2
@q:
    lda #1
    sta tint_dirty
@d:
    rts

; X = slot * 2: composite that silhouette into the WRAM photo.
; Solid (no translucent-figure colours, or not tint_col), per pixel row of a tile, with cover c and rim r (mask
; bytes) and old plane words:
;   planes 0/1 = (old & ~c) | r | (red: c in plane 1)
;   planes 2/3 = (old & ~c) | c in plane 3 | (blue: c in plane 2)
;   planes 4-7 = old & ~c
; which gives colour 12/13 (blue body/rim), 10/11 (red), 8/9 (white).
; Translucent: no rim; the whole figure keeps the photo's colour with bit 7 set, the same colour seen through
; the figure (colours 144-255):  plane 7 = old | c
Composite:
    stz s_tr
    lda tint_ok
    beq :+
    lda sil_col,x
    cmp tint_col
    bne :+
    inc s_tr
:   lda sil_col,x
    ldy #0
    cmp #2
    bne :+
    ldy #$FF00
:   sty s_m0
    ldy #$FF00
    cmp #0
    bne :+
    ldy #$FFFF
:   sty s_m1
    lda sil_x,x
    sta c_x
    lda sil_id,x
    asl a
    asl a
    asl a
    tay
    lda SilTable,y
    and #$00FF
    sta c_ty
    lda SilTable+1,y
    and #$00FF
    asl a
    sta c_row
    lda SilTable+2,y
    sta p0
    lda SilTable+4,y
    and #$00FF
    sta p0+2
    ldy #0                      ; mask offset
@trow:
    lda [p0],y                  ; first column | tile count << 8
    iny
    iny
    cmp #0
    jeq @row_done
    sta t0
    and #$00FF
    clc
    adc c_x
    sta c_start
    lda t0
    xba
    and #$00FF
    sta t3
    asl a
    asl a
    asl a
    asl a
    sta t0
    tya
    clc
    adc t0
    sta c_next
    lda c_start
    cmp #PHOTO_COLS
    jcs @next_row
    adc t3
    cmp #PHOTO_COLS+1
    bcc :+
    lda #PHOTO_COLS
:   sta t0
    sec
    sbc c_start
    sta c_left
    lda t0
    xba
    ora c_start
    sta t4
    ldx c_row
    jsr PhotoSpanDMA
    lda t2
    sta c_dest
    lda sil_spans,x
    sta t1
    lda t4
    jsr MergeSpan
    sta sil_spans,x
@tile:
    lda work_count
    cmp #TILES_PER_FRAME
    bcc :+
    phy
    jsr PacedWait
    ply
:   inc work_count
    ldx c_dest
    lda #8
    sta c_n
    lda s_tr
    beq @px
    jmp @pxt
@px:
    lda [p0],y
    sta t1                      ; rim << 8 | cover
    and #$00FF
    beq @skip
    sta t2
    xba
    ora t2
    sta t3                      ; cover in both bytes
    eor #$FFFF
    sta t4                      ; keep mask
    lda t1
    xba
    and #$00FF
    sta t5                      ; rim in plane 0
    lda t3
    and s_m0
    ora t5
    sta t5
    lda f:PHOTO,x
    and t4
    ora t5
    sta f:PHOTO,x
    lda t3
    and s_m1
    sta t5
    lda f:PHOTO+16,x
    and t4
    ora t5
    sta f:PHOTO+16,x
    lda f:PHOTO+32,x
    and t4
    sta f:PHOTO+32,x
    lda f:PHOTO+48,x
    and t4
    sta f:PHOTO+48,x
@skip:
    inx
    inx
    iny
    iny
    dec c_n
    bne @px
    bra @tnext
@pxt:
    lda [p0],y
    and #$00FF                  ; cover (the rim is part of it)
    beq @skipt
    xba
    ora f:PHOTO+48,x
    sta f:PHOTO+48,x
@skipt:
    inx
    inx
    iny
    iny
    dec c_n
    bne @pxt
@tnext:
    dec c_left
    beq @next_row
    lda c_dest
    clc
    adc #64
    sta c_dest
    jmp @tile
@next_row:
    ldy c_next                  ; skip any tiles clipped off the right edge
@row_done:
    inc c_row
    inc c_row
    dec c_ty
    beq :+
    jmp @trow
:   rts

; VM side: the slot of key A (A = key byte) -> X = slot * 2, or a free one (carry set when new)
FindSlot:
    ldx #0
:   cmp sil_key,x
    beq @found
    inx
    inx
    cpx #8
    bne :-
    ldx #0
:   ldy sil_key,x
    cpy #$FFFF
    beq @free
    inx
    inx
    cpx #8
    bne :-
    ldx #6                      ; all taken: the last slot
@free:
    sec
    rts
@found:
    clc
    rts
