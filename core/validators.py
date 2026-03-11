# core/validators.py
import re
import json
import requests
from build123d import GeomType, Axis

def extract_dimensions(prompt):
    """Extracts all numbers from the prompt to use as reference for scaling."""
    dims = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|unit|diameter|length|width|height|outer|inner)?", prompt.lower())
    return [float(d) for d in dims]

def extract_design_intent_llm(prompt: str) -> dict:
    """
    Deterministic intent extraction to prevent LLM hallucinations.
    Updated with organic dataset keywords.
    """
    prompt_lower = prompt.lower()
    
    intent = {
        "is_bracket": any(word in prompt_lower for word in ["bracket", "l-bracket", "u-bracket", "mounting", "plate", "shelf mount"]),
        "is_container": any(word in prompt_lower for word in ["cup", "bowl", "hollow", "pipe", "vase", "container"]),
        "requires_holes": any(word in prompt_lower for word in ["hole", "drill", "screw", "mount"]) and not any(neg in prompt_lower for neg in ["no hole", "without hole", "do not add", "forget to add"]),
        "is_3d_printable": any(word in prompt_lower for word in ["3d print", "fdm", "printable", "stand", "toy"])
    }
    
    # 4. Dimension Safety (target_dimension)
    numbers = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', prompt)]
    
    # If the user explicitly asks for a single scaled dimension (e.g. '5000mm length' or '0.001mm radius')
    # and NO OTHER dimensions are present, we strictly enforce it.
    if len(numbers) == 1:
        intent["target_dimension"] = numbers[0]
    else:
        # If there are multiple dimensions (e.g., '50x50x5mm plate'), we set target_dimension to None 
        # to avoid the simple 1D bbox check from flagging perfectly valid multi-dimensional boxes.
        intent["target_dimension"] = None
    
    print(f"Deterministic Intent Extracted: {intent}")
    return intent

