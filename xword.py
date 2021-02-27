import curses
import os
import struct
import sys
from collections import defaultdict
from itertools   import groupby
from string      import ascii_lowercase
from textwrap    import TextWrapper

ENCODING = 'iso-8859-1' # used by the .puz format

BLACK = '.'
EMPTY = '-'

DIRECTIONS = ('across', 'down')

LETTERS = set(ascii_lowercase)

WRAPPER = TextWrapper(width             = 32,
                      initial_indent    = ' '*4,
                      subsequent_indent = ' '*4)

#         xpos     ypos    shape
SHAPES = {'head': {'head': 'topleft',
                   'body': 'left',
                   'tail': 'bottomleft'},
          'body': {'head': 'top',
                   'body': 'middle',
                   'tail': 'bottom'},
          'tail': {'head': 'topright',
                   'body': 'right',
                   'tail': 'bottomright'}}

#           shape          boldness
VERTICES = {'topleft':     {'light':       '┌',
                            'topleft':     '┏'},
            'top':         {'light':       '┬',
                            'topleft':     '┲',
                            'topright':    '┱',
                            'horizontal':  '┯'},
            'topright':    {'light':       '┐',
                            'topright':    '┓'},
            'left':        {'light':       '├',
                            'topleft':     '┢',
                            'bottomleft':  '┡',
                            'vertical':    '┠'},
            'middle':      {'light':       '┼',
                            'topleft':     '╆',
                            'topright':    '╅',
                            'bottomleft':  '╄',
                            'bottomright': '╃',
                            'horizontal':  '┿',
                            'vertical':    '╂'},
            'right':       {'light':       '┤',
                            'topright':    '┪',
                            'bottomright': '┩',
                            'vertical':    '┨'},
            'bottomleft':  {'light':       '└',
                            'bottomleft':  '┗'},
            'bottom':      {'light':       '┴',
                            'bottomleft':  '┺',
                            'bottomright': '┹',
                            'horizontal':  '┷'},
            'bottomright': {'light':       '┘',
                            'bottomright': '┛'}}

#        direction      bold?
EDGES = {'horizontal': {False: '─',
                        True:  '━'},
         'vertical':   {False: '│',
                        True:  '┃'}}

SHADE = '░'

