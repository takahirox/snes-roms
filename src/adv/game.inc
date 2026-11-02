; ---------------------------------------------------------------- game modes
.a16
.i16

Update:
    lda mode
    asl a
    tax
    jmp (ModeTable,x)
ModeTable:
    .word UpdateCmd, UpdateList, UpdateMsg, UpdateFade, UpdateEnd, UpdateOpen

; ---------------------------------------------------------------- flags (A = flag id; X and Y kept)
TestFlag:
    phx
    phy
    pha
    lsr a
    lsr a
    lsr a
    tax
    pla
    and #7
    tay
    sep #$20
    .a8
    lda flags,x
    and ByteBit,y
    rep #$20
    .a16
    and #$00FF
    ply
    plx
    cmp #0
    rts

SetFlag:
    phx
    phy
    pha
    lsr a
    lsr a
    lsr a
    tax
    pla
    and #7
    tay
    sep #$20
    .a8
    lda flags,x
    ora ByteBit,y
    sta flags,x
    rep #$20
    .a16
    ply
    plx
    rts

ClrFlag:
    phx
    phy
    pha
    lsr a
    lsr a
    lsr a
    tax
    pla
    and #7
    tay
    sep #$20
    .a8
    lda ByteBit,y
    eor #$FF
    and flags,x
    sta flags,x
    rep #$20
    .a16
    ply
    plx
    rts

ByteBit: .byte $01, $02, $04, $08, $10, $20, $40, $80

; A = condition word (0 = none, bit 15 = not) -> A = 1 true / 0 false
CondTrue:
    cmp #0
    beq @yes
    bit #$8000
    bne @not
    jsr TestFlag
    bne @yes
    bra @no
@not:
    and #$7FFF
    jsr TestFlag
    beq @yes
@no:
    lda #0
    rts
@yes:
    lda #1
    rts

; ---------------------------------------------------------------- command mode
UpdateCmd:
    lda pad_rep
    and #PAD_UP
    beq :+
    lda cmd_sel
    dec a
    bpl @set
    lda #4
    bra @set
:   lda pad_rep
    and #PAD_DOWN
    beq @keys
    lda cmd_sel
    inc a
    cmp #5
    bcc @set
    lda #0
@set:
    sta cmd_sel
    lda #SFX_CURSOR
    jsr PlaySfx
    jmp DrawCmdCursor
@keys:
    lda pad_new
    and #PAD_A
    beq @ret
    lda #SFX_OK
    jsr PlaySfx
    jmp DoCommand
@ret:
    rts

DoCommand:
    lda cmd_sel
    sta cmd_active
    asl a
    tax
    jmp (CmdJump,x)
CmdJump:
    .word CmdTalk, CmdLook, CmdShow, CmdMove, CmdNote

CmdTalk:
    lda person
    bne :+
    lda #TX_NOBODY
    ldx #RET_CMD
    jmp SysMsg
:   jsr PortraitOn
    lda #LK_TOPIC
    jmp OpenList

CmdLook:
    jsr PortraitOff
    lda #LK_LOOK
    jmp OpenList

CmdShow:
    lda person
    bne :+
    lda #TX_NOBODY
    ldx #RET_CMD
    jmp SysMsg
:   lda #LK_SHOW
    sta list_kind
    jsr BuildList
    lda list_count
    bne :+
    lda #TX_NOCLUE
    ldx #RET_CMD
    jmp SysMsg
:   jsr PortraitOn
    lda #LK_SHOW
    jmp OpenList

CmdMove:
    lda #LK_MOVE
    jmp OpenList

CmdNote:
    lda #LK_NOTE
    jmp OpenList

; A = text, X = where to go afterwards
SysMsg:
    stx vm_return
    stz vm_active
    jmp OpenMessage

; A = script address, X = where to go afterwards
RunScript:
    sta vm_pc
    stx vm_return
    stz vm_sp
    lda #1
    sta vm_active
    jmp RunVM

; ---------------------------------------------------------------- lists
OpenList:
    sta list_kind
    stz list_sel
    stz list_top
ShowList:
    jsr BuildList
    lda list_count
    beq @clamp0
    lda list_sel
    cmp list_count
    bcc :+
    lda list_count
    dec a
    sta list_sel
