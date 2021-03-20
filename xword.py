import curses
import os
import struct
import sys
from collections import defaultdict
from itertools   import chain, dropwhile, groupby
from string      import ascii_uppercase, ascii_lowercase
from textwrap    import TextWrapper

ENCODING = 'iso-8859-1' # used by the .puz format

BLACK = '.'
EMPTY = '-'

NORMAL = ' '
PENCIL = '?'
CROSS  = 'x'

DIRECTIONS = ('across', 'down')

UPPERCASE = set(ascii_uppercase)
LOWERCASE = set(ascii_lowercase)

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
VERTICES = {'topleft':     {'normal':      '┌',
                            'topleft':     '┏'},
            'top':         {'normal':      '┬',
                            'topleft':     '┲',
                            'topright':    '┱',
                            'horizontal':  '┯'},
            'topright':    {'normal':      '┐',
                            'topright':    '┓'},
            'left':        {'normal':      '├',
                            'topleft':     '┢',
                            'bottomleft':  '┡',
                            'vertical':    '┠'},
            'middle':      {'normal':      '┼',
                            'topleft':     '╆',
                            'topright':    '╅',
                            'bottomleft':  '╄',
                            'bottomright': '╃',
                            'horizontal':  '┿',
                            'vertical':    '╂'},
            'right':       {'normal':      '┤',
                            'topright':    '┪',
                            'bottomright': '┩',
                            'vertical':    '┨'},
            'bottomleft':  {'normal':      '└',
                            'bottomleft':  '┗'},
            'bottom':      {'normal':      '┴',
                            'bottomleft':  '┺',
                            'bottomright': '┹',
                            'horizontal':  '┷'},
            'bottomright': {'normal':      '┘',
                            'bottomright': '┛'}}

#        direction     bold?
EDGES = {'horizontal': '─━',
         'vertical':   '│┃'}

SHADE = '░'

