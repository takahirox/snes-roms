; ---------------------------------------------------------------- title, menus, chapter cards, endings
.a16
.i16

TITLE_CX = 18                   ; cursor x of the title menu (items 14 px right of it)
TITLE_LINE = 8
MENU_CX = 56                    ; START menu
MENU_LINE = 3

; ---------------------------------------------------------------- generic list menu
; menu_count items at page lines menu_item[i], menu_hlc lines highlighted each, cursor at menu_cx.
; -> A = the chosen item, or $FFFF (B / START: cancel)
MenuLoop:
    jsr MenuShow
    jsr FlushPad
@l:
    jsr WaitFrame
    lda pad_rep
    and #PAD_UP
    beq @dn
    lda menu_count
    cmp #2
    bcc @dn
    jsr MenuHide
    lda menu_sel
    bne :+
    lda menu_count
:   dec a
    sta menu_sel
    jsr MenuShow
    jsr SndCursor
    bra @l
@dn:
    lda pad_rep
    and #PAD_DOWN
    beq @a
    lda menu_count
    cmp #2
    bcc @a
    jsr MenuHide
    lda menu_sel
    inc a
    cmp menu_count
    bcc :+
    lda #0
:   sta menu_sel
    jsr MenuShow
    jsr SndCursor
    bra @l
@a:
    lda pad_new
    and #PAD_A
    beq :+
    jsr MenuHide
    jsr SndOk
    lda menu_sel
    rts
:   lda menu_cancel
    beq @l
    lda pad_new
    and #PAD_B|PAD_START
    beq @l
    jsr MenuHide
    jsr SndCancel
    lda #$FFFF
    rts

MenuShow:
    lda menu_sel
    asl a
    tax
    lda menu_item,x
    ldx menu_hlc
    jsr Highlight
    lda #1
    bra MenuCursor
MenuHide:
    jsr ClearHighlight
    lda #0
MenuCursor:
    sta g_col
    lda menu_sel
    asl a
    tax
    lda menu_item,x
    jsr LineY
    lda menu_cx
    sta g_x
    lda #GLYPH_CURSOR
    sta g_glyph
    jsr DrawGlyph
    lda #1
    sta g_col
    rts

; A = string (bank 0), X = page line: drawn at menu_cx + 14 in g_col
MenuText:
    pha
    txa
    jsr LineY
    lda menu_cx
    clc
    adc #14
    sta g_x
    stz g_space
    pla
    jmp PrintRom

; ---------------------------------------------------------------- title
TitleScreen:
    lda #ST_BUSY
    sta ui_state
    lda #2
    jsr FadeOut
    jsr ResetScreenState
    lda #PIC_TITLE
    jsr LoadPic
    lda #TITLE_SONG
    cmp #$FF
    beq :+
    jsr PlayMusic
:   lda #SND_AMB_OFF
    jsr SndQueue
    lda #$FFFF
    sta amb_cur
    stz menu_sel
    jsr TitleMenuDraw
    jsr WaitUploads
    lda #2
    jsr FadeIn
@menu:
    lda #ST_TITLE
    sta ui_state
    lda #TITLE_CX
    sta menu_cx
    lda #1
    sta menu_hlc
    stz menu_cancel
    jsr MenuLoop
    asl a
    tax
    lda #ST_BUSY
    sta ui_state
    lda menu_kind,x
    beq @new
    cmp #1
    beq @load
    cmp #2
    beq @list
    ; おまけ
    jsr StartGame
    lda #.loword(OMAKE_ADDR)
    sta vp
    lda #^OMAKE_ADDR
    sta vp+2
    jsr RunVM
    jmp TitleScreen
@new:
    jsr NameEntry
    bcc :+
    jmp @back                   ; cancelled
:   jsr StartGame
    lda #.loword(START_ADDR)
    sta vp
    lda #^START_ADDR
    sta vp+2
.if DEBUG_START
    lda debug_vp+2
    beq :+
    sta vp+2
    lda debug_vp
    sta vp
:
.endif
    jsr RunVM
    jmp TitleScreen
