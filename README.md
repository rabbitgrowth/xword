# xword-vim

The goal here is to build a Terminal-based crossword solving interface with Vim-like keybindings.
This means that you press `i` to enter “insert mode” to start typing answers,
`<Esc>` or `jk` to quit insert mode, `h` `j` `k` `l` to move around the grid,
`w` to jump to the next clue and `b` to the previous clue, etc.
Keys like `0` `$` `r` `x` `f` `F` `t` `T` `;` `,` `}` `{` should also work as you expect.

I made this mostly for my own use
(how big is the overlap between “crossword enthusiasts” and “Vim enthusiasts”, I wonder?),
so documentation is currently lacking, but basically you run this with

```
$ python3 xword.py path/to/your/puzzle.puz
```

and start solving.
To switch directions, press Space.
To check your answers, type `:check`,
or `:check!` if you also want to have the wrong answers marked with crosses.
When you’re done, type `:q` to quit.

I’m just a hobbyist programmer, so the code is probably not very good.
There aren’t any tests yet, and certain core features are still missing.
For example, rebuses and circled squares aren’t supported, and you can’t save your progress.