class Puzzle:
    def __init__(self, answer, buffer, cluelist, title, author, copyright, notes):
        self.grid = [[Square(x, y, a, b)
                      for x, (a, b) in enumerate(zip(answer_row, buffer_row))]
                     for y, (answer_row, buffer_row) in enumerate(zip(answer, buffer))]

        self.width  = len(self.grid[0])
        self.height = len(self.grid)

        self.title     = title
        self.author    = author
        self.copyright = copyright
        self.notes     = notes

        # Map squares that start clues to the squares the clues span
        spans = {direction: {} for direction in DIRECTIONS}

        for direction, grid in zip(DIRECTIONS, (self.grid, zip(*self.grid))):
            for row in grid: # or column
                for black, squares in groupby(row, key=lambda square: square.black):
                    if not black: # contiguous sequence of white squares
                        squares = list(squares)
                        spans[direction][squares[0]] = squares

        # Assign clue numbers
        number     = 1
        cluelist   = iter(cluelist)
        self.clues = {direction: [] for direction in DIRECTIONS}

        for row in self.grid:
            for square in row:
                numbered = False
                for direction in DIRECTIONS:
                    span = spans[direction].get(square)
                    if span is not None:
                        text = next(cluelist)
                        clue = Clue(number, text, span)
                        self.clues[direction].append(clue)
                        square.number = number
                        for other_square in span:
                            other_square.clues[direction] = clue
                        numbered = True
                if numbered:
                    number += 1

        # Doubly-link clues and squares
        for direction, clues in self.clues.items():
            prev_clue   = None
            prev_square = None

            for clue in clues:
                if prev_clue is not None:
                    clue.prev = prev_clue
                    prev_clue.next = clue
                prev_clue = clue

                for square in clue.span:
                    if prev_square is not None:
                        square.prev[direction] = prev_square
                        prev_square.next[direction] = square
                    prev_square = square

        self.mode      = 'normal'
        self.direction = 'across'

        # Initialize the cursor position to the first square of the
        # first across clue, which is not necessarily (0, 0), since
        # there could be black squares in the top left-hand corner.
        self.x, self.y = self.clues[self.direction][0].span[0]

        self.find_letter  = None
        self.find_forward = None

    def run(self):
        # Prevent escape key delay
        os.environ.setdefault('ESCDELAY', '0')

        def main(stdscr):
            # Hide cursor
            curses.curs_set(0)
            # Compute size of puzzle grid
            nrows = self.height * 2 + 1 # or, in curses lingo, `nlines`
            ncols = self.width  * 4 + 1
            # Draw static stuff
            stdscr.addstr(0, 0, self.title, curses.A_BOLD)
            stdscr.addstr(1, 0, self.author)
            stdscr.addstr(3, ncols + 2,  'Across', curses.A_BOLD)
            stdscr.addstr(3, ncols + 36, 'Down',   curses.A_BOLD)
            stdscr.refresh()
            # As a bit of an ugly hack to get around the curses quirk of not
            # allowing writing at the bottom right corner, add an extra line
            # at the bottom of windows that can be filled to the brim
            self.main_grid   = curses.newwin(nrows + 1, ncols, 3, 0)
            self.status_line = curses.newwin(1, ncols, nrows + 4, 0)
            self.clue_grids  = {'across': curses.newwin(nrows, 33, 4, ncols + 2),
                                'down':   curses.newwin(nrows, 33, 4, ncols + 36)}
            while True:
                self.render_main_grid()
                self.render_clue_grids()
                self.handle(stdscr.getkey())

        curses.wrapper(main)

    def render_main_grid(self):
        self.main_grid.erase()

        span       = self.clue.span
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
                boldness = boldnesses.get((x, y), 'normal')
                vertex   = VERTICES[shape][boldness]
                row.append(vertex)
            vertices.append(row)

        for y in range(self.height):
            for x in range(self.width):
                vertex = vertices[y][x]
                self.main_grid.addstr(vertex)

                square    = self.get(x, y)
                number    = square.number
                attribute = curses.A_BOLD if number == self.clue.number else curses.A_NORMAL
                number    = '' if number is None else str(number)
                self.main_grid.addstr(number, attribute)

                bold = boldnesses.get((x, y)) in ('topleft', 'bottomleft', 'horizontal')
                edge = EDGES['horizontal'][bold] * (3 - len(number))
                self.main_grid.addstr(edge)

            self.main_grid.addstr(vertices[y][x + 1])

            for x in range(self.width):
                bold = boldnesses.get((x, y)) in ('topleft', 'topright', 'vertical')
                edge = EDGES['vertical'][bold]
                self.main_grid.addstr(edge)

                square = self.get(x, y)
                if square.black:
                    self.main_grid.addstr(SHADE * 3)
                else:
                    cursor = '>' if (x, y) == (self.x, self.y) else ' '
                    self.main_grid.addstr(cursor, curses.A_BOLD)

                    letter = ' ' if square.empty else square.buffer
                    status = square.status
                    self.main_grid.addstr(letter + status)

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

            active_clue = self.square.clues[direction]

            for index, clue in enumerate(self.clues[direction]):
                active    = clue is active_clue
                render    = clue.render(active)
                attribute = curses.A_BOLD if clue is self.clue else curses.A_NORMAL
                lines.extend((line, attribute) for line in render)
                heights.append(len(render))
                if active:
                    active_index = index

            if sum(heights[active_index:]) > nrows: # >= also works
                start   = sum(heights[:active_index])
                section = slice(start, start + nrows)
            else:
                section = slice(-nrows, None)

            for line, attribute in lines[section]:
                clue_grid.addstr(line + '\n', attribute)

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
                elif key in 'fF':
                    forward = key == 'f'
                    letter = self.main_grid.getkey().upper()
                    # Remember letter and direction for ; and ,
                    self.find_letter  = letter
                    self.find_forward = forward
                    self.find(lambda square: square.buffer == letter,
                              forward, skip_repeats=False)
                    # There's no real need for t and T,
                    # because it's all just English letters.
                elif key in ';,':
                    if self.find_letter is not None:
                        forward = self.find_forward
                        if key == ',':
                            forward = not forward
                        self.find(lambda square: square.buffer == self.find_letter,
                                  forward, skip_repeats=False)
                elif key in '}{':
                    forward = key == '}'
                    self.find(lambda square: square.empty, forward)
                elif key in '][':
                    forward  = key == ']'
                    next_key = self.main_grid.getkey()
                    status   = {'q': PENCIL, 'w': CROSS}.get(next_key)
                    if status is not None:
                        self.find(lambda square: square.status == status, forward)
                elif key == 'r':
                    self.replace()
                elif key == 'x':
                    self.delete()
                elif key == ' ':
                    self.toggle()
                elif key == 'i':
                    self.insert()
                elif key == 'a':
                    self.advance()
                    self.insert()
                elif key == '~':
                    self.toggle_pencil()
                elif key == ':':
                    self.type_command()
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
    def square(self):
        return self.get(self.x, self.y)

    @property
    def next_square(self):
        return self.square.next[self.direction]

    @property
    def prev_square(self):
        return self.square.prev[self.direction]

    @property
    def next_squares(self):
        square = self.next_square
        while square is not None:
            yield square
            square = square.next[self.direction]

    @property
    def prev_squares(self):
        square = self.prev_square
        while square is not None:
            yield square
            square = square.prev[self.direction]

    @property
    def clue(self):
        return self.square.clues[self.direction]

    @property
    def next_clue(self):
        return self.clue.next

    @property
    def prev_clue(self):
        return self.clue.prev

    @property
    def other_direction(self):
        return 'down' if self.direction == 'across' else 'across'

    def in_range(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x, y):
        if not self.in_range(x, y):
            return None
        return self.grid[y][x]

    def move(self, dx, dy):
        x, y = self.square
        x += dx
        y += dy
        while True:
            next_square = self.get(x, y)
            if next_square is None:
                break
            if next_square.black:
                x += dx
                y += dy
            else:
                self.jump(next_square)
                break

    def jump(self, square):
        self.x, self.y = square

    def start(self):
        self.jump(self.clue.span[0])

    def end(self):
        self.jump(self.clue.span[-1])

    def next(self):
        if self.next_clue is not None:
            self.jump(self.next_clue.span[0])
        else:
            self.jump(self.clues[self.other_direction][0].span[0])
            self.toggle()

    def prev(self):
        if self.prev_clue is not None:
            self.jump(self.prev_clue.span[0])
        else:
            self.jump(self.clues[self.other_direction][-1].span[0])
            self.toggle()

    def find(self, condition, forward=True, skip_repeats=True):
        squares = self.next_squares if forward else self.prev_squares
        try:
            if skip_repeats:
                # Using ]w [w (jump to next wrong square) as an example:
                #  xxx   xxx
                #  ^^^^^^#
                # When at ^, jump to #. But compare these two scenarios:
                #  xxx   xxx
                #  ^     #
                #   xx   xxx
                #  ^#
                # The next squares are identical ("xx   xxx"), but the
                # square you jump to is different. So you also need to
                # consider the current square ("xxx..." vs " xx...").
                # Then you can simply skip all squares that meet the
                # condition ("x"s), then all squares that don't (" "s);
                # after two rounds of skipping, the next square in line
                # is the square you want to jump to.
                squares = chain([self.square], squares)
                squares = dropwhile(condition, squares)
            self.jump(next(filter(condition, squares)))
        except StopIteration:
            pass

    def advance(self):
        if self.next_square is not None:
            self.jump(self.next_square)
        else:
            self.next()
            # self.next() already jumps to the start,
            # so there's no need to write self.start() here
            # (compare with retreat() below)

    def retreat(self):
        if self.prev_square is not None:
            self.jump(self.prev_square)
        else:
            self.prev()
            self.end()

    def replace(self):
        key = self.main_grid.getkey()
        self.type(key)

    def type(self, key):
        if key in LOWERCASE:
            self.square.set(key.upper())
        elif key in UPPERCASE:
            self.square.set(key, pencil=True)

    def delete(self):
        self.square.unset()

    def toggle(self):
        self.direction = self.other_direction

    def insert(self):
        self.mode = 'insert'
        self.show_message('-- INSERT --')

    def escape(self):
        self.mode = 'normal'
        self.show_message('')

    def backspace(self):
        self.retreat()
        self.delete()

    def reveal(self):
        self.square.reveal()
        self.advance()

    def toggle_pencil(self):
        if not self.square.empty:
            self.square.toggle_pencil()
        self.advance()

    def type_command(self):
        curses.echo()      # show characters typed
        curses.curs_set(1) # show cursor

        self.status_line.erase()
        self.status_line.addstr(':')
        command = self.status_line.getstr(0, 1)
        self.execute_command(command)

        curses.noecho()
        curses.curs_set(0)

    def execute_command(self, command):
        command = command.strip().decode()

        if command in ('q', 'quit'):
            self.quit()
        elif command in ('c', 'check'):
            self.check()
        elif command in ('c!', 'check!'):
            self.check(bang=True)
        elif command: # not entirely whitespace
            self.show_message(f'Unknown command "{command}"')

    def show_message(self, message):
        self.status_line.erase()
        self.status_line.addstr(message)
        self.status_line.refresh()

    def check(self, bang=False):
        #                      wrong
        #              ┌──────┬──────┬──────┐
        #              │ none │ some │ all  │
        #       ┌──────┼──────┼──────┴──────┤
        #       │ none │ done │             │
        #       ├──────┼──────┤    amiss    │
        # empty │ some │ fine │             │
        #       ├──────┼──────┴─────────────┤
        #       │  all │  nothing to check  │
        #       └──────┴────────────────────┘

        empty = []
        wrong = []

        for row in self.grid:
            for square in row:
                if square.black:
                    continue
                empty.append(square.empty)
                wrong.append(square.wrong)
                if bang:
                    square.mark()

        if all(empty):
            self.show_message("There's nothing to check.")
        elif any(wrong):
            if bang:
                nwrong = sum(wrong)
                suffix = 's' if nwrong > 1 else ''
                self.show_message(f"Found {nwrong} wrong square{suffix}.")
                self.erase()
            else:
                self.show_message("At least one square's amiss.")
        elif any(empty):
            self.show_message("You're doing fine.")
            self.erase()
        else:
            self.show_message("Congrats! You've finished the puzzle.")
            self.erase()

    def erase(self):
        for row in self.grid:
            for square in row:
                square.erase()

    def quit(self):
        sys.exit()

