import time

from PIL import ImageFont


class Button:

    button_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
    )

    def __init__(self, x, y, width, height, text, font, text_colour, back_colour, up_handler, down_handler, visible=True):
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
        self.visible = visible
        self.pressed = False
        self.enabled = False
        self.touch_down_pending = False
        self.touch_up_pending = False

    def draw(self, draw):

        # visible=False buttons still hit-test/dispatch normally - used for tap targets (e.g.
        # thumbnail cells) whose visuals are drawn separately, onto the base image, by the caller.
        if not self.enabled or not self.visible:
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

        # Gated on pressed, not enabled: a down_handler commonly switches to a new
        # button panel (disabling this button) before the matching physical release
        # arrives, often within the same update() tick. The button still owes this
        # release to whoever pressed it, so completion must survive being disabled
        # mid-press - only a button that was never actually pressed should no-op here.
        if not self.pressed:
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
        self.touch_up_pending = True

    def set_down(self):

        if not self.enabled:
            return

        self.touch_down_pending = True

    def update(self):
        # Clear each pending flag *before* invoking the handler, not after: handlers here
        # (e.g. print_image, start/finish_voice_prompt) can call screen.update() themselves
        # while they run (to stay responsive during a blocking action), which re-enters this
        # method - if the flag were still set at that point, the handler would be invoked again
        # from within itself, recursing until Python's stack limit is hit.
        dirty = False

        if self.touch_down_pending:
            self.touch_down_pending = False
            dirty = True
            self.do_down()

        if self.touch_up_pending:
            self.touch_up_pending = False
            dirty = True
            self.do_up()

        return dirty


class ButtonPanel:
    """Holds the active set of buttons and dispatches press/release coordinates to them.

    Input handlers (touch interrupts, mouse events) may run on another thread, so press()/
    release() only set pending flags on the buttons; update() applies them on the main thread
    and reports whether anything changed, so the caller knows whether to redraw.
    """

    # Menus reuse screen real estate - a button in the new menu can sit at the exact
    # coordinates a button in the old one occupied. Real touchscreens can report a stray
    # extra press/release right on the heels of the tap that caused the swap (electrical
    # bounce, or a finger not quite lifted yet); without this guard that stray event lands
    # on whatever's now underneath instead of being harmlessly dropped.
    SWITCH_GUARD_SECONDS = 0.3

    def __init__(self):
        self.buttons = []
        self._switched_at = 0.0
        # Buttons currently down, oldest first - a list rather than a single slot because a
        # second press can land before the first one's release does (a bounced/duplicate touch,
        # or the user retapping because a sluggish redraw hasn't visibly responded yet). Each
        # release() call resolves the oldest outstanding one, so a new press never silently
        # discards a still-pending one - that used to leave the discarded button's `pressed`
        # state stuck, and since menus reuse the same Button objects across switches (see
        # set_buttons()), it could resurface later as a mismatched, delayed release for the
        # wrong button.
        self._pressed_buttons = []

    def set_buttons(self, buttons):
        for button in self.buttons:
            button.disable()
        self.buttons = buttons
        for button in self.buttons:
            button.enable()
        self._switched_at = time.monotonic()
        # self._pressed_buttons is deliberately left alone here: buttons in this app act on
        # press (down_handler), so the handler that just ran often *is* what called
        # set_buttons(), swapping this button out of self.buttons before its own physical
        # release has arrived. It still owes that button its release.

    def draw(self, draw):
        for button in self.buttons:
            button.draw(draw)

    def press(self, x, y):
        if time.monotonic() - self._switched_at < self.SWITCH_GUARD_SECONDS:
            return
        for button in self.buttons:
            if button.check_coord(x, y):
                button.set_down()
                self._pressed_buttons.append(button)
                return

    def release(self, x, y):
        # A finger pressing a button can drift outside its bounds before lifting, and/or
        # the button's own down_handler may have already swapped in a new panel - either
        # way the release belongs to whichever button is tracked as pressed, not whatever
        # is now under the release coordinate. This must bypass the switch guard below:
        # that guard exists for stray/untracked touches landing on the new panel, not for
        # the very button whose press caused the switch. Resolves the oldest outstanding
        # press first, matching physical touches in the order they went down.
        if self._pressed_buttons:
            self._pressed_buttons.pop(0).set_up()
            return
        if time.monotonic() - self._switched_at < self.SWITCH_GUARD_SECONDS:
            return
        for button in self.buttons:
            if button.check_coord(x, y):
                button.set_up()

    def update(self):
        dirty = False
        seen = set()
        for button in self.buttons:
            seen.add(id(button))
            if button.update():
                dirty = True

        # A pressed button may have been dropped from self.buttons by a panel switch
        # before its release was drained above (see set_buttons()) - give each one still
        # outstanding a chance too, so the touch_up_pending set by release() doesn't sit
        # forever unprocessed.
        for button in list(self._pressed_buttons):
            if id(button) not in seen:
                if button.update():
                    dirty = True
            if not button.pressed and not button.touch_down_pending and not button.touch_up_pending:
                self._pressed_buttons.remove(button)

        return dirty
