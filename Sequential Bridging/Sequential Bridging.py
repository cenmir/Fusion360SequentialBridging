# Author - Mirza Cenanovic
# Description - Create support geometry for overhanging holes when 3D printing.
# Also known as sequential bridging
#
# Entry point only. The work is in the sequential_bridging package.

import importlib
import traceback
import adsk.core

from .sequential_bridging import geometry
from .sequential_bridging import command

# Fusion keeps imported modules loaded for the whole session, so edits to the
# package would not show up when the add-in is stopped and started again.
# Reloading on start keeps the development loop tight and costs nothing.
reloadOnStart = True

def run(context):
    try:
        if reloadOnStart:
            importlib.reload(geometry)
            importlib.reload(command)
        command.AddButton()
    except:
        adsk.core.Application.get().userInterface.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def stop(context):
    try:
        command.RemoveButton()
    except:
        adsk.core.Application.get().userInterface.messageBox('Failed:\n{}'.format(traceback.format_exc()))