def validate_geometry(part, intent=None, user_prompt="", z_offset=0.0):
    """
    Physics and Engineering Validator for build123d parts.
    Checks against LLM-extracted intent and physical constraints.
    """
    if intent is None:
        intent = {}
        
    if part is None:
        return False, {"error_type": "NoPart", "message": "No part object found."}
    
    # --- BASELINE: Physicality ---
    is_valid_manifold = False
    try:
        is_valid_manifold = part.is_valid if not callable(part.is_valid) else part.is_valid()
    except:
        pass

    volume = 0.0
    try:
        volume = part.volume
    except:
        pass

    if not is_valid_manifold or volume <= 0:
        return False, {
            "error_type": "TopologyViolation",
            "manifold": bool(is_valid_manifold),
            "volume": float(volume),
            "message": "The generated shape is non-manifold (not watertight) or has zero volume. HINT TO FIX: Simplify your boolean operations or ensure no faces are self-intersecting."
        }

    # --- Bounding Box Extraction ---
    try:
        bbox = part.bounding_box()
        dx = bbox.max.X - bbox.min.X
        dy = bbox.max.Y - bbox.min.Y
        dz = bbox.max.Z - bbox.min.Z
        max_actual_dim = max(dx, dy, dz)
        bbox_volume = dx * dy * dz
    except:
        return False, {"error_type": "MeasurementError", "message": "Could not calculate bounding box."}

    print(f"[PHYSICS DEBUG] Bounding Box: {round(dx,2)} x {round(dy,2)} x {round(dz,2)} | Max Dim: {round(max_actual_dim,2)} | Volume: {round(volume,2)}")
    # --- SCALE GUARD ---
    target = intent.get("target_dimension")
    if target is None:
        # Fallback to regex
        requested_dims = extract_dimensions(user_prompt)
        if requested_dims:
            target = max(requested_dims)
            
    if target:
        if max_actual_dim > (target * 1.5) or max_actual_dim < (target * 0.5):
            scalar = target / max_actual_dim if max_actual_dim > 0 else 1.0
            return False, {
                "error_type": "ScaleViolation",
                "actual_size": round(max_actual_dim, 2),
                "requested_size": target,
                "message": f"Dimension Mismatch: The part is {round(max_actual_dim, 2)}mm, but requested {target}mm. (Allowed range: 0.5x - 1.5x). HINT TO FIX: Multiply your base dimensions (length, width, or radius) by exactly {scalar:.2f}. For example, if you used radius=10, change it to radius={round(10*scalar, 2)}."
            }

    # --- CONTAINER CHECK --- 
    if intent.get("is_container"): 
        # Calculate how much of the bounding box is actually filled with material 
        fill_ratio = volume / bbox_volume if bbox_volume > 0 else 1.0 
        print(f"[PHYSICS DEBUG] Container Fill Ratio: {round(fill_ratio, 3)} (Needs to be < 0.7 to be considered hollow)")         
        # A solid cylinder is ~0.785. A solid box is 1.0. 
        # If it's > 0.7, they forgot to subtract the inside! 
        if fill_ratio > 0.7: 
            return False, { 
                "error_type": "FunctionalViolation", 
                "issue": "Missing Hollow Features", 
                "message": "User requested a hollow container, but the generated part is completely solid. Use Boolean Subtraction to hollow it out. HINT TO FIX: `with Locations((0, 0, wall_thickness)): Cylinder(radius=inner_r, height=inner_h, mode=Mode.SUBTRACT)`" 
            } 
 
        try: 
            area = part.area 
            # A hollow cup with 0.1mm walls will have a tiny volume but massive surface area 
            if area and (volume / area) < 0.3: 
                return False, { 
                    "error_type": "EngineeringViolation", 
                    "issue": "Thin Walls", 
                    "message": "Walls are too thin to manufacture safely. HINT TO FIX: Standard 3D printing requires a minimum wall thickness of 1.2mm. Do NOT change your outer dimensions to fix this! Instead, calculate your inner subtraction shape using strict math: `inner_radius = target_radius - 1.2` (or `inner_length = target_length - 2.4` for boxes). Leave exactly 1.2mm of material on all sides." 
                } 
        except: 
            return False, {
                "error_type": "MathCalculationError",
                "message": "MathCalculationError: The generated geometry is invalid or non-manifold, preventing physical calculations. HINT TO FIX: Simplify your boolean operations or ensure no faces are self-intersecting."
            }

    if intent.get("is_bracket") or intent.get("requires_holes"):
        # Bracket topological check
        if intent.get("is_bracket"):
            fill_ratio = volume / bbox_volume if bbox_volume > 0 else 1.0
            if fill_ratio > 0.7:
                return False, {
                    "error_type": "FunctionalViolation",
                    "issue": "Missing Bracket Geometry",
                    "message": "User requested a bracket, but you generated a flat plate or solid block. A bracket must have horizontal and vertical flanges (an L-shape or U-shape). HINT TO FIX: Create an L-bracket by combining two boxes using the addition operator `+`. Ensure one box is vertical and one is horizontal, and they share a corner."
                }
        
        try:
            cylinder_count = 0
            for face in part.faces():
                try:
                    face_type = face.geom_type
                    if hasattr(face_type, "name"):
                        face_type_str = face_type.name
                    else:
                        face_type_str = str(face_type)
                except:
                    try:
                        face_type_str = face.geom_type().upper()
                    except:
                        face_type_str = ""
                if str(face_type_str).upper() == "CYLINDER":
                    cylinder_count += 1
            if cylinder_count == 0 and intent.get("requires_holes"):
                return False, {
                    "error_type": "FunctionalViolation",
                    "issue": "Missing Holes",
                    "message": "User requested mounting holes, but no cylindrical cavities were detected. Use boolean subtraction to add holes. HINT TO FIX: You must use the minus operator (-) to subtract a Cylinder from your main body. Example: `hole = Cylinder(radius=2.5, height=50); final_part = main_body - hole`."
                }
        except:
            return False, {
                "error_type": "MathCalculationError",
                "message": "MathCalculationError: The generated geometry is invalid or non-manifold, preventing physical calculations. HINT TO FIX: Simplify your boolean operations or ensure no faces are self-intersecting."
            }

    try:
        center = part.center()
        faces = part.faces().sort_by(Axis.Z)
        if faces:
            base_face = faces[0]
            base_bbox = base_face.bounding_box()
            if not (base_bbox.min.X <= center.X <= base_bbox.max.X) or not (base_bbox.min.Y <= center.Y <= base_bbox.max.Y):
                # Calculate required expansion (v_x, v_y) to safely enclose the center of mass
                v_x = 0.0
                v_y = 0.0
                
                if center.X > base_bbox.max.X:
                    v_x = center.X - base_bbox.max.X + 2.0  # Widen right by deficit + 2mm margin
                elif center.X < base_bbox.min.X:
                    v_x = base_bbox.min.X - center.X + 2.0  # Widen left 
                    
                if center.Y > base_bbox.max.Y:
                    v_y = center.Y - base_bbox.max.Y + 2.0  # Widen forward
                elif center.Y < base_bbox.min.Y:
                    v_y = base_bbox.min.Y - center.Y + 2.0  # Widen backward

                dist = (v_x**2 + v_y**2)**0.5
                
                return False, {
                    "error_type": "FunctionalViolation",
                    "issue": "Stability",
                    "message": f"Stability Error: The Center of Mass (X={center.X:.2f}, Y={center.Y:.2f}) is {dist:.2f}mm outside the support base's footprint. The object will tip over! HINT TO FIX: You MUST drastically widen the bottom-most Box. Increase your base width (X) by {v_x:.2f}mm and depth (Y) by {v_y:.2f}mm so it safely supports the heavy cantilever limits."
                }
    except:
        return False, {
            "error_type": "MathCalculationError",
            "message": "MathCalculationError: The generated geometry is invalid or non-manifold, preventing physical calculations. HINT TO FIX: Simplify your boolean operations or ensure no faces are self-intersecting."
        }

    # --- DFM PRINTABILITY & OVERHANG VALIDATION --- 
    if intent.get("is_3d_printable"):
        try:
            bottom_z = part.bounding_box().min.Z
            
            # 1. Bed Adhesion Check (Must have a flat bottom)
            bottom_faces = part.faces().sort_by(Axis.Z)
            if bottom_faces:
                lowest_face = bottom_faces[0]
                # Safely check if the lowest face is a flat plane
                if "PLANE" not in str(lowest_face.geom_type).upper():
                    
                    if abs(z_offset) > 0.1:
                        error_msg = f"Your part does not have a flat base, AND it was floating at Z={z_offset:.2f}. Although the system auto-grounded it for this test, you MUST fix your code logic. Use Locations((0, 0, -{z_offset:.2f})) or adjust your subtraction box to ensure the base is flat and at exactly Z=0."
                    else:
                        error_msg = "The part does not have a flat base on the XY plane (Z-min), which is required for 3D printing adhesion. HINT TO FIX: Slice a small amount off the bottom using boolean subtraction so it sits flat."
                        
                    return False, {
                        "error_type": "EngineeringViolation",
                        "issue": "Printability / Adhesion",
                        "message": error_msg
                    }

            # 2. Overhang Validator (The 45-Degree Rule)
            for face in part.faces():
                # Get the normal vector at the center of the face
                normal = face.normal_at(face.center())
                
                # In FDM, a 45-degree angle corresponds to a Z normal of roughly -0.707.
                # Anything closer to -1.0 (straight down) is unprintable without supports.
                if normal.Z < -0.707:
                    # Check if the face is floating above the bottom (not touching the build plate)
                    # Adding a small tolerance (0.2mm) for standard FDM layer heights
                    if face.bounding_box().min.Z > bottom_z + 0.2:
                        return False, {
                            "error_type": "ManufacturingViolation",
                            "issue": "Unprintable Overhang",
                            "message": f"Validation Failed: You generated a severe mid-air overhang (Normal Z: {normal.Z:.2f}). FDM 3D printers cannot print in mid-air! HINT TO FIX: You MUST redesign this. Either extend a supporting pillar directly beneath the floating face down to the base, or widen the base structure to eliminate the overhang."
                        }
                        
        except Exception as e:
            return False, {
                "error_type": "MathCalculationError",
                "message": "MathCalculationError: The generated geometry is invalid or non-manifold, preventing physical calculations. HINT TO FIX: Simplify your boolean operations or ensure no faces are self-intersecting."
            }

    return True, {"message": "Success"}

def extract_design_intent(user_prompt):
    """Legacy alias for backward compatibility."""
    return extract_design_intent_llm(user_prompt)
