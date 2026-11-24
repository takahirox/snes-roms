"""Write real bookmarks with the baseline ROM and prepare pad-only cold boot checks."""
import hashlib
import json

from drive import Driver, ST
from run import checkpoint, global_block, is_read, slot_block


def resume_state(game, point):
    state = {w: game.w(w) for w in ('ui_state', 'speed', 'loads_done', 'sram_resets')}
    state.update(gendings=int.from_bytes(game.b('gendings', 4), 'little'),
                 gflags=int.from_bytes(game.b('gflags', 4), 'little'))
    if point == 'title':
        state.update(names=game.b('names', 20).hex(), slot_any=game.w('slot_any'),
                     menu=[game.w('menu_kind', 2 * i) for i in range(game.w('menu_count'))])
    else:
        fields, silhouettes, lflags, names = checkpoint(game)
        state.update(scene=[fields, [list(entry) for entry in silhouettes]], lflags=lflags.hex(), names=names.hex())
        if point == 'paragraph':
            state.update(text=game.w('cur_text'), read=game.w('cur_read'))
        else:
            state.update(choice=game.w('choice_id'), last_text=game.w('last_text'),
                         options=game.w('opt_count'), text_on=game.w('text_on'))
    return state


def ending_seed(build, traces):
    # E01 is the main ending and sets the production clears used by gated choices. Use
    # the production input sequence but start from blank battery SRAM on the baseline.
    trace = json.loads((traces / 'real_E01.json').read_text())
    game = Driver(build=build, sram=bytes(8192))
    try:
        for mask in trace['masks']:
            game.e.mask = mask
            game.e.lib.retro_run()
        e01 = next(i for i, ending in enumerate(game.layout['endings']) if ending['id'] == 'E01')
        sram = game.sram_image()
        end = global_block(sram)
        assert end['endings'] == 1 << e01, end
        unlocks = game.layout['endings'][e01]['sets']
        assert unlocks and end['gflags'] == sum(1 << game.layout['gflags'].index(f) for f in unlocks), end
        return sram
    finally:
        game.close()


def save_bookmark(game, slot, state):
    game.press('START', 'MENU')
    game.menu_to(0)
    game.press('A', 'SLOTS')
    game.menu_to(slot)
    game.press('A', state)
    assert game.w('save_ok') == 1


def write_bookmarks(build, seed):
    game = Driver(build=build, sram=seed)
    try:
        game.title()
        game.menu_to(game.title_items().index(0))
        game.tap('A', 2, 4)
        for field in range(2):
            game.until(lambda: game.state() == 'NAME' and game.w('ne_field') == field)
            original = game.name_glyphs(field)
            game.tap('B', 2, 6)
            game.name_pick(0, field)
            assert game.name_glyphs(field) != original, 'expected a custom name'
            game.tap('START', 2, 6)

        game.until(lambda: game.state() == 'WAIT', 2000, 'first paragraph')
        game.press('START', 'MENU')
        game.menu_to(1)
        game.tap('A', 2, 30)
        assert game.w('speed') == 2, 'expected a non-default speed'
        game.press('B', 'WAIT')
        assert game.advance() == 'CHOICE'
        game.choose(target='pro_camera')
        # Save a paragraph with a nonzero local flag, then advance to and save a choice.
        for _ in range(3000):
            if game.state() == 'WAIT' and any(game.b('lflags', 64)):
                break
            if game.state() in ('WAIT', 'TYPE'):
                game.tap('A', 1, 1)
            else:
                game.run(1)
        assert game.state() == 'WAIT' and any(game.b('lflags', 64)), 'paragraph with local flags'
        paragraph = resume_state(game, 'paragraph')
        assert paragraph['scene'][1], 'paragraph with an active silhouette'
        save_bookmark(game, 1, 'WAIT')
        assert game.advance() == 'CHOICE'
        choice = resume_state(game, 'choice')
        assert choice['last_text'] != 0xffff and choice['options'] >= 2 and choice['text_on'] == 1
        save_bookmark(game, 2, 'CHOICE')
        sram = game.sram_image()
        assert slot_block(sram, 1) == dict(valid=True, kind=1, id=paragraph['text'])
        assert slot_block(sram, 2) == dict(valid=True, kind=2, id=choice['choice'])
        assert is_read(sram, paragraph['text']) and is_read(sram, choice['last_text'])
        return sram, (paragraph, choice)
    finally:
        game.close()


def prepare_bookmarks(build, traces, out):
    out.mkdir(parents=True, exist_ok=True)
    seed = ending_seed(build, traces) if traces is not None else bytes(8192)
    sram, bookmarks = write_bookmarks(build, seed)
    paths = []
    for slot, (point, expected) in enumerate(zip(('paragraph', 'choice'), bookmarks), 1):
        # Take the pad sequence from a fresh baseline session with the same battery.
        # The replay workers apply it to both ROMs in separate processes on both cores.
        game = Driver(build=build, sram=sram)
        try:
            game.title()
            title = resume_state(game, 'title')
            assert title['ui_state'] == ST['TITLE'] and title['slot_any'] == 1 and 1 in title['menu']
            for field in ('speed', 'gendings', 'gflags', 'names'):
                assert title[field] == expected[field], (field, title, expected)
            assert title['sram_resets'] == title['loads_done'] == 0
            title_frame = game.frame
            game.title_pick(1)
            game.until(lambda: game.state() == 'SLOTS', 300, 'load slots')
            game.menu_to(slot)
            state = 'WAIT' if point == 'paragraph' else 'CHOICE'
            game.press('A', state, limit=1200)
            game.run(10)  # let queued graphics finish on both cores
            resumed = resume_state(game, point)
            expected = dict(expected, loads_done=1, sram_resets=0)
            if point == 'paragraph':
                expected['read'] = 1
            assert resumed == expected, (point, resumed, expected)
            assert game.sram_image() == sram, 'loading or redrawing changed the battery'
            path = out / f'upgrade_{point}.json'
            digest = hashlib.sha256(sram).hexdigest()
            path.write_text(json.dumps(dict(
                masks=game.masks, input_sram_sha256=digest, output_sram_sha256=digest,
                captures=[dict(frame=game.frame)],
                checkpoints={title_frame: ('title', title), game.frame: (point, resumed)},
            )) + '\n')
            path.with_suffix('.in.srm').write_bytes(sram)
            paths.append(path)
        finally:
            game.close()
    return paths
