"""
Theme Definitions - Data models for LCD display themes
Supports serialization to JSON for persistence and sharing
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path
import json


class ElementType(Enum):
    """Element types for theme composition"""
    BACKGROUND = "background"
    TEXT_LABEL = "text_label"
    GAUGE = "gauge"
    PROGRESS_BAR = "progress_bar"
    IMAGE = "image"
    ANIMATED_GIF = "animated_gif"
    ICON = "icon"
    GRAPH = "graph"
    RING = "ring"


@dataclass
class Color:
    """RGB Color representation"""
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255  # Alpha (0-255)
    
    def to_hex(self) -> str:
        """Convert to hex color string"""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"
    
    @staticmethod
    def from_hex(hex_color: str) -> 'Color':
        """Create Color from hex string"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return Color(r, g, b)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {"r": self.r, "g": self.g, "b": self.b, "a": self.a}
    
    @staticmethod
    def from_dict(data: Dict) -> 'Color':
        """Create Color from dictionary"""
        return Color(**data)


@dataclass
class Position:
    """2D position coordinates"""
    x: int = 0
    y: int = 0
    
    def to_dict(self) -> Dict:
        return {"x": self.x, "y": self.y}
    
    @staticmethod
    def from_dict(data: Dict) -> 'Position':
        return Position(**data)


@dataclass
class Size:
    """Dimensions"""
    width: int = 100
    height: int = 100
    
    def to_dict(self) -> Dict:
        return {"width": self.width, "height": self.height}
    
    @staticmethod
    def from_dict(data: Dict) -> 'Size':
        return Size(**data)


@dataclass
class BackgroundElement:
    """Background element"""
    element_id: str = "background"
    element_type: ElementType = ElementType.BACKGROUND
    color: Optional[Color] = None
    image_path: Optional[str] = None
    opacity: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "color": self.color.to_dict() if self.color else None,
            "image_path": self.image_path,
            "opacity": self.opacity,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'BackgroundElement':
        data = data.copy()
        if "color" in data and data["color"]:
            data["color"] = Color.from_dict(data["color"])
        if "element_type" in data:
            data["element_type"] = ElementType(data["element_type"])
        return BackgroundElement(**data)


@dataclass
class TextElement:
    """Text label element with data binding support"""
    element_id: str
    position: Optional[Position] = None
    text: str = "Label"
    font_size: int = 12
    color: Optional[Color] = None
    data_source: Optional[str] = None  # e.g., "cpu_temp", "pump_rpm"
    format_string: str = "{value}"  # e.g., "{value:.1f}°C"
    font_family: str = "DejaVuSans"
    bold: bool = False
    element_type: ElementType = ElementType.TEXT_LABEL
    
    def to_dict(self) -> Dict:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "position": self.position.to_dict() if self.position else None,
            "text": self.text,
            "font_size": self.font_size,
            "color": self.color.to_dict() if self.color else None,
            "data_source": self.data_source,
            "format_string": self.format_string,
            "font_family": self.font_family,
            "bold": self.bold,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'TextElement':
        data = data.copy()
        if "position" in data and data["position"]:
            data["position"] = Position.from_dict(data["position"])
        if "color" in data and data["color"]:
            data["color"] = Color.from_dict(data["color"])
        if "element_type" in data:
            data["element_type"] = ElementType(data["element_type"])
        return TextElement(**data)


@dataclass
class GaugeElement:
    """Circular gauge element with data binding"""
    element_id: str
    position: Optional[Position] = None
    radius: int = 50
    data_source: str = "cpu_temp"
    min_value: float = 0
    max_value: float = 100
    color_min: Optional[Color] = None  # Color at min value
    color_max: Optional[Color] = None  # Color at max value
    show_value: bool = True
    element_type: ElementType = ElementType.GAUGE
    
    def to_dict(self) -> Dict:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "position": self.position.to_dict() if self.position else None,
            "radius": self.radius,
            "data_source": self.data_source,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "color_min": self.color_min.to_dict() if self.color_min else None,
            "color_max": self.color_max.to_dict() if self.color_max else None,
            "show_value": self.show_value,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'GaugeElement':
        data = data.copy()
        if "position" in data and data["position"]:
            data["position"] = Position.from_dict(data["position"])
        if "color_min" in data and data["color_min"]:
            data["color_min"] = Color.from_dict(data["color_min"])
        if "color_max" in data and data["color_max"]:
            data["color_max"] = Color.from_dict(data["color_max"])
        if "element_type" in data:
            data["element_type"] = ElementType(data["element_type"])
        return GaugeElement(**data)