@load:
    lda slot_any
    beq @menu
    lda #1
    jsr SlotScreen
    cmp #$FFFF
    beq @back
    pha
    lda #2
    jsr FadeOut
    jsr ResetScreenState
    pla
    jsr LoadGame
    jsr RunVM
    jmp TitleScreen
@list:
    jsr EndingsList
@back:
    jsr ClearPage
    jsr TitleMenuDraw
    jmp @menu

; ---------------------------------------------------------------- name entry (はじめから)
; The hero's family name (主人公) and the heroine's given name (ヒロイン) (1..NAME_MAX glyphs each) typed from
; pages of characters (かな, カナ, 漢字 1-3, NameGrid) over the dimmed title picture (the heroine's family name
; 早瀬 is fixed and shown grey before her name; notes say which name each one is).  Arrows move the cursor (the command row under the grid:
; かな カナ 漢字 けす 決定), A types or runs a command, B deletes (on an empty name: back to the first name, or
; to the title), L / R change the page, START decides.  Carry set: back to the title.
NE_FAMILY_X = TX0 + 74                  ; ヒロイン: 早瀬
NE_NAME_X  = TX0 + 104                  ; the names (aligned)
NE_NOTE_X  = NE_NAME_X + NAME_MAX * 12 + 6   ; （名字） / （名前）
NE_GRID    = 3                          ; first page line of the characters
NE_CMDS    = NE_GRID + NAME_ROWS        ; the command line
NE_CELL    = 21                         ; px per character cell (cursor, then the character at +9)
NE_CMD_W   = 44                         ; px per command

NameEntry:
    lda #ST_BUSY
    sta ui_state
    stz ne_field
    stz ne_page
    stz ne_row
    stz ne_col
    lda #1
    sta dark_on                 ; the title picture out of the way
    jsr NeDrawAll
    jsr WaitUploads
    jsr FlushPad
@loop:
    lda #ST_NAME
    sta ui_state
    jsr WaitFrame
    lda pad_rep
    and #PAD_DIRS
    beq @keys
    jsr NeMove
    bra @loop
@keys:
    lda pad_new
    bit #PAD_A
    beq :+
    jsr NePress
    bcc @loop
    bra @leave
:   bit #PAD_B
    beq :+
    jsr NeBack
    bcc @loop
    bra @leave
:   bit #PAD_START
    beq :+
    jsr NeDecide
    bcc @loop
    bra @leave
:   bit #PAD_L
    beq :+
    lda ne_page
    bne @l1
    lda #NAME_PAGES
@l1:
    dec a
    jsr NePage
    bra @loop
:   bit #PAD_R
    beq @loop
    lda ne_page
    inc a
    cmp #NAME_PAGES
    bcc :+
    lda #0
:   jsr NePage
    jmp @loop
@leave:
    stz dark_on
    cmp #1                      ; carry set: cancelled
    rts

; carry clear: go on; carry set and A = 0: done (names saved), A = 1: cancelled
NeDecide:
    jsr NeLenX
    lda names,x
    bne :+
    jsr SndCancel
    clc
    rts
:   jsr SndOk
    lda ne_field
    bne :+
    lda #1
    sta ne_field
    jsr NeFieldMark
    clc
    rts
:   lda #ST_BUSY
    sta ui_state
    jsr SaveGlobal
    lda #0
    sec
    rts

NeBack:
    jsr NeLenX
    lda names,x
    beq :+
    jsr NeDelete
    clc
    rts
:   jsr SndCancel
    lda ne_field
    beq :+
    stz ne_field
    jsr NeFieldMark
    clc
    rts
:   lda #1
    sec
    rts

; A pressed on the cursor
NePress:
    lda ne_row
    cmp #NAME_ROWS
    bcs @cmd
    jsr NeCell
    cmp #$FFFF
    beq @no
    sta ne_g
    jsr NeLenX
    lda names,x
    cmp #NAME_MAX
    bcs @no
    jsr NeType
    jsr SndOk
    clc
    rts
@no:
    jsr SndCancel
    clc
    rts
@cmd:
    lda ne_col
    cmp #3
    bcc @page
    beq @del
    jmp NeDecide
@del:
    jsr NeLenX
    lda names,x
    beq @no
    jsr NeDelete
    clc
    rts
