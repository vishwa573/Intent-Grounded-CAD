from typing import Dict, Any, List

EXAMPLE_VAULT = {
    "sphere": '''from build123d import *
with BuildPart() as p:
    Sphere(radius=10, align=(Align.MIN, Align.MIN, Align.MIN))
    # Slice the bottom to ensure adhesion. Sphere's center footprint is (10,10,0)
    with Locations((10, 10, 0)):
        Box(20, 20, 1.5, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "cantilever": '''from build123d import *
with BuildPart() as p:
    # Base (Widened to 40mm to support the cantilevered arm's center of mass)
    Box(40, 10, 5, align=(Align.MIN, Align.MIN, Align.MIN))
    # Pillar
    with Locations((0, 0, 5)):
        Box(5, 5, 60, align=(Align.MIN, Align.MIN, Align.MIN))
    # Arm
    with Locations((0, 0, 65)):
        Box(60, 10, 5, align=(Align.MIN, Align.MIN, Align.MIN))

final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "bracket": """from build123d import *

# A simple L-bracket using the + operator
base_box = Box(40, 20, 5, align=(Align.MIN, Align.MIN, Align.MIN))
wall_box = Box(5, 20, 40, align=(Align.MIN, Align.MIN, Align.MIN))

final_part = base_box + wall_box
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
""",

    "hollow_container": '''from build123d import *
with BuildPart() as p:
    # Outer solid (e.g., a cup or box)
    Cylinder(radius=15, height=30, align=(Align.MIN, Align.MIN, Align.MIN))
    # Subtract inner solid, shifting up by 2mm for the floor, and reducing radius by 2mm for walls
    with Locations((0, 0, 2)):
        Cylinder(radius=13, height=30, align=(Align.MIN, Align.MIN, Align.MIN), mode=Mode.SUBTRACT)
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "overhang_support": '''from build123d import *
with BuildPart() as p:
    # A roof floating at Z=40
    with Locations((0, 0, 40)):
        Box(30, 30, 5, align=(Align.MIN, Align.MIN, Align.MIN))
    # A support pillar extending from Z=0 up to the roof to prevent mid-air printing
    Box(10, 10, 40, align=(Align.MIN, Align.MIN, Align.MIN))
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "cone": '''from build123d import *
with BuildPart() as p:
    Cone(bottom_radius=10, top_radius=0, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "cube": '''from build123d import *
with BuildPart() as p:
    Box(20, 20, 20, align=(Align.MIN, Align.MIN, Align.MIN))
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "cylinder": '''from build123d import *
with BuildPart() as p:
    Cylinder(radius=10, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "gear": '''from build123d import *
with BuildPart() as p:
    with BuildSketch():
        RegularPolygon(radius=20, side_count=12)
        measure = 20
        for i in range(12):
            with Locations((measure * 0.9, 0)):
                Circle(3)
    extrude(amount=5)
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
''',

    "pyramid": '''from build123d import *
with BuildPart() as p:
    # A pyramid is just a lofted rect
    with BuildSketch(Location((0,0,0))):
        Rectangle(20, 20)
    with BuildSketch(Location((0,0,20))):
        Rectangle(0.1, 0.1) # Tiny point at top
    loft()
final_part = p.part
export_stl(final_part, 'generated_files/generated_part.stl')
export_step(final_part, 'generated_files/generated_part.step')
'''
}

def get_shape_blueprint(shape_type: str) -> str:
    """
    Fetches a validated build123d blueprint for a specific shape category.
    """
    if shape_type in EXAMPLE_VAULT:
        return EXAMPLE_VAULT[shape_type]
    return f"I'm sorry, no exact blueprint exists for '{shape_type}'. Please do your best using standard build123d practices."

CAD_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_shape_blueprint",
            "description": "Fetches a perfect, validated Python build123d blueprint for a specific shape category. Use this to learn the correct syntax and alignment rules before writing your own code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shape_type": {
                        "type": "string",
                        "enum": ["sphere", "cantilever", "bracket", "hollow_container", "overhang_support", "cone", "cube", "cylinder", "gear", "pyramid"]
                    }
                },
                "required": ["shape_type"]
            }
        }
    }
]