class Puzzle:
    def __init__(self,
                 answers, buffer, cluelist,
                 title, author, copyright, notes):
        self.answers = answers
        self.buffer  = buffer

        self.width  = len(answers[0])
        self.height = len(answers)

        self.title     = title
        self.author    = author
        self.copyright = copyright
        self.notes     = notes

        # Map coords that start clues (across or down)
        # to lists of coords the clues span
        starts = {direction: {} for direction in DIRECTIONS}

        def key(pair):
            index, square = pair
            return square != BLACK

        for y, row in enumerate(self.buffer):
            for white, pairs in groupby(enumerate(row), key=key):
                if white:
                    xs = [x for x, _ in pairs]
                    starts['across'][(xs[0], y)] = [(x, y) for x in xs]

        for x, col in enumerate(zip(*self.buffer)):
            for white, pairs in groupby(enumerate(col), key=key):
                if white:
                    ys = [y for y, _ in pairs]
                    starts['down'][(x, ys[0])] = [(x, y) for y in ys]

        self.clues   = {direction: [] for direction in DIRECTIONS}
        self.numbers = {}
        cluelist     = iter(cluelist)
        number       = 1

        self.clue_by_coords = {direction: {} for direction in DIRECTIONS}
        self.clue_by_number = {direction: {} for direction in DIRECTIONS}

        for y in range(self.height):
            for x in range(self.width):
                numbered = False
                for direction in DIRECTIONS:
                    if (x, y) in starts[direction]:
                        span = starts[direction][(x, y)]
                        text = next(cluelist)
                        clue = Clue(number, span, text)
                        self.clues[direction].append(clue)
                        for coords in span:
                            self.clue_by_coords[direction][coords] = clue
                        self.clue_by_number[direction][number] = clue
                        numbered = True
                if numbered:
                    self.numbers[(x, y)] = number
                    number += 1

        for direction in DIRECTIONS:
            prev_clue = None
            for clue in self.clues[direction]:
                if prev_clue is not None:
                    clue.prev = prev_clue
                    prev_clue.next = clue
                prev_clue = clue

        self.mode      = 'normal'
        self.direction = 'across'

        # Initialize the cursor position to the first square of the
        # first across clue, which is not necessarily (0, 0), since
        # there could be black squares in the top left-hand corner.
        self.x, self.y = self.clues[self.direction][0].span[0]

    def run(self):
        # Prevent escape key delay
        os.environ.setdefault('ESCDELAY', '0')

        def main(stdscr):
            # Make cursor invisible
            curses.curs_set(0)
            # Compute size of puzzle grid
            nrows = self.height * 2 + 1 # or, in curses lingo, `nlines`
            ncols = self.width  * 4 + 1
            # Draw static stuff
            stdscr.addstr(0, 0, self.title)
            stdscr.addstr(1, 0, self.author)
            stdscr.addstr(3, ncols + 2,  'Across')
            stdscr.addstr(3, ncols + 36, 'Down')
            stdscr.refresh()
            # As a bit of an ugly hack to get around the curses quirk of not
            # allowing writing at the bottom right corner, add an extra line
            # at the bottom of windows that can be filled to the brim
            self.main_grid = curses.newwin(nrows + 1, ncols, 3, 0)
            self.mode_line = curses.newwin(1, ncols, nrows + 4, 0)
            self.clue_grids = {'across': curses.newwin(nrows, 33, 4, ncols + 2),
                               'down':   curses.newwin(nrows, 33, 4, ncols + 36)}
            while True:
                self.render_main_grid()
                self.render_clue_grids()
                self.handle(stdscr.getkey())

        curses.wrapper(main)

    def render_main_grid(self):
        self.main_grid.erase()

        span       = self.current_clue.span
        boldnesses = {}
        if self.direction == 'across':
            x, y = span[0]
            boldnesses[(x, y    )] = 'topleft'
            boldnesses[(x, y + 1)] = 'bottomleft'
            for x, y in span[1:]:
                boldnesses[(x, y    )] = 'horizontal'
                boldnesses[(x, y + 1)] = 'horizontal'
            x, y = span[-1]
            boldnesses[(x + 1, y    )] = 'topright'
            boldnesses[(x + 1, y + 1)] = 'bottomright'
        else:
            x, y = span[0]
            boldnesses[(x,     y)] = 'topleft'
            boldnesses[(x + 1, y)] = 'topright'
            for x, y in span[1:]:
                boldnesses[(x,     y)] = 'vertical'
                boldnesses[(x + 1, y)] = 'vertical'
            x, y = span[-1]
            boldnesses[(x,     y + 1)] = 'bottomleft'
            boldnesses[(x + 1, y + 1)] = 'bottomright'

        vertices = []
        for y in range(self.height + 1):
            row = []
            for x in range(self.width + 1):
                xpos     = {0: 'head', self.width:  'tail'}.get(x, 'body')
                ypos     = {0: 'head', self.height: 'tail'}.get(y, 'body')
                shape    = SHAPES[xpos][ypos]
                boldness = boldnesses.get((x, y), 'light')
                vertex   = VERTICES[shape][boldness]
                row.append(vertex)
            vertices.append(row)

        for y, row in enumerate(self.buffer):
            pairs = list(enumerate(row))

            for x, square in pairs:
                vertex = vertices[y][x]
                number = self.numbers.get((x, y))
                number = '' if number is None else str(number)
                bold   = boldnesses.get((x, y)) in ('topleft', 'bottomleft', 'horizontal')
                edge   = EDGES['horizontal'][bold]
                padded = number.ljust(3, edge)
                self.main_grid.addstr(vertex + padded)

            self.main_grid.addstr(vertices[y][x + 1])

            for x, square in pairs:
                if square == BLACK:
                    fill = SHADE * 3
                else:
                    left   = '>' if (x, y) == self.current_coords else ' '
                    middle = ' ' if square == EMPTY else square
                    right  = ' ' # could be used to indicate status;
                                 # hard-code to be blank for now
                    fill   = left + middle + right
                bold = boldnesses.get((x, y)) in ('topleft', 'topright', 'vertical')
                edge = EDGES['vertical'][bold]
                self.main_grid.addstr(edge + fill)

            bold = boldnesses.get((x + 1, y)) in ('topright', 'vertical')
            edge = EDGES['vertical'][bold]
            self.main_grid.addstr(edge)

        y = self.height
        for x in range(self.width):
            vertex = vertices[y][x]
            bold   = boldnesses.get((x, y)) in ('bottomleft', 'horizontal')
            edge   = EDGES['horizontal'][bold]
            self.main_grid.addstr(vertex + edge * 3)

        vertex = vertices[y][x + 1]
        self.main_grid.addstr(vertex)

        self.main_grid.refresh()

    def render_clue_grids(self):
        nrows = self.height * 2

        for direction, clue_grid in self.clue_grids.items():
            clue_grid.erase()

            lines   = []
            heights = []
            active_clue = self.clue_by_coords[direction][self.current_coords]

            for index, clue in enumerate(self.clues[direction]):
                active = clue is active_clue
                render = clue.render(active)
                lines.extend(render)
                heights.append(len(render))
                if active:
                    active_index = index

            if sum(heights[active_index:]) > nrows: # >= also works
                start   = sum(heights[:active_index])
                section = slice(start, start + nrows)
            else:
                section = slice(-nrows, None)

            clue_grid.addstr('\n'.join(lines[section]))
            clue_grid.refresh()

    def handle(self, key):
        # Keys that work in all modes
        if key == '\t':
            self.next()
        elif key == '?':
            self.reveal()
        else:
            # Keys specific to normal mode
            if self.mode == 'normal':
                if key == 'k':
                    self.move(0, -1)
                elif key == 'j':
                    self.move(0, 1)
                elif key == 'h':
                    self.move(-1, 0)
                elif key == 'l':
                    self.move(1, 0)
                elif key == '0':
                    self.start()
                elif key == '$':
                    self.end()
                elif key == 'w':
                    self.next()
                elif key == 'b':
                    self.prev()
                elif key == 'r':
                    self.replace()
                elif key == 'x':
                    self.delete()
                elif key == ' ':
                    self.toggle()
                elif key in ('i', 'a'):
                    self.insert()
                elif key == ']':
                    self.next_empty()
                elif key == '[':
                    self.prev_empty()
                elif key == 'q':
                    sys.exit(0)
            # Keys specific to insert mode
            else:
                if key == '\x1b':
                    self.escape()
                elif key == 'j':
                    next_key = self.main_grid.getkey()
                    if next_key == 'k':
                        self.escape()
                    else:
                        self.type('j')
                        self.advance()
                        self.handle(next_key)
                elif key == '\x7f':
                    self.backspace()
                else:
                    self.type(key)
                    self.advance()

    @property
    def current_coords(self):
        return (self.x, self.y)

    @property
    def current_clue(self):
        return self.clue_by_coords[self.direction][self.current_coords]

    def in_range(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def is_white(self, x, y):
        return self.get(x, y) not in (BLACK, None)

    def get(self, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        if not self.in_range(x, y):
            return None
        return self.buffer[y][x]

    def set(self, letter, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        if not self.in_range(x, y):
            raise IndexError(f'Trying to assign to out-of-range square ({x}, {y})')
        self.buffer[y][x] = letter

    def jump(self, x, y):
        self.x = x
        self.y = y

    def move(self, dx, dy):
        x = self.x
        y = self.y
        x += dx
        y += dy
        while self.get(x, y) == BLACK:
            x += dx
            y += dy
        if self.get(x, y) is not None:
            self.jump(x, y)

    def start(self):
        self.jump(*self.current_clue.span[0])

    def end(self):
        self.jump(*self.current_clue.span[-1])

    def next(self):
        next_clue = self.current_clue.next
        if next_clue is not None:
            self.jump(*next_clue.span[0])
        else:
            self.jump(*self.clues[self.other_direction(self.direction)][0].span[0])
            self.toggle()

    def prev(self):
        prev_clue = self.current_clue.prev
        if prev_clue is not None:
            self.jump(*prev_clue.span[0])
        else:
            self.jump(*self.clues[self.other_direction(self.direction)][-1].span[0])
            self.toggle()

    def replace(self):
        key = self.main_grid.getkey()
        self.type(key)

    def delete(self, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        self.set(EMPTY, x, y)

    @staticmethod
    def other_direction(direction):
        return 'down' if direction == 'across' else 'across'

    def toggle(self):
        self.direction = self.other_direction(self.direction)

    def insert(self):
        self.mode = 'insert'
        self.mode_line.addstr('-- INSERT --')
        self.mode_line.refresh()

    def escape(self):
        self.mode = 'normal'
        self.mode_line.erase()
        self.mode_line.refresh()

    def type(self, key):
        if key in LETTERS:
            self.set(key.upper())

    def reveal(self):
        self.set(self.answers[self.y][self.x])
        self.advance()

    def backspace(self):
        self.retreat()
        self.delete()

    def advance(self):
        if self.direction == 'across':
            next_coords = (self.x + 1, self.y)
        else:
            next_coords = (self.x, self.y + 1)
        if not self.is_white(*next_coords):
            self.next()
            # self.next() already jumps to the start,
            # so there's no need to write self.start() here
            # (compare with retreat() below)
        else:
            self.jump(*next_coords)

    def retreat(self):
        if self.direction == 'across':
            prev_coords = (self.x - 1, self.y)
        else:
            prev_coords = (self.x, self.y - 1)
        if not self.is_white(*prev_coords):
            self.prev()
            self.end()
        else:
            self.jump(*prev_coords)

    def next_empty(self):
        while True:
            self.advance()
            if self.get() == EMPTY:
                break

    def prev_empty(self):
        while True:
            self.retreat()
            if self.get() == EMPTY:
                break

class Clue:
    def __init__(self, number, span, text):
        self.number = number
        self.span   = span
        self.text   = text
        self.prev   = None
        self.next   = None

    def render(self, active):
        lines    = WRAPPER.wrap(self.text)
        cursor   = '>' if active else ' '
        lines[0] = f'{cursor}{self.number:>2} ' + lines[0][4:]
        return lines

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip checksums, file magic, etc. for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answers, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                           for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        title     = strings[0]
        author    = strings[1]
        copyright = strings[2]
        cluelist  = strings[3:3+nclues]
        notes     = strings[3+nclues:]
        assert len(cluelist) == nclues, f'Expected {nclues} clues, got {len(cluelist)}'
        return Puzzle(answers, buffer, cluelist, title, author, copyright, notes)

if __name__ == '__main__':
    puzzle = parse(sys.argv[1])
    puzzle.run()