@page:
    cmp #2
    bcc @go
    lda ne_page                 ; 漢字: the first kanji page, then the next one
    inc a
    cmp #3
    bcc @k
    cmp #NAME_PAGES
    bcc @go
@k:
    lda #2
@go:
    jsr NePage
    jsr SndOk
    clc
    rts

; X = offset of the current name in names
NeLenX:
    lda ne_field
    beq :+
    lda #10
:   tax
    rts

; glyph ne_g at the end of the current name
NeType:
    jsr NeLenX
    lda names,x
    sta ne_i                      ; position
    inc a
    sta names,x
    txa
    clc
    adc ne_i
    adc ne_i
    tax
    lda ne_g
    sta names+2,x
    lda ne_i
    jsr NeSlotXY
    lda #GLYPH_BLANK_NAME
    sta g_glyph
    stz g_col
    jsr DrawGlyph
    lda ne_i
    jsr NeSlotXY
    lda ne_g
    sta g_glyph
    lda #1
    sta g_col
    jmp DrawGlyph

; the last glyph of the current name off
NeDelete:
    jsr NeLenX
    lda names,x
    dec a
    sta names,x
    sta ne_i
    txa
    clc
    adc ne_i
    adc ne_i
    tax
    lda names+2,x
    sta g_glyph
    lda ne_i
    jsr NeSlotXY
    stz g_col
    jsr DrawGlyph
    lda ne_i
    jsr NeSlotXY
    lda #GLYPH_BLANK_NAME
    sta g_glyph
    lda #1
    sta g_col
    jsr DrawGlyph
    jmp SndCancel

; A = position in the current name -> g_x, g_y
NeSlotXY:
    asl a
    asl a
    sta t0
    asl a
    clc
    adc t0                      ; * 12
    adc #NE_NAME_X
    sta g_x
    lda ne_field
    jmp LineY

; the cell under the cursor -> A = glyph ($FFFF none)
NeCell:
    lda ne_page
    asl a
    asl a
    asl a
    asl a
    sta t0                      ; page * 16
    asl a
    asl a
    clc
    adc t0                      ; page * 80
    sta t0
    lda ne_row
    asl a
    sta t1                      ; row * 2
    asl a
    asl a
    adc t1                      ; row * 10
    adc ne_col
    adc t0
    asl a
    tax
    lda NameGrid,x
    rts

; arrows (pad_rep in A)
NeMove:
    pha
    jsr NeCursorOff
    pla
    bit #PAD_UP
    beq :+
    lda ne_row
    bne @up
    lda #NAME_ROWS+1
@up:
    dec a
    jsr NeRow
    bra @done
:   bit #PAD_DOWN
    beq :+
    lda ne_row
    inc a
    cmp #NAME_ROWS+1
    bcc @dn
    lda #0
@dn:
    jsr NeRow
    bra @done
:   pha
    lda #NAME_COLS
    ldx ne_row
    cpx #NAME_ROWS
    bcc :+
    lda #5
:   sta t0                      ; columns in this row
    pla
    bit #PAD_LEFT
    beq :+
    lda ne_col
    bne @left
    lda t0
@left:
    dec a
    sta ne_col
    bra @done
:   bit #PAD_RIGHT
    beq @done
    lda ne_col
    inc a
    cmp t0
    bcc :+
    lda #0
:   sta ne_col
@done:
    jsr SndCursor
    jmp NeCursorOn

; A = new row: the column follows between the characters and the commands
NeRow:
    ldx ne_row
    sta ne_row
    cmp #NAME_ROWS
    bcc @grid
    cpx #NAME_ROWS
    bcs @same
    lda ne_col                  ; into the commands
    lsr a
    cmp #5
    bcc :+
    lda #4
:   sta ne_col
@same:
    rts
@grid:
    cpx #NAME_ROWS
    bcc @same
    lda ne_col                  ; out of the commands
    asl a
    sta ne_col
    rts

NeCursorOff:
    stz g_col
    bra NeCursor
NeCursorOn:
    lda #1
    sta g_col
NeCursor:
    lda ne_row
    cmp #NAME_ROWS
    bcs @cmd
    lda ne_col
    jsr NeCellX
    bra @x
