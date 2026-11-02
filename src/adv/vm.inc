; ---------------------------------------------------------------- script VM
; Scripts are word lists in bank 0 (built from data/adv/story.txt).  The VM runs until an operation
; has to wait (a message or a fade) and resumes from MessageDone / FadeDone.
.a16
.i16

RunVM:
    ldx vm_pc
    lda a:0,x
    inx
    inx
    stx vm_pc
    cmp #OP_MUSIC+1
    bcc :+
    lda #OP_END                 ; unknown operation: stop
:   asl a
    tax
    jmp (VmOps,x)
VmOps:
    .word OpEnd, OpText, OpSet, OpClr, OpIf, OpIfn, OpJmp, OpGoto, OpImage, OpSfx, OpCall, OpDeduce
    .word OpEnding, OpEnd, OpResume, OpMusic

VmArg:
    ldx vm_pc
    lda a:0,x
    inx
    inx
    stx vm_pc
    rts

OpEnd:
    lda vm_sp
    beq @fin
    dec a
    dec a
    sta vm_sp
    tax
    lda vm_stack,x
    sta vm_pc
    jmp RunVM
@fin:
    stz vm_active
    lda vm_return
    jmp DoReturn

OpText:
    jsr VmArg
    jmp OpenMessage

OpSet:
    jsr VmArg
    jsr SetFlag
    jmp RunVM

OpClr:
    jsr VmArg
    jsr ClrFlag
    jmp RunVM

OpIf:
    jsr VmArg
    jsr TestFlag
    beq OpSkip
OpJmp:
    jsr VmArg
    sta vm_pc
    jmp RunVM

OpIfn:
    jsr VmArg
    jsr TestFlag
    beq OpJmp
OpSkip:
    jsr VmArg
    jmp RunVM

OpGoto:
    jsr VmArg
    pha
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+2,x
    sta fade_image
    pla
    ldx #RET_VM
    jmp StartFade

OpImage:
    jsr VmArg
    sta fade_image
    lda #$FFFF
    ldx #RET_VM
    jmp StartFade

OpResume:
    lda scene
    asl a
    asl a
    asl a
    asl a
    tax
    lda SceneTable+2,x
    sta fade_image
    lda scene
    ldx #RET_VM
    jmp StartFade

OpSfx:
    jsr VmArg
    jsr PlaySfx
    jmp RunVM

OpCall:
    jsr VmArg
    pha
    lda vm_sp
    cmp #16
    bcs @full
    tax
    lda vm_pc
    sta vm_stack,x
    inx
    inx
    stx vm_sp
    pla
    sta vm_pc
    jmp RunVM
@full:
    pla
    jmp RunVM

OpDeduce:
    lda #RET_DQSTART
    sta vm_return
    jmp RunVM

OpEnding:
    stz vm_active
    jmp EnterEnding

; music: SONG (the song stays over scene changes) / music: scene ($FF: the scene's song again)
OpMusic:
    jsr VmArg
    cmp #$FF
    bne @song
    stz music_lock
    jsr SceneMusic
    jmp RunVM
@song:
    ldx #1
    stx music_lock
    jsr PlayMusic
    jmp RunVM
