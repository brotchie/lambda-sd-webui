import curses
import urwid


class Screen:
    def __init__(self, stdscr):
        self.stdscr = stdscr

    def tick(self):
        self.stdscr.clear()
        rows, cols = self.stdscr.getmaxyx()
        x = (cols - len("Hello World!")) // 2
        y = rows // 2
        self.stdscr.addstr(y, x, "Hello World!")
        self.stdscr.addstr(0, 0, str(curses.LINES))
        self.stdscr.refresh()


def main(stdscr):
    # Clear screen
    screen = Screen(stdscr)
    while True:
        
        #window = curses.newwin(10, curses.COLS, 0, 0)
        #window.clear()
        #window.addstr(0, 0, "Hello World!")

        #stdscr.refresh()
        #window.refresh()
        screen.tick()
        code = stdscr.getch()
        #if code == curses.KEY_RESIZE:
            #curses.endwin()
            #stdscr = curses.initscr()
            #stdscr.refresh()
            #stdscr.clear()
            #screen = Screen(stdscr)


if __name__ == "__main__":
    #curses.wrapper(main)
    def exit_on_q(key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    palette = [
        ('banner', 'black', 'light gray'),
        ('streak', 'black', 'dark red'),
        ('bg', 'black', 'dark blue'),]

    txt = urwid.Text(('banner', u" Hello World "), align='center')
    map1 = urwid.AttrMap(txt, 'streak')
    fill = urwid.Filler(map1)
    map2 = urwid.AttrMap(fill, 'bg')
    loop = urwid.MainLoop(map2, palette, unhandled_input=exit_on_q)
    loop.run()