@cmd:
    lda ne_col
    asl a
    tax
    lda NeCmdX,x
    sec
    sbc #TX0
@x:
    clc
    adc #TX0
    sta g_x
    lda ne_row
    clc
    adc #NE_GRID
    jsr LineY
    lda #GLYPH_CURSOR
    sta g_glyph
    jsr DrawGlyph
    lda #1
    sta g_col
    rts

; A = column -> A = column * NE_CELL
NeCellX:
    sta t0
    asl a
    asl a
    sta t1                      ; * 4
    asl a
    asl a
    clc
    adc t1                      ; * 20
    adc t0                      ; * 21
    rts

NeCmdX: .word TX0, TX0 + NE_CMD_W, TX0 + 2 * NE_CMD_W, TX0 + 3 * NE_CMD_W, TX0 + 4 * NE_CMD_W

; the current name's line highlighted
NeFieldMark:
    jsr ClearHighlight
    lda ne_field
    ldx #1
    jmp Highlight

; A = page: the characters drawn again
NePage:
    sta ne_page
    lda #ST_BUSY
    sta ui_state
NeDrawAll:
    jsr ClearPage
    lda #1
    sta g_col
    stz g_space
    lda #0
    jsr LineY
    lda #TX0+14
    sta g_x
    lda #.loword(Str_name_hero)
    jsr PrintRom
    lda #1
    jsr LineY
    lda #TX0+14
    sta g_x
    lda #.loword(Str_name_heroine)
    jsr PrintRom
    lda #3                      ; grey: what is fixed, what each name is
    sta g_col
    lda #1
    jsr LineY
    lda #NE_FAMILY_X
    sta g_x
    lda #.loword(Str_name_heroine_family)
    jsr PrintRom
    lda #0
    jsr LineY
    lda #NE_NOTE_X
    sta g_x
    lda #.loword(Str_name_hero_note)
    jsr PrintRom
    lda #1
    jsr LineY
    lda #NE_NOTE_X
    sta g_x
    lda #.loword(Str_name_heroine_note)
    jsr PrintRom
    lda #1
    sta g_col
    ; the names
    lda ne_field
    pha
    stz ne_field
    jsr @name
    lda #1
    sta ne_field
    jsr @name
    pla
    sta ne_field
    lda #2
    jsr LineY
    lda #TX0+14
    sta g_x
    lda #3
    sta g_col
    lda #.loword(Str_name_hint)
    jsr PrintRom
    lda #1
    sta g_col
    ; the characters
    lda ne_row
    pha
    lda ne_col
    pha
    stz ne_row
@row:
    stz ne_col
@cell:
    jsr NeCell
    cmp #$FFFF
    beq :+
    sta g_glyph
    lda ne_col
    jsr NeCellX
    clc
    adc #TX0+9
    sta g_x
    lda ne_row
    clc
    adc #NE_GRID
    jsr LineY
    jsr DrawGlyph
:   inc ne_col
    lda ne_col
    cmp #NAME_COLS
    bcc @cell
    inc ne_row
    lda ne_row
    cmp #NAME_ROWS
    bcc @row
    pla
    sta ne_col
    pla
    sta ne_row
    ; the commands
    ldx #0
@cmd:
    phx
    lda #NE_CMDS
    jsr LineY
    lda NeCmdX,x
    clc
    adc #12
    sta g_x
    lda NameCmds,x
    jsr PrintRom
    plx
    inx
    inx
    cpx #10
    bne @cmd
    jsr NeFieldMark
    jmp NeCursorOn
@name:
    jsr NeLenX
    stz ne_i
:   lda ne_i
    jsr NeSlotXY
    jsr NeLenX
    lda ne_i
    cmp names,x
    lda #GLYPH_BLANK_NAME
    bcs :+
    txa
    clc
    adc ne_i
    adc ne_i
    tax
    lda names+2,x
:   sta g_glyph
    jsr DrawGlyph
    inc ne_i
    lda ne_i
    cmp #NAME_MAX
    bcc :--
    rts

