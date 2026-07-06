from PIL import ImageFont


class Button:

    button_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
    )

    def __init__(self, x, y, width, height, text, font, text_colour, back_colour, up_handler, down_handler):
        self.x = x
        self.y = y
        self.height = height
        self.width = width
        self.text = text
        self.font = font
        self.text_colour = text_colour
        self.back_colour = back_colour
        self.up_handler = up_handler
        self.down_handler = down_handler
        self.pressed = False
        self.enabled = False
        self.touch_down_pending = False
        self.touch_up_pending = False

    def draw(self, draw):

        if not self.enabled:
            return

        text_colour = self.back_colour if self.pressed else self.text_colour
        back_colour = self.text_colour if self.pressed else self.back_colour
        draw.rectangle((self.x, self.y, self.x+self.width, self.y+self.height), fill=back_colour)

        text_x = self.x + (self.width  // 2)
        text_y = self.y + (self.height // 2)

        draw.text((text_x, text_y), self.text, font=self.font, fill=text_colour, anchor="mm")

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def check_coord(self, x, y):

        if not self.enabled:
            return False

        if x < self.x: return False
        if y < self.y: return False
        if x > (self.x+self.width): return False
        if y > (self.y+self.height): return False

        return True

    def do_up(self):

        if not self.enabled:
            return

        self.pressed = False

        print(f"Button: {self.text} released")
        if self.up_handler:
            self.up_handler()

    def do_down(self):
        if not self.enabled:
            return

        self.pressed = True

        print(f"Button: {self.text} pressed")
        if self.down_handler:
            self.down_handler()

    def set_up(self):

        if not self.enabled:
            return

        self.touch_up_pending = True

    def set_down(self):

        if not self.enabled:
            return

        self.touch_down_pending = True

    def update(self):
        dirty = False

        if self.touch_down_pending:
            dirty = True
            self.do_down()
            self.touch_down_pending = False

        if self.touch_up_pending:
            dirty = True
            self.do_up()
            self.touch_up_pending = False

        return dirty


class ButtonPanel:
    """Holds the active set of buttons and dispatches press/release coordinates to them.

    Input handlers (touch interrupts, mouse events) may run on another thread, so press()/
    release() only set pending flags on the buttons; update() applies them on the main thread
    and reports whether anything changed, so the caller knows whether to redraw.
    """

    def __init__(self):
        self.buttons = []

    def set_buttons(self, buttons):
        for button in self.buttons:
            button.disable()
        self.buttons = buttons
        for button in self.buttons:
            button.enable()

    def draw(self, draw):
        for button in self.buttons:
            button.draw(draw)

    def press(self, x, y):
        for button in self.buttons:
            if button.check_coord(x, y):
                button.set_down()

    def release(self, x, y):
        for button in self.buttons:
            if button.check_coord(x, y):
                button.set_up()

    def update(self):
        dirty = False
        for button in self.buttons:
            if button.update():
                dirty = True
        return dirty
