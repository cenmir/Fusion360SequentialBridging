# Author - Mirza Cenanovic
# The sketch constraints are adapted from a contribution by Arsenii Tymoshenko,
# the layer height parameter from one by Barney15e.
#
# Geometry only, no user interface. Anything this module cannot handle comes
# back as UnsupportedGeometry so the caller decides how to tell the user.

import adsk.core, adsk.fusion

# Fusion works in centimeters internally, so this is 10 nm.
tolerance = 1e-6

# Every cut is driven by this user parameter rather than a fixed distance, so
# changing the layer height later updates every bridge in the design.
parameterName = "seq_bridge_height"
parameterUnit = "mm"
parameterDefault = "0.2 mm"
parameterComment = "The FFF printer layer height"

# The first bridge is one layer deep and the second is two
extrusionAmount = ("-2*" + parameterName, "-" + parameterName)

class UnsupportedGeometry(Exception):
    """A face this script cannot bridge, with a reason fit to show the user."""

def ParameterExpression(design):
    # Reading without creating, so opening the dialog and cancelling leaves
    # no parameter behind
    parameter = design.userParameters.itemByName(parameterName)
    if parameter:
        return parameter.expression
    return parameterDefault

def SetParameter(design, expression):
    parameter = design.userParameters.itemByName(parameterName)
    if parameter:
        parameter.expression = expression
        return parameter
    value = adsk.core.ValueInput.createByString(expression)
    return design.userParameters.add(parameterName, value, parameterUnit, parameterComment)

def ReadFace(sketch):
    """Work out the hole radius r and the outer extent R of the selected face."""
    curves = sketch.sketchCurves
    circles = curves.sketchCircles
    lines = curves.sketchLines

    if curves.count == 2:
        #Hole geometry
        if circles.count != 2:
            raise UnsupportedGeometry("a face with two curves that are not both circles")
        # Determine the inner and outer circles
        if circles[0].radius > circles[1].radius:
            outer = circles[0]
            inner = circles[1]
        else:
            outer = circles[1]
            inner = circles[0]

        # Everything below is laid out around one center point, so anything
        # eccentric would put the bridges in the wrong place
        if outer.centerSketchPoint.geometry.distanceTo(inner.centerSketchPoint.geometry) > tolerance:
            raise UnsupportedGeometry("a hole whose circles are not concentric")

        return (inner, inner.radius, outer.radius)

    if curves.count == 7:
        #Hex geometry
        if circles.count != 1 or lines.count != 6:
            raise UnsupportedGeometry("a face with seven curves that is not a hexagon around a circle")
        # A regular hexagon has a circumradius equal to its side length
        return (circles[0], circles[0].radius, lines[0].length)

    raise UnsupportedGeometry("a face that is neither two concentric circles nor a hexagon around a circle")

def DrawBridgeLines(sketch, circle, r, R):
    """Draw the four lines tangent to the hole, running past the outer edge.

    No trimming is needed thanks to Fusion360 automatic sketch profiling.
    """
    center = circle.centerSketchPoint.geometry
    xc = center.x
    yc = center.y
    zc = center.z

    lines = sketch.sketchCurves.sketchLines
    lineW = lines.addByTwoPoints(
        adsk.core.Point3D.create(xc-r, yc+R, zc),
        adsk.core.Point3D.create(xc-r, yc-R, zc))
    lineE = lines.addByTwoPoints(
        adsk.core.Point3D.create(xc+r, yc+R, zc),
        adsk.core.Point3D.create(xc+r, yc-R, zc))
    lineN = lines.addByTwoPoints(
        adsk.core.Point3D.create(xc-R, yc+r, zc),
        adsk.core.Point3D.create(xc+R, yc+r, zc))
    lineS = lines.addByTwoPoints(
        adsk.core.Point3D.create(xc-R, yc-r, zc),
        adsk.core.Point3D.create(xc+R, yc-r, zc))

    return (lineW, lineE, lineN, lineS)