; the title menu: はじめから / しおりから (grey without a bookmark) / 結末の一覧 / おまけ (unlocked)
TitleMenuDraw:
    lda #ST_BUSY
    sta ui_state
    jsr ClearPage
    stz menu_dim
    jsr AnySlot
    lda #TITLE_CX
    sta menu_cx
    stz menu_count
    lda #0
    ldx #.loword(Str_new)
    jsr @item
    lda #1
    ldx #.loword(Str_load)
    jsr @item
    lda #2
    ldx #.loword(Str_endings)
    jsr @item
    lda #OMAKE_ADDR & $FFFF
    ora #OMAKE_ADDR >> 16
    beq :+
    jsr EndingsSeen
    cmp #OMAKE_ENDINGS
    bcc :+
    lda #3
    ldx #.loword(Str_omake)
    jsr @item
:   lda menu_sel
    cmp menu_count
    bcc :+
    stz menu_sel
:   rts
@item:
    sta t0
    lda menu_count
    asl a
    tay
    lda t0
    sta menu_kind,y
    lda menu_count
    clc
    adc #TITLE_LINE
    sta menu_item,y
    lda #1
    sta g_col
    lda t0
    cmp #1
    bne :+
    lda slot_any
    bne :+
    lda #3
    sta g_col
:   phx
    lda menu_item,y
    tax
    pla
    jsr MenuText
    lda #1
    sta g_col
    inc menu_count
    rts

; new game / omake: no flags, no picture, no music
StartGame:
    lda #2
    jsr FadeOut
    jsr ResetScreenState
    ldx #62
:   stz lflags,x
    dex
    dex
    bpl :-
    lda #SND_FADE
    jsr SndQueue
    lda #$FFFF
    sta music_cur
    sta chapter_cur
    lda #0
    jsr SelectPic
    rts

ResetScreenState:
    stz text_on
    stz dark_on
    stz ripple_on
    stz menu_dim
    stz mosaic
    stz add_level
    stz shake
    stz hide_bg1
    stz dim_cur
    stz redraw
    lda #3
    sta reg_tm
    jsr ClearPage
    jsr ClearSlots
    stz sil_dirty
    stz reg_c1
    stz reg_c0
    lda #24
    sta reg_top
    rts

; A = number of endings seen
EndingsSeen:
    stz t0
    ldx #0
:   txa
    phx
    ldx #gendings
    jsr BitTest
    plx
    clc
    adc t0
    sta t0
    inx
    cpx #ENDING_COUNT
    bne :-
    lda t0
    rts

; ---------------------------------------------------------------- endings list
EndingsList:
    lda #ST_ENDLIST
    sta ui_state
    lda #1
    sta menu_dim
    stz list_page
@draw:
    lda #ST_BUSY
    sta ui_state
    jsr ClearPage
    lda #1
    sta g_col
    stz g_space
    lda #0
    jsr LineY
    lda #TX0
    sta g_x
    lda #.loword(Str_endings)
    jsr PrintRom
    lda #176
    sta g_x
    jsr EndingsSeen
    jsr PutNum
    lda SlashCode
    and #$00FF
    sec
    sbc #$10
    jsr PutGlyph
    lda #ENDING_COUNT
    jsr PutNum
    ; ten per page
    lda list_page
    asl a
    sta t0
    asl a
    asl a
    clc
    adc t0                      ; page * 10
    sta list_first
    stz list_k
@item:
    lda list_first
    clc
    adc list_k
    cmp #ENDING_COUNT
    bcs @hint
    sta list_i
    lda list_k
    inc a                       ; lines 1-10 (0 the heading, 11 the hint)
    jsr LineY
    lda #TX0+6
    sta g_x
    lda #1
    sta g_col
    lda list_i
    inc a
    jsr PutNum2
    lda g_x
    clc
    adc #8
    sta g_x
    lda list_i
    ldx #gendings
    jsr BitTest
    beq @unseen
    lda list_i
    asl a
    asl a
    asl a
    tax
    lda EndingTable,x
    jsr PrintRom
    bra @nextk
@unseen:
    lda #3
    sta g_col
    lda #.loword(Str_unknown)
    jsr PrintRom
@nextk:
    inc list_k
    lda list_k
    cmp #10
    bcc @item
