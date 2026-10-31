import subprocess
import os
from PIL import Image

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
svg_dir = r"E:\SEM 5 PROJECT\LexGuard-HTML\report_diagrams_svg"
out_dir = r"E:\SEM 5 PROJECT\LexGuard-HTML\report_builder\diagrams"

svg_map = {
    "Figure_3_1_UseCase_Diagram.svg": "fig_3_1_use_case.png",
    "Figure_3_2_Class_Diagram.svg": "fig_3_2_class.png",
    "Figure_3_3_Activity_Ingestion_Diagram.svg": "fig_3_2_activity.png",
    "Figure_3_4_Sequence_Precedent_Search_Draft_Diagram.svg": "fig_3_4_sequence.png",
    "Figure_3_5_Sequence_Document_Verification_Audit_Diagram.svg": "fig_3_5_sequence_verify.png",
    "Figure_3_6_State_Machine_Diagram.svg": "fig_3_3_state.png",
    "Figure_3_7_Component_Diagram.svg": "fig_3_7_architecture.png",
    "Figure_3_8_Deployment_Diagram.svg": "fig_3_8_deployment.png",
    "Figure_3_9_Chen_ER_Diagram.svg": "fig_3_5_er.png"
}

def render_svg_to_png():
    for svg_name, png_name in svg_map.items():
        svg_file = os.path.join(svg_dir, svg_name)
        png_file = os.path.join(out_dir, png_name)
        temp_html = os.path.join(out_dir, "temp_view.html")
        temp_shot = os.path.join(out_dir, "temp_shot.png")
        
        # Read SVG text
        with open(svg_file, "r", encoding="utf-8") as f:
            svg_content = f.read()
            
        # Create a clean white-background HTML container for pixel-perfect rendering
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 30px;
    background: #ffffff;
    display: flex;
    justify-content: center;
    align-items: center;
  }}
  svg {{
    max-width: 100%;
    height: auto;
    background: #ffffff;
    box-shadow: none;
  }}
</style>
</head>
<body>
{svg_content}
</body>
</html>"""
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Call headless chrome
        args = [
            chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--default-background-color=ffffff",
            f"--screenshot={temp_shot}",
            "--window-size=2200,1600",
            temp_html
        ]
        res = subprocess.run(args, capture_output=True)
        
        if os.path.exists(temp_shot):
            # Crop whitespace borders using PIL for maximum crispness
            img = Image.open(temp_shot)
            # Find bounding box of non-pure-white content
            # Convert to RGB
            img_rgb = img.convert("RGB")
            # Get bbox
            from PIL import ImageChops
            bg = Image.new(img_rgb.mode, img_rgb.size, (255, 255, 255))
            diff = ImageChops.difference(img_rgb, bg)
            bbox = diff.getbbox()
            if bbox:
                # Add small 20px padding
                w, h = img.size
                pad = 25
                x0 = max(0, bbox[0] - pad)
                y0 = max(0, bbox[1] - pad)
                x1 = min(w, bbox[2] + pad)
                y1 = min(h, bbox[3] + pad)
                cropped = img.crop((x0, y0, x1, y1))
                cropped.save(png_file, "PNG", dpi=(300, 300))
            else:
                img.save(png_file, "PNG", dpi=(300, 300))
            print(f"Rendered {svg_name} -> {png_name} successfully ({os.path.getsize(png_file)} bytes)")
            if os.path.exists(temp_shot):
                os.remove(temp_shot)
        else:
            print(f"Failed to render {svg_name}")

    if os.path.exists(temp_html):
        os.remove(temp_html)

if __name__ == "__main__":
    render_svg_to_png()
