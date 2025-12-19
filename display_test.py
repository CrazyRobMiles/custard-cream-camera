from ili9486_display import ILI9486Display

disp = ILI9486Display()
#disp.crazy_test()
disp.test_pattern()
# for v in (0x28, 0x68, 0xA8, 0xE8):
#     print(hex(v))
#     disp.set_madctl(v)
#     disp.clear_portrait(0x0002)  # clear to black    
#     disp.test_pattern()
#     input("Press Enter for next...")