@hint:
    lda #ENDING_COUNT
    cmp #11
    bcc @wait
    lda #3
    sta g_col
    lda #11
    jsr LineY
    lda #.loword(Str_list_hint)
    jsr PrintCentered
@wait:
    lda #ST_ENDLIST
    sta ui_state
    jsr WaitFrame
    lda pad_new
    and #PAD_B|PAD_A|PAD_START
    bne @out
    lda #ENDING_COUNT
    cmp #11
    bcc @wait
    lda pad_new
    and #PAD_LEFT|PAD_RIGHT
    beq @wait
    lda list_page
    eor #1
    sta list_page
    lda list_page
    asl a
    sta t0
    asl a
    asl a
    clc
    adc t0
    cmp #ENDING_COUNT
    bcc :+
    stz list_page
:   jsr SndCursor
    jmp @draw
@out:
    jsr SndCancel
    stz menu_dim
    lda #1
    sta g_col
    rts

; ---------------------------------------------------------------- START menu
; Called from a paragraph wait or a choice.  The page is kept in BMPSAVE and restored.
OpenMenu:
    ; context of the caller
    lda p0
    pha
    lda p0+2
    pha
    lda g_x
    pha
    lda g_y
    pha
    lda page_line
    sta saved_line
    lda hl_line
    sta saved_hl
    lda hl_count
    sta saved_hlc
    lda last_text
    sta menu_last_text          ; (SaveGame: the paragraph to redraw before a choice)
    pha
    lda mark_on
    pha
    lda ui_state
    pha
    lda #ST_BUSY
    sta ui_state
    jsr SndOk
    jsr ClearHighlight
    jsr BackupBitmap
    lda #1
    sta menu_dim
    stz menu_sel
@draw:
    jsr MenuDraw
@loop:
    lda #ST_MENU
    sta ui_state
    lda #MENU_CX
    sta menu_cx
    lda #1
    sta menu_hlc
    sta menu_cancel
    jsr MenuLoop
    cmp #$FFFF
    beq @close
    cmp #0
    bne @speed
    ; しおりをはさむ
    lda #0
    jsr SlotScreen
    cmp #$FFFF
    beq @draw
    jsr SaveGame
    jsr ClearPage
    lda #5
    jsr LineY
    lda #.loword(Str_saved)
    jsr PrintCentered
    lda #60
    jsr WaitFrames
    bra @close
@speed:
    cmp #1
    bne @title
    lda speed
    inc a
    and #3
    sta speed
    jsr SaveGlobal
    bra @draw
@title:
    cmp #2
    bne @close
    jsr Confirm
    beq @draw
    ; to the title
    lda #SND_FADE
    jsr SndQueue
    lda #$FFFF
    sta music_cur
    lda #2
    jsr FadeOut
    stz menu_dim
    jmp VmExit
@close:
    jsr RestoreBitmap
    stz menu_dim
    lda saved_line
    sta page_line
    lda saved_hl
    cmp #$FFFF
    beq :+
    ldx saved_hlc
    jsr Highlight
:   pla
    sta ui_state
    pla
    sta mark_on
    pla
    sta last_text
    pla
    sta g_y
    pla
    sta g_x
    pla
    sta p0+2
    pla
    sta p0
    rts

MenuDraw:
    lda #ST_BUSY
    sta ui_state
    jsr ClearPage
    lda #1
    sta g_col
    lda #MENU_CX
    sta menu_cx
    lda #4
    sta menu_count
    ldx #0
:   txa
    lsr a
    clc
    adc #MENU_LINE
    sta menu_item,x
    inx
    inx
    cpx #8
    bne :-
    lda #.loword(Str_menu_save)
    ldx #MENU_LINE
    jsr MenuText
    lda #.loword(Str_menu_speed)
    ldx #MENU_LINE+1
    jsr MenuText
    lda #MENU_CX+14+108
    sta g_x
    lda speed
    asl a
    tax
    lda SpeedTable,x
    jsr PrintRom
    lda #.loword(Str_menu_title)
    ldx #MENU_LINE+2
    jsr MenuText
    lda #.loword(Str_menu_back)
    ldx #MENU_LINE+3
    jsr MenuText
    rts