:   jsr KeepVisible
    bra @show
@clamp0:
    stz list_sel
    stz list_top
@show:
    lda #M_LIST
    sta mode
    lda list_kind
    cmp #LK_TITLE
    bne :+
    jmp DrawTitleList
:   jmp DrawGameScreen

KeepVisible:
    lda list_sel
    cmp list_top
    bcs :+
    sta list_top
:   lda list_top
    clc
    adc #LIST_ROWS
    cmp list_sel
    beq :+
    bcs :++
:   lda list_sel
    sec
    sbc #LIST_ROWS-1
    sta list_top
:   rts

; add one entry: A = label, t6 = argument, t7 = colour
AddEntry:
    ldx list_count
    cpx #LIST_MAX
    bcs @full
    pha
    txa
    asl a
    tax
    pla
    sta list_label,x
    lda t6
    sta list_arg,x
    lda t7
    sta list_color,x
    inc list_count
@full:
    rts

BuildList:
    stz list_count
    lda list_kind
    asl a
    tax
    jmp (BuildJump,x)
BuildJump:
    .word BuildItems, BuildItems, BuildClues, BuildMove, BuildNote, BuildClues, BuildClues
    .word BuildDqChoice, BuildClues, BuildTitle

; LOOK (scene) or TOPIC (person): count, then 6-word entries (label, cond x3, script, seen flag)
BuildItems:
    lda list_kind
    cmp #LK_LOOK
    bne @topic
    lda scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+6,x
    bra @base
@topic:
    lda person
    dec a
    asl a
    asl a
    asl a
    tax
    lda PersonTable+2,x
@base:
    sta list_base
    tax
    lda a:0,x
    sta t5                      ; count
    stz t6                      ; index
    inx
    inx
@l:
    lda t6
    cmp t5
    beq @done
    phx
    lda a:2,x
    jsr CondTrue
    beq @skip
    plx
    phx
    lda a:4,x
    jsr CondTrue
    beq @skip
    plx
    phx
    lda a:6,x
    jsr CondTrue
    beq @skip
    plx
    phx
    lda a:10,x
    jsr TestFlag
    beq :+
    lda #C_GRAY
    bra :++
:   lda #C_WHITE
:   sta t7
    plx
    phx
    lda a:0,x
    jsr AddEntry
@skip:
    plx
    txa
    clc
    adc #12
    tax
    inc t6
    bra @l
@done:
    rts

; SHOW / DQCLUE: every clue noted; ITEMS / TESTI: only things / testimony
BuildClues:
    lda #1
    sta t6
    ldx #0
@l:
    lda t6
    cmp #CLUE_COUNT+1
    beq @done
    lda ClueTable,x
    jsr TestFlag
    beq @next
    lda list_kind
    cmp #LK_ITEMS
    bne :+
    lda ClueTable+6,x
    bne @next
    bra @add
:   cmp #LK_TESTI
    bne @add
    lda ClueTable+6,x
    beq @next
@add:
    lda #C_WHITE
    sta t7
    phx
    lda ClueTable+2,x
    jsr AddEntry
    plx
@next:
    txa
    clc
    adc #8
    tax
    inc t6
    bra @l
@done:
    rts

BuildMove:
    stz t6
@l:
    lda t6
    cmp #SCENE_COUNT
    beq @done
    cmp scene
    beq @next
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+8,x
    beq :+
    jsr TestFlag
    beq @next
:   lda #C_WHITE
    sta t7
    lda SceneTable,x
    jsr AddEntry
@next:
    inc t6
    bra @l
@done:
    rts

BuildNote:
    lda #C_WHITE
    sta t7
    stz t6
@l:
    lda t6
    asl a
    tax
    lda NoteTexts,x
    cpx #10
    bne @add
    ldy sound_on
    bne @add
    lda #TX_NOTE_SOUND_OFF
@add:
    jsr AddEntry
    inc t6
    lda t6
    cmp #6
    bne @l
    rts
NoteTexts:
    .word TX_NOTE_ITEMS, TX_NOTE_TESTI, TX_NOTE_HINT, TX_NOTE_DEDUCE, TX_NOTE_SAVE, TX_NOTE_SOUND_ON

BuildDqChoice:
    ldx dq_entry
    lda a:8,x
    tax
    lda a:0,x
    sta t5
    stz t6
    inx
    inx
