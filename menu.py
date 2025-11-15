import nuke


menu = nuke.menu('Nuke')
ar_menu = menu.addMenu('AR')

# Add menu items to the "AR" menu
ar_menu.addCommand('StaX', 'gui_main.main()', 'Ctrl+Alt+S')