; タイトルにもどりますか  はい / いいえ -> A = 1 yes (Z clear), 0 no
Confirm:
    lda menu_sel
    pha
    jsr ClearPage
    lda #ST_CONFIRM
    sta ui_state
    lda #4
    jsr LineY
    lda #.loword(Str_title_confirm)
    jsr PrintCentered
    lda #96
    sta menu_cx
    lda #2
    sta menu_count
    lda #6
    sta menu_item
    lda #7
    sta menu_item+2
    lda #.loword(Str_yes)
    ldx #6
    jsr MenuText
    lda #.loword(Str_no)
    ldx #7
    jsr MenuText
    lda #1
    sta menu_sel
    jsr MenuLoop
    tax
    pla
    sta menu_sel
    lda #0
    cpx #0
    bne :+
    lda #1
:   cmp #0
    rts

; ---------------------------------------------------------------- bookmarks
; A = 0 save / 1 load -> A = slot 0-2, or $FFFF
SlotScreen:
    sta slot_mode
    lda ui_state
    pha
    lda #ST_BUSY
    sta ui_state
    lda #1
    sta menu_dim
    jsr ClearPage
    lda #1
    sta g_col
    lda #0
    jsr LineY
    lda #.loword(Str_slot_head_save)
    ldx slot_mode
    beq :+
    lda #.loword(Str_slot_head_load)
:   jsr PrintCentered
    lda #24
    sta menu_cx
    lda #3
    sta menu_count
    lda #2
    sta menu_hlc
    lda #1
    sta menu_cancel
    stz slot_k
@slot:
    lda slot_k
    asl a
    tax
    lda slot_k
    asl a
    clc
    adc slot_k
    adc #2
    sta menu_item,x
    lda #1
    sta g_col
    lda SlotNames,x
    pha
    lda menu_item,x
    tax
    pla
    jsr MenuText
    lda slot_k
    jsr ValidateSlot
    pha
    lda slot_k
    asl a
    tax
    pla
    sta slot_valid,x
    beq @empty
    lda save_buf+20             ; chapter
    cmp #CHAPTER_COUNT
    bcs @nochap
    asl a
    asl a
    tax
    lda ChapterTable,x
    pha
    lda ChapterTable+2,x
    pha
    bra @chap
@nochap:
    lda #.loword(Str_notitle)
    pha
    lda #.loword(Str_empty)
    pha
@chap:
    lda slot_k
    asl a
    clc
    adc slot_k
    adc #3
    jsr LineY
    lda #64
    sta g_x
    lda #1
    sta g_space
    pla
    sta t7
    pla
    jsr PrintRom
    lda g_x
    clc
    adc #8
    sta g_x
    lda t7
    jsr PrintRom
    stz g_space
    bra @nexts
@empty:
    lda #3
    sta g_col
    lda slot_k
    asl a
    clc
    adc slot_k
    adc #3
    jsr LineY
    lda #64
    sta g_x
    lda #.loword(Str_slot_empty)
    jsr PrintRom
@nexts:
    inc slot_k
    lda slot_k
    cmp #3
    bcs :+
    jmp @slot
:   lda #1
    sta g_col
    stz menu_sel
    lda #ST_SLOTS
    sta ui_state
@pick:
    jsr MenuLoop
    cmp #$FFFF
    beq @out
    sta t0
    lda slot_mode
    beq @ok                     ; saving: any slot
    lda t0
    asl a
    tax
    lda slot_valid,x
    beq @pick
@ok:
    lda t0
@out:
    sta t0
    pla
    sta ui_state
    lda t0
    rts

; slot_any = 1 when a valid bookmark exists
AnySlot:
    stz slot_any
    lda #0
    jsr ValidateSlot
    ora slot_any
    sta slot_any
    lda #1
    jsr ValidateSlot
    ora slot_any
    sta slot_any
    lda #2
    jsr ValidateSlot
    ora slot_any
    sta slot_any
    rts

; ---------------------------------------------------------------- the bitmap under the menu
; in 8 slices of 1440 bytes (MVN: 7 cycles a byte), a frame each
BackupBitmap:
    ldx #.loword(BMP)
    ldy #.loword(BMPSAVE)
    bra CopyBitmap