@l:
    lda t6
    cmp t5
    beq @done
    lda #C_WHITE
    sta t7
    phx
    lda a:0,x
    jsr AddEntry
    plx
    txa
    clc
    adc #6
    tax
    inc t6
    bra @l
@done:
    rts

BuildTitle:
    lda #C_WHITE
    sta t7
    stz t6
    lda #TX_TITLE_NEW
    jsr AddEntry
    lda #C_WHITE
    ldx save_status
    cpx #2
    beq :+
    lda #C_GRAY
:   sta t7
    lda #1
    sta t6
    lda #TX_TITLE_CONT
    jmp AddEntry

UpdateList:
    lda list_kind
    cmp #LK_TITLE
    bne @game
    ; title: two rows, wrap
    lda pad_rep
    and #PAD_UP|PAD_DOWN
    beq @tkeys
    lda list_sel
    eor #1
    sta list_sel
    lda #SFX_CURSOR
    jsr PlaySfx
    jmp DrawTitleCursor
@tkeys:
    lda pad_new
    and #PAD_B
    beq @tok
    lda #SFX_CANCEL
    jsr PlaySfx
    lda #M_OPEN
    sta mode
    lda #OP_TITLE
    sta op_state
    stz op_idle
    stz op_blink
    jsr BuildUiPal
    jmp OpDrawPush
@tok:
    lda pad_new
    and #PAD_A|PAD_START
    beq :+
    lda #SFX_OK
    jsr PlaySfx
    lda list_sel
    beq @new
    jmp ContinueGame
@new:
    jmp NewGame
:   rts
@game:
    lda list_sel
    sta nav_old_sel
    lda list_top
    sta nav_old_top
    lda pad_rep
    and #PAD_UP
    beq :+
    lda list_sel
    beq @moved
    dec list_sel
    bra @moved
:   lda pad_rep
    and #PAD_DOWN
    beq :+
    lda list_sel
    inc a
    cmp list_count
    bcs @moved
    sta list_sel
    bra @moved
:   lda pad_rep
    and #PAD_LEFT|PAD_L
    beq @right
    lda list_sel
    sec
    sbc #LIST_ROWS
    bpl @store
    lda #0
    bra @store
@right:
    lda pad_rep
    and #PAD_RIGHT|PAD_R
    beq @keys
    lda list_sel
    clc
    adc #LIST_ROWS
    cmp list_count
    bcc @store
    lda list_count
    dec a
@store:
    sta list_sel
@moved:
    lda list_sel
    cmp nav_old_sel
    beq @keys
    lda #SFX_CURSOR
    jsr PlaySfx
    jsr KeepVisible
    lda list_top
    cmp nav_old_top
    beq :+
    jsr DrawRightBox
    bra @hdr
:   jsr DrawListCursor
@hdr:
    lda list_count
    cmp #LIST_ROWS+1
    bcc @ret
    lda list_sel
    jsr DivRows
    sta nav_old_top             ; (page of the new selection)
    lda nav_old_sel
    jsr DivRows
    cmp nav_old_top
    beq @ret
    jmp GameHeader
@keys:
    lda pad_new
    and #PAD_A
    beq :+
    lda list_count
    beq @ret
    lda #SFX_OK
    jsr PlaySfx
    jmp ListSelect
:   lda pad_new
    and #PAD_B
    beq @ret
    jmp ListBack
@ret:
    rts

ListSelect:
    lda list_sel
    asl a
    tax
    lda list_arg,x
    sta t6
    lda list_kind
    asl a
    tax
    lda t6
    jmp (SelectJump,x)
SelectJump:
    .word SelItem, SelItem, SelShow, SelMove, SelNote, SelClue, SelClue, DqAnswer, DqAnswer, SelTitle

SelItem:
    ; entry = list_base + 2 + index * 12
    asl a
    asl a
    sta t0
    asl a
    clc
    adc t0
    clc
    adc list_base
    tax
    lda a:12,x                  ; seen flag (entry + 10, after the count word)
    jsr SetFlag
    inc actions
    lda a:10,x                  ; script
    ldx #RET_LIST
    jmp RunScript