def ConstrainSketch(sketch, circle, bridgeLines, R):
    """Fully constrain the sketch so later edits cannot drag the bridges out of place.

    Adapted from Arsenii Tymoshenko's contribution. The square is construction
    geometry: as real lines it would close off profiles between the outer edge
    and the square, and the ones due north and south of the hole pass the
    profile test below and would cut stray slots into the face.
    """
    lineW, lineE, lineN, lineS = bridgeLines
    lines = sketch.sketchCurves.sketchLines
    constraints = sketch.geometricConstraints

    center = circle.centerSketchPoint
    xc = center.geometry.x
    yc = center.geometry.y
    zc = center.geometry.z

    # A square around the whole construction gives the four bridge lines
    # something to end on
    corners = (
        adsk.core.Point3D.create(xc-R, yc-R, zc),
        adsk.core.Point3D.create(xc+R, yc-R, zc),
        adsk.core.Point3D.create(xc+R, yc+R, zc),
        adsk.core.Point3D.create(xc-R, yc+R, zc))
    bottom = lines.addByTwoPoints(corners[0], corners[1])
    right = lines.addByTwoPoints(corners[1], corners[2])
    top = lines.addByTwoPoints(corners[2], corners[3])
    left = lines.addByTwoPoints(corners[3], corners[0])
    square = (bottom, right, top, left)
    for line in square:
        line.isConstruction = True

    constraints.addCoincident(bottom.endSketchPoint, right.startSketchPoint)
    constraints.addCoincident(right.endSketchPoint, top.startSketchPoint)
    constraints.addCoincident(top.endSketchPoint, left.startSketchPoint)
    constraints.addCoincident(left.endSketchPoint, bottom.startSketchPoint)

    constraints.addHorizontal(bottom)
    constraints.addHorizontal(top)
    constraints.addVertical(right)
    constraints.addVertical(left)
    constraints.addEqual(bottom, right)

    # A diagonal pins the square to the hole center
    diagonal = lines.addByTwoPoints(bottom.startSketchPoint, right.endSketchPoint)
    diagonal.isConstruction = True
    midPoint = sketch.sketchPoints.add(adsk.core.Point3D.create(xc, yc, zc))
    constraints.addMidPoint(midPoint, diagonal)
    constraints.addCoincident(midPoint, center)

    # One dimension drives the size of the whole thing
    sketch.sketchDimensions.addDistanceDimension(
        bottom.startSketchPoint,
        bottom.endSketchPoint,
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
        adsk.core.Point3D.create(xc, yc+R+1, zc))

    constraints.addHorizontal(lineN)
    constraints.addHorizontal(lineS)
    constraints.addVertical(lineE)
    constraints.addVertical(lineW)

    for line in bridgeLines:
        constraints.addTangent(line, circle)

    # Each bridge line ends on the square. The pairing follows the order the
    # points were created in, so the solver never has to flip a line.
    constraints.addCoincident(lineN.startSketchPoint, left)
    constraints.addCoincident(lineN.endSketchPoint, right)
    constraints.addCoincident(lineS.startSketchPoint, left)
    constraints.addCoincident(lineS.endSketchPoint, right)
    constraints.addCoincident(lineE.startSketchPoint, top)
    constraints.addCoincident(lineE.endSketchPoint, bottom)
    constraints.addCoincident(lineW.startSketchPoint, top)
    constraints.addCoincident(lineW.endSketchPoint, bottom)

def SortProfiles(sketch, circle, r):
    """Split the profiles into the ones cut one layer deep and two layers deep."""
    center = circle.centerSketchPoint.geometry
    xc = center.x
    yc = center.y

    profiles = sketch.profiles
    innerProfiles = adsk.core.ObjectCollection.create()
    outerProfiles = adsk.core.ObjectCollection.create()

    for i in range(profiles.count):
        profile_i = profiles.item(i)
        bcx = abs( (profile_i.boundingBox.maxPoint.x + profile_i.boundingBox.minPoint.x)/2 - xc)
        bcy = abs( (profile_i.boundingBox.maxPoint.y + profile_i.boundingBox.minPoint.y)/2 - yc)
        # The hole itself sits on the center, there is nothing to cut there
        if bcx < tolerance and bcy < tolerance:
            continue
        # bcx and bcy are distances, so only the upper bound is a real test
        if bcx < r:
            if bcy < r:
                innerProfiles.add(profile_i)
                outerProfiles.add(profile_i)
            else:
                outerProfiles.add(profile_i)

    # The corner profiles only exist because Fusion splits the hole circle
    # where the bridge lines touch it. If that ever fails the collections come
    # out empty, and an empty collection makes the extrude throw.
    if innerProfiles.count == 0 or outerProfiles.count == 0:
        raise UnsupportedGeometry("a face whose bridge profiles could not be worked out")

    return (outerProfiles, innerProfiles)

def ExtrudeProfiles(comp, outerProfiles, innerProfiles):
    extrudes = comp.features.extrudeFeatures
    fullDistance = adsk.core.ValueInput.createByString(extrusionAmount[0])
    halfDistance = adsk.core.ValueInput.createByString(extrusionAmount[1])
    extent_distance_half = adsk.fusion.DistanceExtentDefinition.create(halfDistance)
    extent_distance_full = adsk.fusion.DistanceExtentDefinition.create(fullDistance)

    extrudeInput = extrudes.createInput(outerProfiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
    extrudeInput.setOneSideExtent(extent_distance_half, adsk.fusion.ExtentDirections.PositiveExtentDirection)
    extrude1 = extrudes.add(extrudeInput)

    extrudeInput = extrudes.createInput(innerProfiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
    extrudeInput.setOneSideExtent(extent_distance_full, adsk.fusion.ExtentDirections.PositiveExtentDirection)
    extrude2 = extrudes.add(extrudeInput)

    return (extrude1, extrude2)

def CreateSequentialBridging(face):
    """Cut the sequential bridging steps into one selected face."""
    # A face picked inside a component comes back as a proxy. Working on the
    # native face keeps the sketch and the extrusions in the component that
    # owns the geometry instead of dumping them in the root.
    if face.assemblyContext:
        face = face.nativeObject
    comp = face.body.parentComponent

    #Create a sketch on the face
    sketch = comp.sketches.add(face)

    try:
        circle, r, R = ReadFace(sketch)
        bridgeLines = DrawBridgeLines(sketch, circle, r, R)
        ConstrainSketch(sketch, circle, bridgeLines, R)
        outerProfiles, innerProfiles = SortProfiles(sketch, circle, r)
    except UnsupportedGeometry:
        # Nothing usable came of it, so do not leave the sketch behind
        sketch.deleteMe()
        raise

    #Create extrusion
    ExtrudeProfiles(comp, outerProfiles, innerProfiles)
