from PIL import Image, ImageDraw, ImageFont

class Button:

    button_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
    )
    
    def __init__(self, x, y, width,height,text,font,text_colour,back_colour,up_handler,down_handler):
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
        
        draw.text((text_x, text_y), self.text, font=self.font, fill=text_colour,anchor="mm")
        
    def enable(self):
        self.enabled = True
        
    def disable(self):
        self.enabled = False
        
    def check_coord(self,x,y):
        
        if not self.enabled:
            return False
        
        if x<self.x: return False
        if y<self.y: return False
        if x>(self.x+self.width): return False
        if y>(self.y+self.height): return False
        
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
        
        self.touch_up_pending=True
        
    def set_down(self):
        
        if not self.enabled:
            return
        
        self.touch_down_pending=True
            
    def update(self):
        dirty = False
        
        if self.touch_down_pending:
            dirty=True
            self.do_down()
            self.touch_down_pending=False
        
        if self.touch_up_pending:
            dirty=True
            self.do_up()
            self.touch_up_pending=False
            
        return dirty

class Menu:
    
    min_touch_x=281
    max_touch_x=3859
    min_touch_y=3724
    max_touch_y=243
    
    def touch_handler(self,touch_down,raw_x,raw_y):
        if touch_down:
            print("Touch down")
            
            x_range = self.max_touch_x - self.min_touch_x
            x = int(((raw_x - self.min_touch_x)/x_range)*480)
            self.last_x = x
            
            y_range = self.min_touch_y - self.max_touch_y
            raw_y = raw_y - self.max_touch_y
            raw_y = y_range - raw_y
            y = int((raw_y/y_range)*320)
            self.last_y = y
        else:        
            print("Touch up")
            # Use the down coordinates if the button is released
            x = self.last_x
            y = self.last_y
    
        print(f"Button callback x:{x} y:{y}")

        for button in self.buttons:
            if button.check_coord(x,y):
                if touch_down:
                    button.set_down()
                else:
                    button.set_up()

    def __init__(self):
        
        self.buttons = []
        
        x_range=self.max_touch_x-self.min_touch_x
        self.x_factor = x_range/480
        
        y_range=self.max_touch_y-self.min_touch_y
        self.y_factor = y_range/320
        
        self.last_x = None
        self.last_y = None

    def draw(self,draw):
        for button in self.buttons:
            button.draw(draw)
            
    def set_buttons(self,buttons):
        for button in self.buttons:
            button.disable()
        self.buttons = buttons
        for button in self.buttons:
            button.enable()
            
    def update(self):
        dirty = False
        for button in self.buttons:
            if button.update():
                dirty=True
        return dirty
        

