import streamlit as st
import os
from backend import generate_cad_part

def main():
    st.set_page_config(page_title="AI CAD Agent", layout="wide")
    st.title("AI CAD Agent")

    # Main Chat Input
    user_prompt = st.chat_input("Describe the part you want to create (e.g., 'Make a bracket')")

    if user_prompt:
        with st.status("Generating CAD model...", expanded=True) as status:
            st.write(f"Requesting: {user_prompt}")
            
            # Call backend (Returns a dictionary of paths)
            result_files = generate_cad_part(user_prompt)
            
            if isinstance(result_files, dict):
                status.update(label="Generation Complete!", state="complete", expanded=False)
                st.success("Successfully generated CAD models!")
                
                # Create two columns for the download buttons
                col1, col2 = st.columns(2)
                
                # 1. STEP Download Button
                if result_files.get("step") and os.path.exists(result_files["step"]):
                    with open(result_files["step"], "rb") as f:
                        col1.download_button(
                            label="📥 Download STEP (CAD Solid)",
                            data=f,
                            file_name=os.path.basename(result_files["step"]),
                            mime="application/octet-stream"
                        )
                        
                # 2. STL Download Button
                if result_files.get("stl") and os.path.exists(result_files["stl"]):
                    with open(result_files["stl"], "rb") as f:
                        col2.download_button(
                            label="📥 Download STL (3D Mesh)",
                            data=f,
                            file_name=os.path.basename(result_files["stl"]),
                            mime="application/sla"
                        )
            else:
                status.update(label="Generation Failed", state="error", expanded=True)
                st.error("Failed to generate the CAD part. Check the terminal logs.")

if __name__ == "__main__":
    main()