SelShow:
    sta t6
    inc actions
    lda person
    dec a
    asl a
    asl a
    asl a
    tay
    lda PersonTable+4,y
    tax
@l:
    lda a:0,x
    beq @default
    cmp t6
    beq @hit
    inx
    inx
    inx
    inx
    bra @l
@hit:
    lda a:2,x
    bra @run
@default:
    lda PersonTable+6,y
@run:
    ldx #RET_LIST
    jmp RunScript

SelMove:
    sta t6
    lda #SFX_MOVE
    jsr PlaySfx
    lda t6
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+2,x
    sta fade_image
    lda t6
    ldx #RET_CMD
    jmp StartFade

SelNote:
    pha
    lda list_sel
    sta note_sel
    pla
    asl a
    tax
    jmp (NoteJump,x)
NoteJump:
    .word NoteItems, NoteTesti, NoteHint, NoteDeduce, NoteSave, NoteSound

NoteItems:
    lda #LK_ITEMS
    bra NoteList
NoteTesti:
    lda #LK_TESTI
NoteList:
    sta list_kind
    jsr BuildList
    lda list_count
    bne :+
    lda #LK_NOTE
    sta list_kind
    lda #TX_NOITEMS
    ldx #RET_LIST
    jmp SysMsg
:   lda list_kind
    jmp OpenList
NoteHint:
    lda #SCR_hint
    ldx #RET_LIST
    jmp RunScript
NoteDeduce:
    lda #SCR_deduce_start
    ldx #RET_LIST
    jmp RunScript
NoteSave:
    jsr SaveGame
    lda save_ok
    beq :+
    lda #TX_SAVED
    bra :++
:   lda #TX_SAVEFAIL
:   ldx #RET_LIST
    jmp SysMsg
NoteSound:
    lda sound_on
    eor #1
    sta sound_on
    jsr ApplyAmbient
    lda sound_on
    beq :+
    lda #TX_SOUND_ON
    bra :++
:   lda #TX_SOUND_OFF
:   ldx #RET_LIST
    jmp SysMsg

SelClue:
    dec a
    asl a
    asl a
    asl a
    tax
    lda ClueTable+4,x
    ldx #RET_LIST
    jmp SysMsg

SelTitle:
    rts

ListBack:
    lda list_kind
    cmp #LK_ITEMS
    beq @note
    cmp #LK_TESTI
    beq @note
    cmp #LK_DQCHOICE
    beq @dq
    cmp #LK_DQCLUE
    beq @dq
    lda #SFX_CANCEL
    jsr PlaySfx
    lda #RET_CMD
    jmp DoReturn
@note:
    lda #SFX_CANCEL
    jsr PlaySfx
    lda #LK_NOTE
    sta list_kind
    lda note_sel
    sta list_sel
    stz list_top
    jmp ShowList
@dq:
    lda #SFX_CANCEL
    jsr PlaySfx
    stz music_lock
    jsr SceneMusic
    lda #TX_DEDUCE_QUIT
    ldx #RET_CMD
    jmp SysMsg

; ---------------------------------------------------------------- returns
MessageDone:
    lda vm_active
    beq :+
    jmp RunVM
:   lda vm_return
DoReturn:
    asl a
    tax
    jmp (ReturnJump,x)
ReturnJump:
    .word RetCmd, RetList, TitleShow, DqAsk, RetDqList, RetDqNext, RunVM

RetCmd:
    lda #M_CMD
    sta mode
    jsr PortraitOff
    jmp DrawGameScreen

RetList:
    lda list_kind
    cmp #LK_TITLE
    bne :+
    jmp TitleShow
:   jmp ShowList

; ---------------------------------------------------------------- deduction
DqAsk:
    lda dq_index
    asl a
    asl a
    sta t0
    asl a
    clc
    adc t0                      ; * 12
    clc
    adc #.loword(DeduceTable)
    sta dq_entry
    lda #$FFFF
    sta list_kind               ; not listed yet
    jsr PortraitOff
    ldx dq_entry
    lda a:2,x
    ldx #RET_DQLIST
    jmp RunScript

RetDqList:
    ldx dq_entry
    lda a:0,x
    beq :+
    lda #LK_DQCLUE
    bra :++