class Clue:
    def __init__(self, number, text, span):
        self.number = number
        self.text   = text
        self.span   = span
        self.prev   = None
        self.next   = None

    def render(self, active):
        lines    = WRAPPER.wrap(self.text)
        cursor   = '>' if active else ' '
        lines[0] = f'{cursor}{self.number:>2} ' + lines[0][4:]
        return lines

class Square:
    def __init__(self, x, y, answer, buffer):
        self.x      = x
        self.y      = y
        self.answer = answer
        self.buffer = buffer
        self.status = NORMAL
        self.number = None
        self.clues  = {direction: None for direction in DIRECTIONS}
        self.prev   = {direction: None for direction in DIRECTIONS}
        self.next   = {direction: None for direction in DIRECTIONS}

    def __iter__(self):
        yield self.x
        yield self.y

    @property
    def black(self):
        return self.answer == BLACK

    @property
    def empty(self):
        return self.buffer == EMPTY

    @property
    def wrong(self):
        return not self.empty and self.buffer != self.answer

    def set(self, letter, pencil=False):
        self.buffer = letter
        # When setting a square to a new letter (even when the new letter
        # is the same as the old one), overwrite any pencil or cross status,
        # unless you're pencilling in, in which case set the status to pencil
        self.status = PENCIL if pencil else NORMAL

    def unset(self):
        self.set(EMPTY)

    def toggle_pencil(self):
        # normal -> pencil (of course)
        # pencil -> normal (of course)
        # cross  -> pencil (non-obvious but feels right to the user)
        self.status = NORMAL if self.status == PENCIL else PENCIL

    def erase(self):
        if self.status == PENCIL:
            self.status = NORMAL

    def mark(self):
        if self.wrong:
            self.status = CROSS

    def reveal(self):
        self.set(self.answer)

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip checksums, file magic, etc. for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answer, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                          for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        title     = strings[0]
        author    = strings[1]
        copyright = strings[2]
        cluelist  = strings[3:3+nclues]
        notes     = strings[3+nclues:]
        assert len(cluelist) == nclues, f'Expected {nclues} clues, got {len(cluelist)}'
        return Puzzle(answer, buffer, cluelist, title, author, copyright, notes)

if __name__ == '__main__':
    puzzle = parse(sys.argv[1])
    puzzle.run()
