# Author - Mirza Cenanovic
#
# The Sequential Bridging command: the dialog, the toolbar button and the glue
# between them and the geometry module.

import os, traceback
import adsk.core, adsk.fusion

from . import geometry

# A company name in the id keeps it unique against every other add-in loaded
# in the same session
commandId = "MirzaCenanovic_SequentialBridging"
commandName = "Sequential Bridging"
commandTooltip = ("Create support geometry for overhanging holes when 3D printing.\n\n"
    "Select the flat face around each hanging hole or nut pocket. Each one gets two "
    "bridging steps cut into it so the hole prints without supports.")

# Where the button goes. Change these two to move it somewhere else.
workspaceId = "FusionSolidEnvironment"
panelId = "SolidCreatePanel"

facesInputId = "faces"
heightInputId = "layerHeight"

iconFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Fusion releases handlers that nothing holds a reference to
handlers = []

def AddHandler(event, handlerType, callback):
    class Handler(handlerType):
        def notify(self, args):
            try:
                callback(args)
            except:
                ReportFailure()
    handler = Handler()
    event.add(handler)
    handlers.append(handler)

def ReportFailure():
    message = "Failed:\n{}".format(traceback.format_exc())
    app = adsk.core.Application.get()
    if app and app.userInterface:
        app.userInterface.messageBox(message)
    else:
        adsk.core.Application.log(message)

def AddButton():
    """Called when the add-in starts."""
    ui = adsk.core.Application.get().userInterface

    definition = ui.commandDefinitions.itemById(commandId)
    if definition:
        # Left over from a previous session or a reload
        definition.deleteMe()
    definition = ui.commandDefinitions.addButtonDefinition(commandId, commandName, commandTooltip, iconFolder)
    AddHandler(definition.commandCreated, adsk.core.CommandCreatedEventHandler, OnCommandCreated)

    panel = ui.workspaces.itemById(workspaceId).toolbarPanels.itemById(panelId)
    if not panel.controls.itemById(commandId):
        panel.controls.addCommand(definition)

def RemoveButton():
    """Called when the add-in stops."""
    ui = adsk.core.Application.get().userInterface

    panel = ui.workspaces.itemById(workspaceId).toolbarPanels.itemById(panelId)
    if panel:
        control = panel.controls.itemById(commandId)
        if control:
            control.deleteMe()

    definition = ui.commandDefinitions.itemById(commandId)
    if definition:
        definition.deleteMe()

    del handlers[:]

def SelectedFaces(ui):
    """Whatever planar faces the user had picked before opening the dialog."""
    faces = []
    for selection in ui.activeSelections:
        face = adsk.fusion.BRepFace.cast(selection.entity)
        if face and face.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            faces.append(face)
    return faces

def OnCommandCreated(args):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    command = args.command
    inputs = command.commandInputs

    selectionInput = inputs.addSelectionInput(facesInputId, "Faces", "Select the flat face around each hole")
    selectionInput.addSelectionFilter("PlanarFaces")
    selectionInput.setSelectionLimits(1, 0)

    expression = geometry.ParameterExpression(design) if design else geometry.parameterDefault
    heightInput = inputs.addValueInput(heightInputId, "Layer height", geometry.parameterUnit,
        adsk.core.ValueInput.createByString(expression))
    heightInput.tooltip = ("The height of one printed layer. The first bridge is cut one layer deep "
        "and the second two.\n\nThis drives the " + geometry.parameterName + " user parameter, so "
        "changing it here updates every bridge in the design.")

    # Fusion hands some commands their preselection already. Only fill in when
    # it has not, otherwise every face would be listed twice.
    if selectionInput.selectionCount == 0:
        for face in SelectedFaces(app.userInterface):
            selectionInput.addSelection(face)

    AddHandler(command.validateInputs, adsk.core.ValidateInputsEventHandler, OnValidateInputs)
    AddHandler(command.execute, adsk.core.CommandEventHandler, OnExecute)

def OnValidateInputs(args):
    inputs = args.inputs
    args.areInputsValid = (inputs.itemById(facesInputId).selectionCount > 0
        and inputs.itemById(heightInputId).value > 0)

def OnExecute(args):
    app = adsk.core.Application.get()
    ui = app.userInterface

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active design, switch to the Design workspace first.")
        return

    inputs = args.command.commandInputs
    selectionInput = inputs.itemById(facesInputId)
    faces = [selectionInput.selection(i).entity for i in range(selectionInput.selectionCount)]

    geometry.SetParameter(design, inputs.itemById(heightInputId).expression)

    # Three timeline entries per face adds up, so everything this run creates
    # goes into one group. Direct modeling has no timeline.
    isParametric = design.designType == adsk.fusion.DesignTypes.ParametricDesignType
    startIndex = design.timeline.markerPosition if isParametric else 0

    skipped = []
    for face in faces:
        try:
            geometry.CreateSequentialBridging(face)
        except geometry.UnsupportedGeometry as error:
            skipped.append(str(error))

    if isParametric:
        endIndex = design.timeline.markerPosition - 1
        # A group needs at least two entries, and a run where every face was
        # rejected creates none at all
        if endIndex > startIndex:
            design.timeline.timelineGroups.add(startIndex, endIndex)

    if skipped:
        reasons = "\n".join("- " + reason for reason in sorted(set(skipped)))
        ui.messageBox("Skipped {} of {} faces.\n\nSequential bridging needs a flat face around the "
            "hole, and this run was given:\n{}".format(len(skipped), len(faces), reasons))