:   lda #LK_DQCHOICE
:   cmp list_kind
    beq :+
    lda #3                      ; cmd_active is not shown during the deduction
    sta cmd_active
    ldx dq_entry
    lda a:0,x
    beq @c
    lda #LK_DQCLUE
    jmp OpenList
@c:
    lda #LK_DQCHOICE
    jmp OpenList
:   jmp ShowList

RetDqNext:
    inc dq_index
    lda dq_index
    cmp #DEDUCE_COUNT
    bcc :+
    stz dq_index
    lda #SCR_finale
    ldx #RET_CMD
    jmp RunScript
:   jmp DqAsk

; A = argument of the chosen entry (choice index or clue id)
DqAnswer:
    sta t6
    ldx dq_entry
    lda a:0,x
    bne @clue
    ; choice list: count, then (label, correct, reply) entries
    lda a:8,x
    sta t0
    lda t6
    asl a
    sta t1
    asl a
    clc
    adc t1                      ; index * 6
    clc
    adc t0
    tax
    lda a:4,x                   ; correct
    bne @right
    lda a:6,x                   ; reply
    bra @wrong
@clue:
    lda a:8,x
    tax
    lda a:0,x
    sta t5                      ; accepted count
    inx
    inx
@acc:
    lda t5
    beq @spec
    lda a:0,x
    cmp t6
    beq @right
    inx
    inx
    dec t5
    bra @acc
@spec:
    lda a:0,x
    sta t5                      ; specific wrong replies
    inx
    inx
@sp:
    lda t5
    beq @generic
    lda a:0,x
    cmp t6
    beq :+
    inx
    inx
    inx
    inx
    dec t5
    bra @sp
:   lda a:2,x
    bra @wrong
@generic:
    ldx dq_entry
    lda a:6,x
@wrong:
    pha
    inc wrong_count
    lda #SFX_WRONG
    jsr PlaySfx
    pla
    ldx #RET_DQLIST
    jmp RunScript
@right:
    lda #SFX_RIGHT
    jsr PlaySfx
    ldx dq_entry
    lda a:4,x
    ldx #RET_DQNEXT
    jmp RunScript

; ---------------------------------------------------------------- scenes and fades
; A = scene (and its song, unless a script chose one)
SetScene:
    jsr SetSceneQuiet
    jmp SceneMusic

SetSceneQuiet:
    sta scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+4,x
    sta person
    jmp ApplyAmbient

; A = scene ($FFFF = keep), fade_image = picture, X = where to go afterwards
StartFade:
    sta fade_scene
    stx fade_return
    lda fade_image
    cmp image_cur
    bne :+
    ; same picture: no fade
    lda fade_scene
    bmi FadeDone
    jsr SetScene
    jmp FadeDone
:   lda #M_FADE
    sta mode
    lda #1
    sta fade_state
    lda #16
    sta fade_level
    rts

FadeDone:
    stz fade_state
    lda fade_return
    cmp #RET_TITLE
    beq :+
    jsr GameHeader
:   lda fade_return
    jmp DoReturn

UpdateFade:
    lda fade_state
    cmp #1
    bne @load
    lda fade_level
    sec
    sbc #2
    sta fade_level
    jsr FadePalette
    lda fade_level
    bne @ret
    ; black: switch the picture and start the tile stream
    stz por_rows
    stz por_shown
    lda fade_scene
    bmi :+
    jsr SetScene
:   lda fade_image
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
    sta fade_state
    lda fade_return
    cmp #RET_TITLE
    beq @ret
    jmp GameHeader
@load:
    cmp #2
    bne @in
    lda img_left
    bne @ret
    lda #3
    sta fade_state
    rts
@in:
    lda fade_level
    clc
    adc #2
    sta fade_level
    jsr FadePalette
    lda fade_level
    cmp #16
    bne @ret
    jmp FadeDone
@ret:
    rts

; pal_buf = palette of image_cur at fade_level (0-16)
FadePalette:
    lda image_cur
    asl a
    asl a
    tax
    lda ImageTable+2,x
    sta p1
    lda fade_level
    sta pal_level
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
    tyx
    sta f:pal_buf,x
    iny
    iny
    cpy #480
    bne @l
    lda #1
    sta pal_dirty
    rts

FadeTab:
.repeat 17, L
  .repeat 32, V
    .byte (V * L) / 16
  .endrepeat
