"""
Theme Renderer - Converts theme definitions to LCD display frames
Renders themed elements to PIL Image for USB transmission
"""

from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, Optional
import io
import math
from models.theme import Theme, TextElement, GaugeElement, Color, Position, ElementType


class ThemeRenderer:
    """Renders themes to 480×480 pixel images for LCD display"""
    
    CANVAS_WIDTH = 480
    CANVAS_HEIGHT = 480
    
    def __init__(self, theme: Theme):
        self.theme = theme
        self.image = None
        self.draw = None
        self._telemetry_data = {}
    
    def set_telemetry(self, data: Dict[str, Any]):
        """Set current telemetry data for rendering"""
        self._telemetry_data = data
    
    def render(self) -> Image.Image:
        """Render theme to PIL Image"""
        # Create new image
        self.image = Image.new('RGB', (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        
        # Render background
        if self.theme.background:
            self._render_background()
        
        # Render all elements
        for element in self.theme.elements:
            if isinstance(element, TextElement):
                self._render_text_element(element)
            elif isinstance(element, GaugeElement):
                self._render_gauge_element(element)
        
        return self.image
    
    def render_to_bytes(self) -> bytes:
        """Render theme to bytes for USB transmission"""
        image = self.render()
        # Convert to JPEG for efficient transmission
        jpeg_buffer = io.BytesIO()
        image.save(jpeg_buffer, format='JPEG', quality=90)
        return jpeg_buffer.getvalue()
    
    def render_to_rgb_array(self) -> bytes:
        """Render theme to raw RGB bytes (480×480×3)"""
        image = self.render()
        return image.tobytes()
    
    def _render_background(self):
        """Render background color or image"""
        bg = self.theme.background
        
        if bg.color:
            # Solid color background
            color = (bg.color.r, bg.color.g, bg.color.b)
            self.draw.rectangle(
                [(0, 0), (self.CANVAS_WIDTH, self.CANVAS_HEIGHT)],
                fill=color
            )
        
        if bg.image_path:
            # Background image (would load from file)
            # For now, just colored rectangle
            pass
    
    def _render_text_element(self, element: TextElement):
        """Render text element"""
        if not element.position:
            return
        
        # Get display text
        display_text = element.text
        
        if element.data_source and element.data_source in self._telemetry_data:
            value = self._telemetry_data[element.data_source]
            try:
                display_text = element.format_string.format(value=value)
            except:
                display_text = str(value)
        
        # Prepare font
        font = self._get_font(element.font_size, element.bold)
        
        # Get color
        color = (element.color.r, element.color.g, element.color.b) if element.color else (255, 255, 255)
        
        # Draw text (centered)
        self.draw.text(
            (element.position.x, element.position.y),
            display_text,
            fill=color,
            font=font,
            anchor="mm"  # Middle-middle anchor
        )
    
    def _render_gauge_element(self, element: GaugeElement):
        """Render circular gauge element"""
        if not element.position or not element.data_source:
            return
        
        # Get current value
        if element.data_source not in self._telemetry_data:
            return
        
        value = self._telemetry_data[element.data_source]
        
        # Calculate percentage (0-100)
        value_range = element.max_value - element.min_value
        percentage = max(0, min(100, (value - element.min_value) / value_range * 100))
        
        # Interpolate color based on percentage
        color = self._interpolate_color(
            element.color_min or Color(0, 255, 136),
            element.color_max or Color(255, 100, 0),
            percentage / 100.0
        )
        
        # Draw gauge circle (outer ring)
        x, y = element.position.x, element.position.y
        r = element.radius
        
        # Background circle (gray)
        self.draw.ellipse(
            [(x - r, y - r), (x + r, y + r)],
            outline=(50, 50, 50),
            width=3
        )
        
        # Filled arc (progress)
        self.draw.arc(
            [(x - r, y - r), (x + r, y + r)],
            start=0,
            end=int(360 * percentage / 100),
            fill=(color.r, color.g, color.b),
            width=8
        )
        
        # Center dot
        self.draw.ellipse(
            [(x - 5, y - 5), (x + 5, y + 5)],
            fill=(color.r, color.g, color.b)
        )
        
        # Display value in center if enabled
        if element.show_value:
            font = self._get_font(14, True)
            value_text = f"{value:.1f}"
            self.draw.text(
                (x, y),
                value_text,
                fill=(color.r, color.g, color.b),
                font=font,
                anchor="mm"
            )
    
    def _interpolate_color(self, color_min: Color, color_max: Color, factor: float) -> Color:
        """Interpolate between two colors"""
        factor = max(0, min(1, factor))
        
        r = int(color_min.r + (color_max.r - color_min.r) * factor)
        g = int(color_min.g + (color_max.g - color_min.g) * factor)
        b = int(color_min.b + (color_max.b - color_min.b) * factor)
        
        return Color(r, g, b)
    
    def _get_font(self, size: int, bold: bool = False) -> Optional[ImageFont.FreeTypeFont]:
        """Get font object"""
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
            font_file = f"{font_path}-Bold.ttf" if bold else f"{font_path}.ttf"
            return ImageFont.truetype(font_file, size)
        except:
            # Fallback to default font
            return ImageFont.load_default()
    
    def preview_to_pil(self) -> Image.Image:
        """Get PIL Image for preview in GUI"""
        return self.render()


class ThemeManager:
    """Manages theme loading, switching, and rendering"""
    
    def __init__(self):
        self.current_theme: Optional[Theme] = None
        self.themes: Dict[str, Theme] = {}
        self.renderer: Optional[ThemeRenderer] = None
    
    def load_theme(self, theme: Theme) -> bool:
        """Load and activate a theme"""
        try:
            self.current_theme = theme
            self.renderer = ThemeRenderer(theme)
            return True
        except Exception as e:
            print(f"Error loading theme: {e}")
            return False
    
    def set_telemetry(self, data: Dict[str, Any]):
        """Update telemetry for current theme rendering"""
        if self.renderer:
            self.renderer.set_telemetry(data)
    
    def render_frame(self, telemetry_data: Dict[str, Any]) -> bytes:
        """Render current frame with telemetry"""
        if not self.renderer:
            return b''
        
        self.renderer.set_telemetry(telemetry_data)
        return self.renderer.render_to_rgb_array()
    
    def get_preview(self, telemetry_data: Dict[str, Any]) -> Image.Image:
        """Get preview image for GUI"""
        if not self.renderer:
            return Image.new('RGB', (480, 480), (0, 0, 0))
        
        self.renderer.set_telemetry(telemetry_data)
        return self.renderer.preview_to_pil()
    
    def register_theme(self, name: str, theme: Theme):
        """Register a theme for later switching"""
        self.themes[name] = theme
    
    def switch_theme(self, name: str) -> bool:
        """Switch to a registered theme by name"""
        if name in self.themes:
            return self.load_theme(self.themes[name])
        return False
    
    def get_theme_list(self) -> list:
        """Get list of available theme names"""
        return list(self.themes.keys())