RestoreBitmap:
    ldx #.loword(BMPSAVE)
    ldy #.loword(BMP)
    jsr CopyBitmap
    lda #$FFFF
    sta text_dirty
    lda #$00FF
    sta text_dirty+2
    rts
CopyBitmap:
    lda #8
    sta t7
@l:
    phx
    phy
    jsr PacedWait
    ply
    plx
    phb
    lda #BMP_SIZE/8-1
    mvn #$7E, #$7E              ; X, Y advance by the slice
    plb
    dec t7
    bne @l
    rts

; ---------------------------------------------------------------- chapter card
; A = chapter: the screen goes black, the two parts of the title (split at the first full-width space)
; appear centred, then black again; the picture comes back unless a new one follows.
ChapterCard:
    sta chapter_cur
    lda #ST_CHAPTER
    sta ui_state
    jsr ClearPage
    stz text_on
    lda #2
    jsr FadeOut
    lda #2                      ; BG2 only
    sta reg_tm
    lda #1
    sta g_col
    lda #6
    sta g_space
    lda #72
    sta g_y
    lda chapter_cur
    asl a
    asl a
    tax
    lda ChapterTable,x
    pha
    lda ChapterTable+2,x
    pha
    pla
    sta t7
    pla
    jsr PrintCentered
    lda #2
    sta g_space
    lda #100
    sta g_y
    lda t7
    jsr PrintCentered
    stz g_space
    jsr WaitUploads
    lda #2
    jsr FadeIn
    lda #150
    sta t7
:   jsr WaitFrame
    lda pad_new
    and #PAD_A
    bne :+
    dec t7
    bne :-
:   lda #2
    jsr FadeOut
    jsr ClearPage
    jsr WaitUploads
    lda #3
    sta reg_tm
    jsr BgFollows
    bne :+
    lda #2
    jmp FadeIn
:   rts

; Z clear when an OP_BG comes next (after sound / flag ops)
BgFollows:
    lda vp
    sta p2
    lda vp+2
    sta p2+2
@l:
    lda [p2]
    and #$00FF
    cmp #OP_BG
    beq @yes
    ldy #2
    cmp #OP_BGM
    beq @skip
    cmp #OP_SE
    beq @skip
    cmp #OP_AMB
    beq @skip
    cmp #OP_SETG
    beq @skip
    cmp #OP_CLRG
    beq @skip
    ldy #3
    cmp #OP_SET
    beq @skip
    cmp #OP_CLR
    beq @skip
    ldy #4
    cmp #OP_FX
    beq @skip
    lda #0
    rts
@skip:
    tya
    clc
    adc p2
    sta p2
    bra @l
@yes:
    lda #1
    rts

; ---------------------------------------------------------------- ending
; A = ending index: record it, 終 and the ending's name over the darkened picture, A -> title
EndingScreen:
    sta end_index
    inc a
    sta endings_reached
    lda end_index
    jsr RecordEnding
    lda #ST_ENDING
    sta ui_state
    jsr ClearPage
    stz text_on
    jsr EnsureVisible
    lda #1
    sta menu_dim
    lda #40
    jsr WaitFrames
    lda #(BMP_COLS-OWARI_W)/2
    sta t0
    lda #6
    sta t1
    jsr BlitOwari
    lda #1
    sta g_col
    lda #2
    sta g_space
    lda #6*8+OWARI_H*8+14
    sta g_y
    lda end_index
    asl a
    asl a
    asl a
    tax
    lda EndingTable,x
    jsr PrintCentered
    stz g_space
    lda #3
    sta g_col
    lda #6*8+OWARI_H*8+40
    sta g_y
    lda end_index
    asl a
    asl a
    asl a
    tax
    lda EndingTable+2,x
    asl a
    tax
    lda KindNames,x
    jsr PrintCentered
    lda #1
    sta g_col
    lda #90
    jsr WaitFrames
:   jsr WaitFrame
    lda pad_new
    and #PAD_A|PAD_START
    beq :-
    lda #SND_FADE
    jsr SndQueue
    lda #$FFFF
    sta music_cur
    lda #3
    jsr FadeOut
    stz menu_dim
    rts