@dataclass
class ProgressBarElement:
    """Progress bar element"""
    element_id: str
    position: Optional[Position] = None
    size: Optional[Size] = None
    data_source: str = "cpu_usage"
    min_value: float = 0
    max_value: float = 100
    color: Optional[Color] = None
    background_color: Optional[Color] = None
    element_type: ElementType = ElementType.PROGRESS_BAR
    
    def to_dict(self) -> Dict:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "position": self.position.to_dict() if self.position else None,
            "size": self.size.to_dict() if self.size else None,
            "data_source": self.data_source,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "color": self.color.to_dict() if self.color else None,
            "background_color": self.background_color.to_dict() if self.background_color else None,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'ProgressBarElement':
        data = data.copy()
        if "position" in data and data["position"]:
            data["position"] = Position.from_dict(data["position"])
        if "size" in data and data["size"]:
            data["size"] = Size.from_dict(data["size"])
        if "color" in data and data["color"]:
            data["color"] = Color.from_dict(data["color"])
        if "background_color" in data and data["background_color"]:
            data["background_color"] = Color.from_dict(data["background_color"])
        if "element_type" in data:
            data["element_type"] = ElementType(data["element_type"])
        return ProgressBarElement(**data)


class Theme:
    """Complete theme definition with serialization"""
    
    def __init__(self, name: str = "Untitled", canvas_width: int = 480, 
                 canvas_height: int = 480, background: Optional[BackgroundElement] = None):
        self.name = name
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.background = background
        self.elements: List = []
        self.version = "1.0"
    
    def add_element(self, element):
        """Add element to theme"""
        self.elements.append(element)
    
    def remove_element(self, element_id: str):
        """Remove element by ID"""
        self.elements = [e for e in self.elements if getattr(e, 'element_id', None) != element_id]
    
    def to_dict(self) -> Dict:
        """Convert theme to dictionary"""
        elements_data = []
        for elem in self.elements:
            if hasattr(elem, 'to_dict'):
                elements_data.append(elem.to_dict())
        
        return {
            "version": self.version,
            "name": self.name,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "background": self.background.to_dict() if self.background else None,
            "elements": elements_data,
        }
    
    def to_json(self) -> str:
        """Convert theme to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    def save(self, file_path: Path):
        """Save theme to JSON file"""
        file_path = Path(file_path)
        with open(file_path, 'w') as f:
            f.write(self.to_json())
    
    @staticmethod
    def from_dict(data: Dict) -> 'Theme':
        """Create Theme from dictionary"""
        theme = Theme(
            name=data.get("name", "Untitled"),
            canvas_width=data.get("canvas_width", 480),
            canvas_height=data.get("canvas_height", 480),
        )
        
        if data.get("background"):
            theme.background = BackgroundElement.from_dict(data["background"])
        
        # Deserialize elements
        for elem_data in data.get("elements", []):
            elem_type = ElementType(elem_data.get("element_type", "text_label"))
            
            if elem_type == ElementType.TEXT_LABEL:
                theme.add_element(TextElement.from_dict(elem_data))
            elif elem_type == ElementType.GAUGE:
                theme.add_element(GaugeElement.from_dict(elem_data))
            elif elem_type == ElementType.PROGRESS_BAR:
                theme.add_element(ProgressBarElement.from_dict(elem_data))
        
        return theme
    
    @staticmethod
    def from_json(json_str: str) -> 'Theme':
        """Create Theme from JSON string"""
        data = json.loads(json_str)
        return Theme.from_dict(data)
    
    @staticmethod
    def load(file_path: Path) -> 'Theme':
        """Load theme from JSON file"""
        file_path = Path(file_path)
        with open(file_path, 'r') as f:
            json_str = f.read()
        return Theme.from_json(json_str)
