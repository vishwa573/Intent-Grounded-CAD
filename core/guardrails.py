# core/guardrails.py

SYNTAX_LOOKUP = {
    "name 'BuildPart' is not defined": "You forgot to import the library! Every script MUST start with: from build123d import *",
    "name 'shell' is not defined": "Do not use shell() or offset() to hollow parts, as face selection often fails. Use Boolean Subtraction instead: subtract a slightly smaller inner solid from your main solid using the minus operator (-).",
    "list index out of range": "You tried to access a face in an empty list. Avoid complex face selection like `.faces().sort_by()[-1]`. If you are trying to make a hollow object, use basic Boolean Subtraction instead (outer_shape - inner_shape).",
    "unexpected keyword argument 'diameter'": "In build123d, Cylinder and Circle use 'radius', not 'diameter'. Divide the requested diameter by 2.",
    "unexpected keyword argument 'd'": "In build123d, primitives use 'radius', not 'd' or 'diameter'.",
    "list indices must be integers": "Check your list slicing. You likely passed a tuple or float instead of an integer index.",
    "unexpected keyword argument 'align'": "In newer build123d versions, use 'align=(Align.CENTER, Align.CENTER, Align.CENTER)' instead of string alignments.",
    "object has no attribute 'faces'": "You are trying to call .faces() on a sketch or 2D object. You must extrude it into a 3D solid first.",
    "name 'cut' is not defined": "In build123d, do not use cut(). To hollow an object, subtract one object from another using the minus operator (part1 - part2).",
    "BuildPart doesn't have a Circle object": "Circle() is a 2D object for BuildSketch. To make a 3D cylinder in BuildPart, use Cylinder(radius=..., height=...).",
    "BuildPart doesn't have a Rectangle object": "Rectangle() is for 2D BuildSketch. For 3D BuildPart, use Box(length, width, height) or extrude a sketch.",
    "unexpected keyword argument 'radius_top'": "For Cone(), you MUST use 'top_radius' and 'bottom_radius'. Do not use 'radius', 'radius_top', or 'r'.",
    "unexpected keyword argument 'radius'": "For Cone(), you MUST use 'top_radius' and 'bottom_radius'. Do not use 'radius'. For Cylinder, use 'radius'.",
    "name 'Gear' is not defined": "There is no built-in 'Gear' primitive in build123d. If asked for a gear or complex shape, just use a basic 'Cylinder' with the requested dimensions as a placeholder.",
    "name 'Disk' is not defined": "There is no 'Disk' primitive. To make a disk, simply use 'Cylinder(radius=..., height=...)' with a very small height.",
    "name 'Extrude' is not defined": "The function is lowercase 'extrude()', not 'Extrude()'. However, it is strongly preferred to stack 3D primitives like Box() and Cylinder() instead of sketching and extruding.",
    "name 'Translate' is not defined": "Do not use Translate() or translate(). You MUST position parts using the context manager: 'with Locations((X, Y, Z)):'",
    "No module named 'solid'": "Do not use the 'solid' library or OpenSCAD syntax. You MUST use 'build123d' exclusively for all geometry generation.",
    "missing 1 required positional argument: 'height'": "You are missing the 'height' parameter. Primitives like Box, Cylinder, and Cone MUST specify height/length dimensions explicitly.",
    "has no attribute 'export_stl'": "Do NOT call export_stl() as an object method. Use the global function and pass the solid: export_stl(final_part, 'generated_files/generated_part.stl').",
    "has no attribute 'export_step'": "Do NOT call export_step() as an object method. Use the global function: export_step(final_part, 'generated_files/generated_part.step').",
    "has no attribute 'export'": "Do NOT call export() as an object method. Use the global functions: export_stl(final_part, 'generated_files/generated_part.stl') and export_step(final_part, 'generated_files/generated_part.step').",
    "name 'translate' is not defined": "In build123d, do not use 'translate()'. To move objects, use 'Pos(X, Y, Z)' or 'with Locations((X, Y, Z)):'.",
    "name 'show_all' is not defined": "Do not use visualizers like show() or show_all(). Just assign the geometry to 'final_part'.",
    "name 'show' is not defined": "Do not use visualizers like show() or show_object(). Just assign the geometry to 'final_part'.",
    "name 'show_object' is not defined": "Do not use visualizers like show() or show_object(). Just assign the geometry to 'final_part'.",
    "The variable 'final_part' (or 'part') was not assigned": "You must assign your final geometry to a variable exactly named 'final_part'. Do not name it 'final_shape' or anything else.",
    "Nothing to subtract from": "You must create your main positive solid FIRST before using mode=Mode.SUBTRACT. Reverse the order of your operations.",
    "unsupported operand type(s) for @: 'Plane' and 'tuple'": "Do not use the '@' operator to shift Planes. Use 'with Locations((X, Y, Z)):' to position your parts.",
    "'Location' object does not support the context manager protocol": "You typed 'with Location'. You MUST use the plural 'with Locations((X, Y, Z)):' to open the context manager.",
    "'Plane' object has no attribute 'at'": "Do not use '.at()' or '@' to shift Planes. Stick to stacking 3D primitives using 'with Locations((X, Y, Z)):'.",
    "(extrude doesn't apply to ['BuildPart'])": "You cannot call extrude() directly inside a BuildPart without a valid 2D context. Stick to stacking 3D primitives like Box() and Cylinder() using 'with Locations()'.",
    "BuildPart is a builder of Shapes and can't be combined": "You are trying to add or subtract the 'BuildPart' object itself! Build your ENTIRE assembly inside ONE SINGLE 'with BuildPart() as p:' block. Do not try to append to 'p'.",
    "unexpected keyword argument 'r'": "Do not use 'r=' for radius. You MUST type out the full word: 'radius='.",
    "got an unexpected keyword argument 'r'": "Do not use 'r=' for radius. You MUST type out the full word: 'radius='.",
    "No module named 'build_part'": "Do not use or import 'build_part'. The only correct import is: from build123d import *",
    "name 'build_part' is not defined": "Do not use or import 'build_part'. The only correct import is: from build123d import *",
    "No module named 'cadquery'": "Do NOT use cadquery. You are strictly a build123d engineer. Use build123d syntax exclusively.",
    "has no attribute 'position_at'": "Do not use '.position_at()'. Position objects using the context manager 'with Locations((X, Y, Z)):'.",
    "name 'Fillet' is not defined": "Do NOT attempt to add fillets or chamfers. Keep the geometry simple using basic, sharp-cornered primitives.",
    "name 'FilletEdges' is not defined": "Do NOT attempt to add fillets or chamfers. Keep the geometry simple using basic, sharp-cornered primitives.",
    "has no attribute 'add'": "BuildPart does not have an .add() method. Simply call the primitive (e.g., Box()) directly inside the 'with BuildPart():' context to add it to the assembly.",
    "BuildSketch doesn't have a Box object": "CRITICAL: You are trying to create a 3D Box inside a 2D BuildSketch. Move your Box() call outside of the BuildSketch and put it directly into the BuildPart context.",
}

def get_smart_feedback(raw_error):
    """
    Intercepts the raw traceback and injects the known API fix if a hallucination is detected.
    """
    for hallucination, fix in SYNTAX_LOOKUP.items():
        if hallucination in raw_error:
            return f"CRITICAL API FIX: {fix}\n\nOriginal Traceback: {raw_error}"
    
    # If no known hallucination is found, just return the raw error
    return raw_error
