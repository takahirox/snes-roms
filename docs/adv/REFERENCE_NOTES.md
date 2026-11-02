# Reference notes on command-selection adventure games

This is material for checking how investigation is operated and presented, not for using any original scenario or assets. The control references below are the Virtual Console manual of the original Famicom game, not frame measurements of the SFC remake.

- [Nintendo official manual: 探偵倶楽部PART II (Tantei Club Part II)](https://www.nintendo.co.jp/data/software/manual/man_tb8j.pdf): p6 confirms Up/Down to select, A to confirm/advance, B to cancel; p16–18 confirm messages / commands / target subcommands, examining a spot with a cursor, deduction, and in-game saving.
- [Nintendo official introduction page](https://www.nintendo.com/jp/switch/aw3ca/index.html): the modern version also progresses with commands such as move, ask, call, look/examine. This is a reference for the lineage of controls, not a depiction of the SFC version's screens.
- [PVSnesLib Backgrounds](https://github.com/alekmaul/pvsneslib/wiki/Backgrounds): Mode 3 is BG1 8bpp and BG2 4bpp. Reference for the design of showing a single background picture and UI text on separate PPU layers.

In this game's design, the player selects a place, a person and a target to gather information, accumulates it in the notebook, and progresses by presenting evidence and deducing. Pointless repetition and wrong choices that create unwinnable states are avoided. The premise and solution of the case are original, and UI and artwork are not copied as is.

The backgrounds were newly generated with the imagegen skill's builtin image_gen. The full-size generated images and generation prompts are recorded in assets/adv/ART.json, the conversion to hardware size in assets/adv/PREPARED.json, and the tool in tools/prepare_art.py (relative to this file). Since the clocks and object shapes in the generated pictures do not guarantee correct reasoning, any part used as an in-game clue is checked for consistency separately.
