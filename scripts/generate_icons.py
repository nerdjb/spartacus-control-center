#!/usr/bin/env python3
"""
Icon Generator Script
Converts SVG icon to PNG at multiple resolutions for Linux desktop integration
"""

import subprocess
import os
from pathlib import Path

# Define output directories and sizes
ICON_SIZES = {
    48: "icons/48x48",
    128: "icons/128x128", 
    256: "icons/256x256",
    512: "icons/512x512"
}

SVG_SOURCE = "assets/spartacus-control.svg"

def generate_icons():
    """Generate PNG icons from SVG using ImageMagick or Inkscape"""
    
    svg_path = Path(SVG_SOURCE)
    if not svg_path.exists():
        print(f"Error: SVG source file not found at {SVG_SOURCE}")
        return False
    
    # Create output directories
    assets_dir = Path("assets")
    for size, subdir in ICON_SIZES.items():
        output_dir = assets_dir / subdir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / "spartacus-control.png"
        
        # Try using ImageMagick's convert command
        try:
            cmd = [
                "convert",
                "-background", "none",
                "-density", "384",  # High DPI for quality
                "-size", f"{size}x{size}",
                str(svg_path),
                "-resize", f"{size}x{size}",
                "-gravity", "center",
                "-extent", f"{size}x{size}",
                str(output_file)
            ]
            
            print(f"Generating {size}x{size} icon...")
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"  ✓ Created {output_file}")
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error creating {size}x{size} icon: {e}")
            return False
        except FileNotFoundError:
            print("  ✗ ImageMagick 'convert' not found. Install it with:")
            print("    sudo pacman -S imagemagick")
            return False
    
    return True

def install_icons():
    """Install icons to system directories"""
    
    home = Path.home()
    app_icons_dir = home / ".local/share/icons/hicolor"
    
    for size, subdir in ICON_SIZES.items():
        src_dir = Path("assets") / subdir
        dst_dir = app_icons_dir / f"{size}x{size}/apps"
        
        if src_dir.exists():
            dst_dir.mkdir(parents=True, exist_ok=True)
            
            for png_file in src_dir.glob("*.png"):
                dst_file = dst_dir / png_file.name
                try:
                    # Copy file
                    import shutil
                    shutil.copy2(png_file, dst_file)
                    print(f"Installed {dst_file}")
                except Exception as e:
                    print(f"Error installing {png_file}: {e}")

if __name__ == "__main__":
    print("Spartacus Control Center - Icon Generator")
    print("=" * 50)
    
    if generate_icons():
        print("\n✓ All icons generated successfully!")
        print("\nTo install icons system-wide:")
        print("  python3 scripts/generate_icons.py --install")
    else:
        print("\n✗ Icon generation failed")
        exit(1)