.endrepeat

; ---------------------------------------------------------------- portrait overlay
PortraitOn:
    lda scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+10,x
    beq @ret
    cmp por_shown
    beq @ret
    sta por_shown
    dec a
    sta por_index
    lda #1
    sta por_on
    bra PortraitStream
@ret:
    rts

PortraitOff:
    lda por_shown
    beq @ret
    dec a
    sta por_index
    stz por_on
    stz por_shown
    bra PortraitStream
@ret:
    rts

PortraitStream:
    lda por_index
    asl a
    asl a
    sta t0
    asl a
    clc
    adc t0
    tax
    lda PortraitTable+6,x
    sta por_rows
    stz por_row
    rts

; ---------------------------------------------------------------- title, new game, continue
; The title menu (はじめから / つづきから) under the logo; the title screen itself is src/adv/opening.inc.
TitleShow:
    jsr ApplyAmbient
    lda #LK_TITLE
    sta list_kind
    stz list_sel
    stz list_top
    lda #M_LIST
    sta mode
    stz hp_count
    jsr DrawTitleScreen
    jsr CheckSave
    jsr BuildList
    lda save_status
    cmp #2
    bne :+
    lda #1
    sta list_sel                ; a valid record: the cursor starts on つづきから
:   jmp DrawTitleList

NewGame:
    jsr GameScreenIn
    ldx #0
:   stz flags,x
    inx
    inx
    cpx #128
    bne :-
    stz actions
    stz wrong_count
    stz dq_index
    stz cmd_sel
    lda #START_SCENE
    jsr SetSceneQuiet           ; (the song starts with the first picture of the intro)
    lda #SCR_intro
    ldx #RET_CMD
    jmp RunScript

ContinueGame:
    lda save_status
    bne :+
    lda #TX_NORECORD
    ldx #RET_TITLE
    jmp SysMsg
:   cmp #1
    bne :+
    lda #TX_BROKEN
    ldx #RET_TITLE
    jmp SysMsg
:   jsr GameScreenIn
    jsr LoadSave
    stz dq_index
    stz cmd_sel
    lda #ScrResume
    ldx #RET_CMD
    jmp RunScript

ScrResume:
    .word OP_RESUME, OP_TEXT, TX_LOADED, OP_END

; leaving the title for a game: the title song fades, the empty game frame in the game's colours
GameScreenIn:
    stz music_lock
    jsr MusicFadeOut
    jsr InitBitmap
    jmp GameColors

; ---------------------------------------------------------------- ending
EnterEnding:
    lda #M_END
    sta mode
    inc ending_seen
    jsr PortraitOff
    lda #TX_HDR_END
    sta hp_val
    stz hp_kind
    lda #2
    sta hp_count
    lda #TX_HDR_GAME
    jsr DrawHeader
    jsr ClearInterior
    lda #TX_END_TITLE
    jsr TextPtr
    jsr TextWidth
    lsr a
    eor #$FFFF
    sec
    adc #128
    sta g_x
    lda #ROW_Y0
    sta g_y
    lda #C_YELLOW
    sta g_c
    lda #TX_END_TITLE
    jsr DrawTextId
    lda #44
    sta g_x
    lda #ROW_Y0+18
    sta g_y
    lda #C_WHITE
    sta g_c
    lda #TX_END_ACTIONS
    jsr DrawTextId
    lda #176
    sta g_x
    lda #.loword(DigitGlyphs)
    sta p1
    lda actions
    jsr DrawNumber
    lda #44
    sta g_x
    lda #ROW_Y0+35
    sta g_y
    lda #TX_END_WRONG
    jsr DrawTextId
    lda #176
    sta g_x
    lda wrong_count
    jsr DrawNumber
    lda #TX_END_PRESS
    jsr TextPtr
    jsr TextWidth
    lsr a
    eor #$FFFF
    sec
    adc #128
    sta g_x
    lda #ROW_Y0+56
    sta g_y
    lda #C_GRAY
    sta g_c
    lda #TX_END_PRESS
    jmp DrawTextId

UpdateEnd:
    lda pad_new
    and #PAD_A|PAD_START
    beq :+
    lda #SFX_OK
    jsr PlaySfx
    jmp TitleFromGame
:   rts
